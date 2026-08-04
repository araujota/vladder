from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


NODE_RE = re.compile(
    r'^\s*"(?P<ptr>0x[0-9a-f]+)".*label="(?P<name>.*?) \((?P<type>[^)]+)\)\|'
    r'(?P<index>\d+) \[(?P<shape>[^]]+)\] \| <x>(?P<op>[^"]+)"; ]$'
)
LEAF_RE = re.compile(
    r'^\s*"(?P<ptr>0x[0-9a-f]+)".*label="<x>(?P<name>.*?) \((?P<type>[^)]+)\)\|'
    r'CONST (?P<index>\d+) \[(?P<shape>[^]]+)\]'
)
EDGE_RE = re.compile(r'^\s*"(?P<src>0x[0-9a-f]+)" -> "(?P<dst>0x[0-9a-f]+)".*label = "src (?P<slot>\d+)"; ]$')
LAYER_RE = re.compile(r"(?:-|_l)(\d+)(?:\b| \()")


@dataclass(frozen=True)
class GGMLNode:
    id: str
    kind: str
    index: int
    name: str
    element_type: str
    shape: tuple[int, ...]
    op: str
    logical_bytes: int | None


@dataclass(frozen=True)
class GGMLEdge:
    src: str
    dst: str
    slot: int


@dataclass(frozen=True)
class NormalizedGGMLGraph:
    schema_version: str
    graph_hash: str
    nodes: tuple[GGMLNode, ...]
    edges: tuple[GGMLEdge, ...]
    annotations: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_ggml_dot(path: Path, provenance: dict[str, Any]) -> NormalizedGGMLGraph:
    pointers: dict[str, str] = {}
    nodes: list[GGMLNode] = []
    lines = path.read_text().splitlines()
    for line in lines:
        match = NODE_RE.match(line)
        kind = "compute"
        if match is None:
            match = LEAF_RE.match(line)
            kind = "leaf"
        if match is None:
            continue
        index = int(match.group("index"))
        stable_id = f"n{index}" if kind == "compute" else f"leaf{index}"
        pointers[match.group("ptr")] = stable_id
        shape = tuple(int(value.strip()) for value in match.group("shape").split(","))
        element_type = match.group("type")
        logical_bytes = _logical_bytes(element_type, shape)
        nodes.append(GGMLNode(stable_id, kind, index, match.group("name"), element_type, shape, match.groupdict().get("op") or "CONST", logical_bytes))
    edges: list[GGMLEdge] = []
    missing: list[str] = []
    for line in lines:
        match = EDGE_RE.match(line)
        if match is None:
            continue
        src = pointers.get(match.group("src"))
        dst = pointers.get(match.group("dst"))
        if src is None or dst is None:
            missing.append(f"{match.group('src')}->{match.group('dst')}")
            continue
        edges.append(GGMLEdge(src, dst, int(match.group("slot"))))
    if missing:
        raise ValueError(f"DOT edges reference {len(missing)} unparsed tensors")
    nodes.sort(key=lambda node: (node.kind != "compute", node.index, node.id))
    edges.sort(key=lambda edge: (edge.dst, edge.slot, edge.src))
    compute = [node for node in nodes if node.kind == "compute"]
    layer_nodes: dict[int, list[str]] = {}
    for node in compute:
        match = LAYER_RE.search(node.name)
        if match:
            layer_nodes.setdefault(int(match.group(1)), []).append(node.id)
    op_counts: dict[str, int] = {}
    for node in compute:
        op_counts[node.op] = op_counts.get(node.op, 0) + 1
    categories = _qwen_categories(compute)
    annotations = {
        "compute_node_count": len(compute),
        "leaf_count": len(nodes) - len(compute),
        "edge_count": len(edges),
        "operation_counts": dict(sorted(op_counts.items())),
        "layer_count": len(layer_nodes),
        "layer_node_counts": {str(layer): len(values) for layer, values in sorted(layer_nodes.items())},
        "qwen_pipeline_categories": categories,
        "v3_add_rms_mul_regions": _count_add_rms_mul(compute, edges),
        "logical_compute_tensor_bytes": sum(node.logical_bytes or 0 for node in compute),
        "traffic_class": "logical_only; views and allocator reuse are not physical transfers",
    }
    stable_provenance = {key: value for key, value in provenance.items() if key not in {"raw_dot_sha256", "raw_dot_path"}}
    payload = {
        "schema_version": "normalized-ggml-graph-v4.0",
        "nodes": [asdict(node) for node in nodes],
        "edges": [asdict(edge) for edge in edges],
        "annotations": annotations,
        "provenance": stable_provenance,
    }
    graph_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return NormalizedGGMLGraph("normalized-ggml-graph-v4.0", graph_hash, tuple(nodes), tuple(edges), annotations, provenance)


def write_normalized_ggml_graph(path: Path, graph: NormalizedGGMLGraph) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n")


def _logical_bytes(element_type: str, shape: tuple[int, ...]) -> int | None:
    sizes = {"f32": 4, "f16": 2, "bf16": 2, "i8": 1, "i16": 2, "i32": 4, "i64": 8}
    if element_type not in sizes:
        return None
    count = 1
    for dimension in shape:
        count *= dimension
    return count * sizes[element_type]


def _qwen_categories(nodes: list[GGMLNode]) -> dict[str, int]:
    categories = {
        "normalization": lambda node: node.op == "rms_norm(x)",
        "projection": lambda node: node.op == "X*Y",
        "rope": lambda node: node.op == "rope(x)",
        "attention": lambda node: node.op == "flash_attn_ext(x)",
        "residual": lambda node: node.op == "x+y",
        "activation": lambda node: node.op == "glu(x)",
        "kv_state_write": lambda node: node.op == "set_rows(x)",
        "layout_view": lambda node: node.op in {"view(x)", "reshape(x)", "permute(x)"},
        "elementwise_scale": lambda node: node.op == "x*y",
    }
    return {name: sum(1 for node in nodes if predicate(node)) for name, predicate in categories.items()}


def _count_add_rms_mul(nodes: list[GGMLNode], edges: list[GGMLEdge]) -> int:
    by_id = {node.id: node for node in nodes}
    consumers: dict[str, list[str]] = {}
    for edge in edges:
        consumers.setdefault(edge.src, []).append(edge.dst)
    count = 0
    for add in nodes:
        if add.op != "x+y":
            continue
        rms_consumers = [by_id[item] for item in consumers.get(add.id, []) if item in by_id and by_id[item].op == "rms_norm(x)"]
        for rms in rms_consumers:
            if any(item in by_id and by_id[item].op == "x*y" for item in consumers.get(rms.id, [])):
                count += 1
    return count
