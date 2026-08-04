from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from .operator_contract import OperatorContract


NODE_KINDS = {
    "LoadStream", "DecodeField", "Map", "Zip", "Reduce", "Scan", "Window",
    "Gather", "Scatter", "Select", "StateRead", "StateWrite", "Materialize",
    "Pack", "Unpack", "Emit", "Barrier", "ExternalCall",
}


@dataclass(frozen=True)
class OperatorNode:
    id: str
    kind: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatorEdge:
    src: str
    dst: str
    element_type: str
    shape: list[Any]
    stride: list[int]
    alignment: int
    alias_set: str
    mutability: str
    lifetime: str
    memory_region: str
    ordering: str
    numerical_contract: str
    distribution: dict[str, Any] = field(default_factory=dict)
    reuse_distance: float | None = None


@dataclass(frozen=True)
class OperatorGraph:
    schema_version: str
    contract_hash: str
    graph_hash: str
    nodes: list[OperatorNode]
    edges: list[OperatorEdge]
    annotations: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_operator_graph(contract: OperatorContract, source_hash: str, ir_provenance: dict[str, Any] | None = None) -> OperatorGraph:
    raw = contract.data["graph"]
    nodes = [OperatorNode(str(n["id"]), str(n["kind"]), dict(n.get("attrs", {}))) for n in raw["nodes"]]
    node_ids = {node.id for node in nodes}
    errors = []
    if len(node_ids) != len(nodes):
        errors.append("operator graph node ids must be unique")
    for node in nodes:
        if node.kind not in NODE_KINDS:
            errors.append(f"unknown node kind {node.kind} at {node.id}")
        if node.kind == "ExternalCall" and not node.attrs.get("allowed", False):
            errors.append(f"ExternalCall {node.id} is disallowed")
    edges = []
    defaults = raw.get("edge_defaults", {})
    for index, edge in enumerate(raw["edges"]):
        merged = {**defaults, **edge}
        if merged.get("src") not in node_ids or merged.get("dst") not in node_ids:
            errors.append(f"edge {index} references an unknown node")
            continue
        try:
            edges.append(OperatorEdge(
                src=str(merged["src"]), dst=str(merged["dst"]), element_type=str(merged["element_type"]),
                shape=list(merged.get("shape", [])), stride=[int(v) for v in merged.get("stride", [])],
                alignment=int(merged.get("alignment", 1)), alias_set=str(merged.get("alias_set", "unknown")),
                mutability=str(merged.get("mutability", "immutable")), lifetime=str(merged.get("lifetime", "operator")),
                memory_region=str(merged.get("memory_region", "register")), ordering=str(merged.get("ordering", "data")),
                numerical_contract=str(merged.get("numerical_contract", "exact")), distribution=dict(merged.get("distribution", {})),
                reuse_distance=(float(merged["reuse_distance"]) if merged.get("reuse_distance") is not None else None),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"invalid edge {index}: {exc}")
    if errors:
        raise ValueError("invalid OperatorGraph:\n- " + "\n- ".join(errors))
    sccs = _strongly_connected_components(nodes, edges)
    regions = _fusion_regions(nodes, edges)
    traffic = _traffic_estimate(edges)
    annotations = {
        "fusion_boundaries": [node.id for node in nodes if node.kind in {"Barrier", "Materialize", "Emit"}],
        "fusion_regions": regions,
        "stateful_sccs": [component for component in sccs if len(component) > 1 or any(e.src == e.dst == component[0] for e in edges)],
        "reduction_algebra": {node.id: node.attrs.get("algebra") for node in nodes if node.kind == "Reduce"},
        "input_distribution": contract.data["distribution"],
        "target_objective": contract.data["objective"],
        "layout_ownership": {node.id: node.attrs.get("layout_owner") for node in nodes if node.attrs.get("layout_owner")},
        "edge_lifetimes": {f"{index}:{edge.src}->{edge.dst}": [next(i for i, n in enumerate(nodes) if n.id == edge.src), next(i for i, n in enumerate(nodes) if n.id == edge.dst)] for index, edge in enumerate(edges)},
        "estimated_materialized_bytes": traffic["materialized_bytes"],
        "estimated_stream_bytes": traffic["stream_bytes"],
        "proof_status": "unverified",
        "grammar_version": "operator-v3",
        "grammar_hash": hashlib.sha256(b"operator-v3").hexdigest(),
    }
    emitted = {str(node.attrs.get("output")) for node in nodes if node.kind == "Emit"}
    expected_outputs = set(contract.data["outputs"])
    if emitted != expected_outputs:
        raise ValueError(f"Emit nodes {sorted(emitted)} do not match contract outputs {sorted(expected_outputs)}")
    provenance = {
        "source_hash": source_hash,
        "contract_hash": contract.contract_hash,
        "entrypoint": contract.entrypoint,
        "extraction_stage": "contract+llvm-effects",
        "llvm": ir_provenance or {},
    }
    payload = {
        "schema_version": "operator-graph-v3.0",
        "contract_hash": contract.contract_hash,
        "nodes": [asdict(n) for n in nodes],
        "edges": [asdict(e) for e in edges],
        "annotations": annotations,
        "provenance": provenance,
    }
    graph_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return OperatorGraph("operator-graph-v3.0", contract.contract_hash, graph_hash, nodes, edges, annotations, provenance)


def write_operator_graph(path: Path, graph: OperatorGraph) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n")


def _strongly_connected_components(nodes: list[OperatorNode], edges: list[OperatorEdge]) -> list[list[str]]:
    adjacency = {node.id: [] for node in nodes}
    for edge in edges:
        adjacency[edge.src].append(edge.dst)
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in adjacency[node]:
            if nxt not in indices:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], indices[nxt])
        if low[node] == indices[node]:
            component = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            components.append(sorted(component))

    for node in sorted(adjacency):
        if node not in indices:
            visit(node)
    return sorted(components)


def _fusion_regions(nodes: list[OperatorNode], edges: list[OperatorEdge]) -> list[list[str]]:
    barriers = {node.id for node in nodes if node.kind in {"Barrier", "Materialize", "Emit", "ExternalCall"}}
    adjacency = {node.id: set() for node in nodes if node.id not in barriers}
    for edge in edges:
        if edge.src in adjacency and edge.dst in adjacency and edge.ordering != "external":
            adjacency[edge.src].add(edge.dst)
            adjacency[edge.dst].add(edge.src)
    regions, seen = [], set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        region, work = [], [start]
        while work:
            item = work.pop()
            if item in seen:
                continue
            seen.add(item)
            region.append(item)
            work.extend(sorted(adjacency[item] - seen))
        regions.append(sorted(region))
    return regions


def _traffic_estimate(edges: list[OperatorEdge]) -> dict[str, int]:
    sizes = {"i8": 1, "u8": 1, "i16": 2, "u16": 2, "f16": 2, "bf16": 2, "i32": 4, "u32": 4, "f32": 4, "i64": 8, "u64": 8, "f64": 8}
    stream = materialized = 0
    for edge in edges:
        count = 1
        bounded = True
        for dim in edge.shape:
            if isinstance(dim, int):
                count *= dim
            else:
                bounded = False
        byte_count = count * sizes.get(edge.element_type, 0) if bounded else 0
        if edge.memory_region in {"input", "output", "state", "stream"}:
            stream += byte_count
        if edge.memory_region in {"temporary", "scratch"}:
            materialized += byte_count
    return {"stream_bytes": stream, "materialized_bytes": materialized}
