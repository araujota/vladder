from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ELEMENT_BYTES = {
    "i8": 1, "u8": 1, "f16": 2, "bf16": 2, "i16": 2, "u16": 2,
    "f32": 4, "i32": 4, "u32": 4, "f64": 8, "i64": 8, "u64": 8,
}
MEMORY_LEVELS = ("register", "l1", "l2", "llc", "dram")


@dataclass(frozen=True)
class PipelineNode:
    id: str
    operator: str
    child_graph_hash: str
    semantic_contract: str
    profile_weight: float | None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineEdge:
    id: str
    src: str
    dst: str
    tensor: str
    element_type: str
    shape: tuple[Any, ...]
    layout: str
    stride: tuple[int, ...]
    alignment: int
    alias_set: str
    ownership: str
    lifetime: str
    observers: tuple[str, ...]
    materialization: str
    reuse_distance_bytes: int | None
    cache_target: str
    ordering: str
    numerical_contract: str
    logical_bytes: int


@dataclass(frozen=True)
class PipelineGraph:
    schema_version: str
    pipeline: str
    manifest_hash: str
    graph_hash: str
    nodes: tuple[PipelineNode, ...]
    edges: tuple[PipelineEdge, ...]
    annotations: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_pipeline_graph(path: Path) -> PipelineGraph:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("pipeline manifest root must be a mapping")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    manifest_hash = hashlib.sha256(canonical.encode()).hexdigest()
    required = {"pipeline", "nodes", "edges", "dimensions", "semantics", "objective", "constraints"}
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError("pipeline manifest missing: " + ", ".join(missing))
    dimensions = {str(key): int(value) for key, value in raw["dimensions"].items()}
    nodes = tuple(_parse_node(item) for item in raw["nodes"])
    node_ids = {node.id for node in nodes}
    errors: list[str] = []
    if len(node_ids) != len(nodes):
        errors.append("pipeline node ids must be unique")
    edges: list[PipelineEdge] = []
    edge_ids: set[str] = set()
    for item in raw["edges"]:
        try:
            edge = _parse_edge(item, dimensions)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"invalid edge {item.get('id', '<unknown>')}: {exc}")
            continue
        if edge.id in edge_ids:
            errors.append(f"duplicate edge id {edge.id}")
        edge_ids.add(edge.id)
        if edge.src not in node_ids or edge.dst not in node_ids:
            errors.append(f"edge {edge.id} references unknown node")
        if edge.materialization not in {"materialized", "streamed", "state", "external"}:
            errors.append(f"edge {edge.id} has invalid materialization")
        if edge.cache_target not in MEMORY_LEVELS:
            errors.append(f"edge {edge.id} has invalid cache target")
        if edge.materialization == "streamed" and any(observer not in {edge.dst, "internal"} for observer in edge.observers):
            errors.append(f"edge {edge.id} streams an externally observed tensor")
        if edge.materialization == "streamed" and edge.alias_set in {"unknown", "external"}:
            errors.append(f"edge {edge.id} streams with unresolved alias authority")
        edges.append(edge)
    stages = _topological_stages(nodes, tuple(edges))
    if stages is None:
        errors.append("pipeline data/control graph must be acyclic; state recurrences belong on state edges")
        stages = []
    if errors:
        raise ValueError("invalid PipelineGraph:\n- " + "\n- ".join(errors))
    lifetimes = _edge_lifetimes(stages, tuple(edges))
    traffic = estimate_information_movement(tuple(edges))
    live = _live_frontier(stages, tuple(edges), lifetimes)
    annotations = {
        "topological_stages": stages,
        "edge_lifetimes": lifetimes,
        "max_live_logical_bytes": max(live, default=0),
        "live_logical_bytes_by_stage": live,
        "critical_path_weight": _critical_path(nodes, tuple(edges)),
        "information_movement": traffic,
        "profile_weight_total": sum(node.profile_weight or 0.0 for node in nodes),
        "profile_weights_measured": bool(raw.get("profile", {}).get("measured", False)),
        "grammar_version": "pipeline-v4",
        "proof_status": "unverified",
    }
    provenance = {
        "manifest": str(path.resolve()),
        "manifest_hash": manifest_hash,
        "model": raw.get("model", {}),
        "target": raw.get("target", {}),
        "workload": raw.get("workload", {}),
        "semantics": raw["semantics"],
        "objective": raw["objective"],
        "constraints": raw["constraints"],
    }
    payload = {
        "schema_version": "pipeline-graph-v4.0",
        "pipeline": str(raw["pipeline"]),
        "manifest_hash": manifest_hash,
        "nodes": [asdict(node) for node in nodes],
        "edges": [asdict(edge) for edge in edges],
        "annotations": annotations,
        "provenance": provenance,
    }
    graph_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return PipelineGraph("pipeline-graph-v4.0", str(raw["pipeline"]), manifest_hash, graph_hash, nodes, tuple(edges), annotations, provenance)


def estimate_information_movement(edges: tuple[PipelineEdge, ...]) -> dict[str, Any]:
    modeled = {level: 0 for level in MEMORY_LEVELS}
    logical_materialized = logical_streamed = logical_external = 0
    for edge in edges:
        size = edge.logical_bytes
        if edge.materialization == "materialized":
            logical_materialized += size
            level = _residency_level(edge)
            modeled[level] += size * 2
            for slower in _slower_levels(level):
                modeled[slower] += size
        elif edge.materialization == "streamed":
            logical_streamed += size
            modeled["register"] += size
        elif edge.materialization == "external":
            logical_external += size
            modeled["dram"] += size
        elif edge.materialization == "state":
            modeled[_residency_level(edge)] += size
    return {
        "logical_tensor_bytes": sum(edge.logical_bytes for edge in edges),
        "logical_materialized_bytes": logical_materialized,
        "logical_streamed_bytes": logical_streamed,
        "logical_external_bytes": logical_external,
        "modeled_transfer_bytes": modeled,
        "measured_hardware_events": None,
        "model_uncertainty": "cache targets and reuse distance are pruning estimates, not measured residency",
    }


def write_pipeline_graph(path: Path, graph: PipelineGraph) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n")


def write_pipeline_dot(path: Path, graph: PipelineGraph, removed_edges: set[str] | None = None) -> None:
    removed_edges = removed_edges or set()
    lines = ["digraph PipelineGraph {", "  rankdir=LR;", "  node [shape=box];"]
    for node in graph.nodes:
        label = f"{node.id}\\n{node.operator}"
        lines.append(f'  "{node.id}" [label="{label}"];')
    colors = {"materialized": "#c43d3d", "streamed": "#2b7a4b", "state": "#8a5a00", "external": "#3a5f9e"}
    for edge in graph.edges:
        transformed = edge.id in removed_edges
        materialization = "streamed" if transformed else edge.materialization
        style = "dashed" if transformed else "solid"
        suffix = " (was materialized)" if transformed else ""
        label = f"{edge.tensor}\\n{materialization} {edge.logical_bytes}B{suffix}"
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{label}",color="{colors[materialization]}",style="{style}"];')
    lines.append("}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _parse_node(raw: dict[str, Any]) -> PipelineNode:
    return PipelineNode(
        id=str(raw["id"]), operator=str(raw["operator"]),
        child_graph_hash=str(raw.get("child_graph_hash", f"builtin:{raw['operator']}")),
        semantic_contract=str(raw.get("semantic_contract", f"builtin:{raw['operator']}")),
        profile_weight=float(raw["profile_weight"]) if raw.get("profile_weight") is not None else None,
        attrs=dict(raw.get("attrs", {})),
    )


def _parse_edge(raw: dict[str, Any], dimensions: dict[str, int]) -> PipelineEdge:
    shape = tuple(raw.get("shape", ()))
    count = 1
    for dim in shape:
        count *= dimensions[str(dim)] if isinstance(dim, str) else int(dim)
    element_type = str(raw["element_type"])
    if element_type not in ELEMENT_BYTES:
        raise ValueError(f"unsupported pipeline element type {element_type}")
    return PipelineEdge(
        id=str(raw["id"]), src=str(raw["src"]), dst=str(raw["dst"]), tensor=str(raw.get("tensor", raw["id"])),
        element_type=element_type, shape=shape, layout=str(raw.get("layout", "contiguous")),
        stride=tuple(int(value) for value in raw.get("stride", ())), alignment=int(raw.get("alignment", 1)),
        alias_set=str(raw.get("alias_set", "unknown")), ownership=str(raw.get("ownership", "pipeline")),
        lifetime=str(raw.get("lifetime", "pipeline")), observers=tuple(str(value) for value in raw.get("observers", (raw["dst"],))),
        materialization=str(raw.get("materialization", "materialized")),
        reuse_distance_bytes=int(raw["reuse_distance_bytes"]) if raw.get("reuse_distance_bytes") is not None else None,
        cache_target=str(raw.get("cache_target", "dram")), ordering=str(raw.get("ordering", "data")),
        numerical_contract=str(raw.get("numerical_contract", "exact")), logical_bytes=count * ELEMENT_BYTES[element_type],
    )


def _topological_stages(nodes: tuple[PipelineNode, ...], edges: tuple[PipelineEdge, ...]) -> list[list[str]] | None:
    indegree = {node.id: 0 for node in nodes}
    adjacency = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.ordering == "state_backedge":
            continue
        indegree[edge.dst] += 1
        adjacency[edge.src].append(edge.dst)
    current = sorted(node for node, degree in indegree.items() if degree == 0)
    stages: list[list[str]] = []
    visited = 0
    while current:
        stages.append(current)
        following: list[str] = []
        for node in current:
            visited += 1
            for dst in adjacency[node]:
                indegree[dst] -= 1
                if indegree[dst] == 0:
                    following.append(dst)
        current = sorted(following)
    return stages if visited == len(nodes) else None


def _edge_lifetimes(stages: list[list[str]], edges: tuple[PipelineEdge, ...]) -> dict[str, list[int]]:
    positions = {node: stage for stage, nodes in enumerate(stages) for node in nodes}
    return {edge.id: [positions[edge.src], positions[edge.dst]] for edge in edges}


def _live_frontier(stages: list[list[str]], edges: tuple[PipelineEdge, ...], lifetimes: dict[str, list[int]]) -> list[int]:
    return [sum(edge.logical_bytes for edge in edges if lifetimes[edge.id][0] <= stage <= lifetimes[edge.id][1]) for stage in range(len(stages))]


def _critical_path(nodes: tuple[PipelineNode, ...], edges: tuple[PipelineEdge, ...]) -> float:
    stages = _topological_stages(nodes, edges) or []
    by_id = {node.id: node for node in nodes}
    predecessors = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.ordering != "state_backedge":
            predecessors[edge.dst].append(edge.src)
    distance: dict[str, float] = {}
    for stage in stages:
        for node_id in stage:
            own = by_id[node_id].profile_weight or 1.0
            distance[node_id] = own + max((distance[pred] for pred in predecessors[node_id]), default=0.0)
    return max(distance.values(), default=0.0)


def _residency_level(edge: PipelineEdge) -> str:
    if edge.cache_target == "register" or edge.reuse_distance_bytes is None:
        return edge.cache_target
    capacities = {"l1": 32 * 1024, "l2": 1024 * 1024, "llc": 96 * 1024 * 1024, "dram": 1 << 62}
    for level in ("l1", "l2", "llc", "dram"):
        if edge.reuse_distance_bytes <= capacities[level]:
            return level
    return "dram"


def _slower_levels(level: str) -> tuple[str, ...]:
    if level == "register":
        return ()
    index = MEMORY_LEVELS.index(level)
    return MEMORY_LEVELS[index + 1:]
