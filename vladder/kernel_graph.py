from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from .projection_graph import ProjectionComplexGraph


KERNEL_NODE_KINDS = {
    "ActivationLoad", "ActivationPack", "ActivationQuantize", "WeightBlockLoad", "MetadataDecode",
    "BlockDecode", "DotProduct", "AccumulatorBank", "PartialReduction", "OutputTransform", "Consumer",
    "Materialize", "Dispatch",
}


@dataclass(frozen=True)
class KernelNode:
    id: str
    kind: str
    attrs: dict[str, Any]


@dataclass(frozen=True)
class KernelEdge:
    id: str
    src: str
    dst: str
    element_type: str
    shape: tuple[int, ...]
    quantization: str
    block_size: int
    alignment: int
    alias_set: str
    lifetime: str
    ownership: str
    cache_residency: str
    expected_reuse: int
    numerical_contract: str
    logical_bytes: int


@dataclass(frozen=True)
class KernelGraph:
    schema_version: str
    id: str
    graph_hash: str
    source_graph_hash: str
    nodes: tuple[KernelNode, ...]
    edges: tuple[KernelEdge, ...]
    annotations: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def kernel_graph_from_projection(graph: ProjectionComplexGraph) -> KernelGraph:
    projection_kinds = {node.id: node.kind for node in graph.nodes}
    nodes: list[KernelNode] = []
    edges: list[KernelEdge] = []
    for node in graph.nodes:
        mapped = _map_kind(node.kind)
        if mapped is not None:
            nodes.append(KernelNode(node.id, mapped, dict(node.attrs)))
    nodes.append(KernelNode("runtime_dispatch", "Dispatch", {
        "required_guards": ["phase", "token_count", "sequence_count", "context", "isa", "alignment", "kv_occupancy"],
        "fallback": "pinned_native_kernel",
    }))
    present = {node.id for node in nodes}
    for edge in graph.edges:
        if edge.src not in present:
            nodes.append(KernelNode(edge.src, _boundary_kind(projection_kinds[edge.src], source=True), {"boundary": True}))
            present.add(edge.src)
        if edge.dst not in present:
            nodes.append(KernelNode(edge.dst, _boundary_kind(projection_kinds[edge.dst], source=False), {"boundary": True}))
            present.add(edge.dst)
        edges.append(KernelEdge(
            edge.id, edge.src, edge.dst, edge.element_type, edge.shape, edge.quantization,
            edge.block_dimensions[0] if edge.block_dimensions else 1, edge.alignment, edge.alias_set,
            edge.lifetime, "complex-owned", edge.memory_region, edge.expected_reuse,
            "exact" if edge.max_abs_error == 0.0 else f"max_abs_error={edge.max_abs_error}", edge.logical_bytes,
        ))
    _validate(tuple(nodes), tuple(edges))
    weight_bytes = sum(edge.logical_bytes for edge in edges if "weight" in edge.id or edge.quantization.startswith("q4"))
    payload = {
        "source": graph.graph_hash,
        "nodes": [asdict(node) for node in nodes],
        "edges": [asdict(edge) for edge in edges],
    }
    graph_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return KernelGraph(
        "vladder-kernel-graph-v6.0", graph.complex, graph_hash, graph.graph_hash, tuple(nodes), tuple(edges),
        {
            "weight_bytes": weight_bytes,
            "logical_bytes": sum(edge.logical_bytes for edge in edges),
            "expected_weight_reuse": max((edge.expected_reuse for edge in edges if edge.quantization.startswith("q")), default=1),
            "source_projection_count": graph.annotations["projection_count"],
            "source_cost": graph.annotations["cost"],
            "runtime_regime": graph.provenance["regime"],
        },
    )


def _map_kind(kind: str) -> str | None:
    return {
        "ActivationSource": "ActivationLoad", "ActivationPack": "ActivationPack",
        "ActivationQuantize": "ActivationQuantize", "WeightBlockLoad": "WeightBlockLoad",
        "WeightBlockDecode": "BlockDecode", "ScaleDecode": "MetadataDecode",
        "DotAccumulate": "DotProduct", "AccumulatorReduce": "PartialReduction",
        "OutputConvert": "OutputTransform", "ProjectionConsumer": "Consumer",
        "Materialize": "Materialize", "Dispatch": "Dispatch",
    }.get(kind)


def _boundary_kind(kind: str, *, source: bool) -> str:
    if source:
        return "ActivationLoad"
    if kind in {"OutputTile", "Gate", "ActivationFunction", "Residual", "Bias", "KVWrite"}:
        return "Consumer"
    return "OutputTransform"


def _validate(nodes: tuple[KernelNode, ...], edges: tuple[KernelEdge, ...]) -> None:
    ids = [node.id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("kernel node ids must be unique")
    unknown = [node.kind for node in nodes if node.kind not in KERNEL_NODE_KINDS]
    if unknown:
        raise ValueError("unsupported kernel node kinds: " + ", ".join(sorted(set(unknown))))
    node_ids = set(ids)
    for edge in edges:
        if edge.src not in node_ids or edge.dst not in node_ids:
            raise ValueError(f"kernel edge {edge.id} references unknown node")
        if edge.alignment < 1 or edge.block_size < 1 or edge.logical_bytes < 0:
            raise ValueError(f"kernel edge {edge.id} has invalid physical metadata")
