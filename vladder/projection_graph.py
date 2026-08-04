from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


NODE_KINDS = {
    "ActivationSource", "Normalize", "ActivationPack", "ActivationQuantize",
    "WeightBlockLoad", "WeightBlockDecode", "ScaleDecode", "DotAccumulate",
    "AccumulatorReduce", "Bias", "Residual", "Gate", "ActivationFunction",
    "OutputConvert", "OutputTile", "ProjectionConsumer", "KVWrite",
    "Materialize", "Dispatch",
}


@dataclass(frozen=True)
class ProjectionNode:
    id: str
    kind: str
    attrs: dict[str, Any]


@dataclass(frozen=True)
class ProjectionEdge:
    id: str
    src: str
    dst: str
    shape: tuple[int, ...]
    token_count: int
    sequence_count: int
    quantization: str
    block_dimensions: tuple[int, ...]
    element_type: str
    alignment: int
    stride: tuple[int, ...]
    layout: str
    memory_region: str
    expected_reuse: int
    producer_tile: tuple[int, ...]
    consumer_tile: tuple[int, ...]
    alias_set: str
    lifetime: str
    max_abs_error: float
    logical_bytes: int
    role: str


@dataclass(frozen=True)
class ProjectionComplexGraph:
    schema_version: str
    complex: str
    manifest_hash: str
    graph_hash: str
    nodes: tuple[ProjectionNode, ...]
    edges: tuple[ProjectionEdge, ...]
    annotations: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_projection_graph(path: Path) -> ProjectionComplexGraph:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("projection manifest root must be a mapping")
    required = {"complex", "dimensions", "regime", "semantics", "nodes", "edges", "objective", "constraints"}
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError("projection manifest missing: " + ", ".join(missing))
    dimensions = {str(key): int(value) for key, value in raw["dimensions"].items()}
    regime = raw["regime"]
    token_count = int(regime["token_count"])
    sequence_count = int(regime["sequence_count"])
    if token_count < 1 or sequence_count < 1:
        raise ValueError("token_count and sequence_count must be positive")
    nodes = tuple(_node(item) for item in raw["nodes"])
    ids = {node.id for node in nodes}
    if len(ids) != len(nodes):
        raise ValueError("projection node ids must be unique")
    errors: list[str] = []
    edges: list[ProjectionEdge] = []
    edge_ids: set[str] = set()
    for item in raw["edges"]:
        try:
            edge = _edge(item, dimensions, token_count, sequence_count)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"invalid edge {item.get('id', '<unknown>')}: {exc}")
            continue
        if edge.id in edge_ids:
            errors.append(f"duplicate edge {edge.id}")
        edge_ids.add(edge.id)
        if edge.src not in ids or edge.dst not in ids:
            errors.append(f"edge {edge.id} references unknown node")
        if edge.quantization == "unknown":
            errors.append(f"edge {edge.id} has unresolved quantization")
        if edge.alias_set in {"unknown", "external-unknown"}:
            errors.append(f"edge {edge.id} has unresolved alias authority")
        if edge.producer_tile and edge.consumer_tile and edge.producer_tile != edge.consumer_tile:
            errors.append(f"edge {edge.id} has incompatible producer/consumer tiles")
        edges.append(edge)
    _acyclic(nodes, edges, errors)
    if errors:
        raise ValueError("; ".join(errors))
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    manifest_hash = hashlib.sha256(canonical.encode()).hexdigest()
    costs = projection_costs(tuple(edges), raw)
    graph_content = {
        "complex": raw["complex"], "nodes": [asdict(node) for node in nodes],
        "edges": [asdict(edge) for edge in edges], "semantics": raw["semantics"],
        "regime": regime, "bindings": raw.get("bindings", {}),
    }
    graph_hash = hashlib.sha256(json.dumps(graph_content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    annotations = {
        "cost": costs,
        "shared_activation_fanout": _shared_fanout(nodes, edges),
        "projection_count": sum(node.kind == "DotAccumulate" for node in nodes),
        "topological_order": _topological(nodes, edges),
        "measured_regional_runtime_share": raw.get("measured_regional_runtime_share"),
    }
    provenance = {
        "dimensions": dimensions, "regime": regime, "semantics": raw["semantics"],
        "objective": raw["objective"], "constraints": raw["constraints"],
        "bindings": raw.get("bindings", {}), "source_manifest": str(path),
    }
    return ProjectionComplexGraph("vladder-projection-v5.0", str(raw["complex"]), manifest_hash, graph_hash, nodes, tuple(edges), annotations, provenance)


def projection_costs(edges: tuple[ProjectionEdge, ...], raw: dict[str, Any]) -> dict[str, Any]:
    by_role: dict[str, int] = {}
    for edge in edges:
        by_role[edge.role] = by_role.get(edge.role, 0) + edge.logical_bytes
    macs = int(raw.get("useful_macs", 0))
    weight = by_role.get("weight", 0)
    activation = by_role.get("activation", 0)
    temporary = by_role.get("temporary", 0)
    metadata = by_role.get("metadata", 0)
    traffic = weight + activation + 2 * temporary + metadata
    return {
        "weight_bytes_read": weight,
        "activation_bytes_read": activation,
        "temporary_bytes_written_read": 2 * temporary,
        "quantization_metadata_bytes": metadata,
        "useful_macs": macs,
        "estimated_arithmetic_intensity_mac_per_byte": macs / traffic if traffic else None,
        "output_materialization_count": sum(edge.role == "temporary" for edge in edges),
        "synchronization_count": int(raw.get("synchronization_count", 0)),
        "cache_line_reuse_estimate": sum(max(0, edge.expected_reuse - 1) * edge.logical_bytes for edge in edges),
    }


def emit_projection_dot(graph: ProjectionComplexGraph) -> str:
    lines = ["digraph ProjectionComplexGraph {", "  rankdir=LR;"]
    for node in graph.nodes:
        lines.append(f'  "{node.id}" [label="{node.id}\\n{node.kind}"];')
    for edge in graph.edges:
        label = f"{edge.id}\\n{edge.quantization} {edge.layout}\\n{edge.logical_bytes} B"
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{label}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def _node(item: dict[str, Any]) -> ProjectionNode:
    kind = str(item["kind"])
    if kind not in NODE_KINDS:
        raise ValueError(f"unsupported projection node kind {kind}")
    return ProjectionNode(str(item["id"]), kind, dict(item.get("attrs", {})))


def _edge(item: dict[str, Any], dimensions: dict[str, int], token_count: int, sequence_count: int) -> ProjectionEdge:
    shape = tuple(_dimension(value, dimensions) for value in item["shape"])
    block = tuple(int(value) for value in item.get("block_dimensions", []))
    producer_tile = tuple(int(value) for value in item.get("producer_tile", []))
    consumer_tile = tuple(int(value) for value in item.get("consumer_tile", []))
    logical_bytes = int(item["logical_bytes"]) if "logical_bytes" in item else _tensor_bytes(shape, str(item["element_type"]))
    return ProjectionEdge(
        str(item["id"]), str(item["src"]), str(item["dst"]), shape,
        int(item.get("token_count", token_count)), int(item.get("sequence_count", sequence_count)),
        str(item["quantization"]), block, str(item["element_type"]), int(item.get("alignment", 1)),
        tuple(int(value) for value in item.get("stride", [])), str(item["layout"]),
        str(item["memory_region"]), int(item.get("expected_reuse", 1)), producer_tile,
        consumer_tile, str(item["alias_set"]), str(item["lifetime"]),
        float(item.get("max_abs_error", 0.0)), logical_bytes, str(item["role"]),
    )


def _dimension(value: Any, dimensions: dict[str, int]) -> int:
    if isinstance(value, int):
        return value
    if str(value) not in dimensions:
        raise ValueError(f"unresolved dimension {value}")
    return dimensions[str(value)]


def _tensor_bytes(shape: tuple[int, ...], element_type: str) -> int:
    sizes = {"f32": 4, "f16": 2, "bf16": 2, "q8_k": 0}
    if element_type not in sizes or sizes[element_type] == 0:
        raise ValueError(f"logical_bytes required for {element_type}")
    count = 1
    for value in shape:
        count *= value
    return count * sizes[element_type]


def _topological(nodes: tuple[ProjectionNode, ...], edges: list[ProjectionEdge]) -> list[str]:
    incoming = {node.id: 0 for node in nodes}
    outgoing = {node.id: [] for node in nodes}
    for edge in edges:
        incoming[edge.dst] += 1
        outgoing[edge.src].append(edge.dst)
    ready = sorted(node for node, degree in incoming.items() if degree == 0)
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for target in sorted(outgoing[node]):
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
                ready.sort()
    return order


def _acyclic(nodes: tuple[ProjectionNode, ...], edges: list[ProjectionEdge], errors: list[str]) -> None:
    if len(_topological(nodes, edges)) != len(nodes):
        errors.append("projection graph must be acyclic")


def _shared_fanout(nodes: tuple[ProjectionNode, ...], edges: list[ProjectionEdge]) -> int:
    kinds = {node.id: node.kind for node in nodes}
    sources = [node.id for node in nodes if node.kind in {"ActivationSource", "ActivationPack", "ActivationQuantize", "Normalize"}]
    return max((sum(edge.src == source and kinds.get(edge.dst) in {"DotAccumulate", "ActivationPack", "ActivationQuantize"} for edge in edges) for source in sources), default=0)
