from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


NODE_KINDS = {
    "WeightBlockLoad", "WeightMetadataDecode", "ActivationTile", "TokenLane",
    "SequenceLane", "ProjectionConsumer", "AccumulatorBank", "ConsumerBarrier",
    "Commit", "Rollback", "Dispatch", "WeightTraversalEnd",
}


@dataclass(frozen=True)
class WeightTraversalNode:
    id: str
    kind: str
    attrs: dict[str, Any]
    provenance: str
    semantic_obligation: str


@dataclass(frozen=True)
class WeightTraversalEdge:
    id: str
    src: str
    dst: str
    role: str
    weight_bytes: int
    activation_bytes: int
    useful_macs: int
    token_lane: int | None
    sequence_lane: int | None
    ownership: str
    ordering: str
    exactness: str


@dataclass(frozen=True)
class WeightTraversalGraph:
    schema_version: str
    name: str
    manifest_hash: str
    graph_hash: str
    nodes: tuple[WeightTraversalNode, ...]
    edges: tuple[WeightTraversalEdge, ...]
    contract: dict[str, Any]
    grammar: dict[str, tuple[Any, ...]]
    portfolio: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_weight_traversal_graph(path: Path) -> WeightTraversalGraph:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("weight traversal manifest root must be a mapping")
    required = {"name", "model", "target", "kernel", "semantics", "grammar", "portfolio", "constraints"}
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError("weight traversal manifest missing: " + ", ".join(missing))
    grammar = _grammar(raw["grammar"])
    portfolio = _portfolio(raw["portfolio"])
    semantics = raw["semantics"]
    if semantics.get("weight_format") != "Q4_K" or semantics.get("activation_format") != "Q8_K":
        raise ValueError("V9 production track requires Q4_K x Q8_K")
    if semantics.get("numerical_contract") != "E1":
        raise ValueError("V9 primary track requires E1 semantics")
    if semantics.get("allocation") != "forbidden_hot_path":
        raise ValueError("hot-path allocation must be forbidden")
    constraints = raw["constraints"]
    if float(constraints.get("interactive_min_relative_performance", 0.0)) < 0.99:
        raise ValueError("interactive floor must be at least 0.99")
    nodes, edges = _build_nodes_edges(raw, grammar)
    _validate_graph(nodes, edges)
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    manifest_hash = hashlib.sha256(canonical.encode()).hexdigest()
    graph_payload = {
        "nodes": [asdict(item) for item in nodes], "edges": [asdict(item) for item in edges],
        "semantics": semantics, "grammar": grammar, "portfolio": portfolio,
    }
    graph_hash = hashlib.sha256(json.dumps(graph_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return WeightTraversalGraph(
        "vladder-weight-traversal-graph-v9.0", str(raw["name"]), manifest_hash,
        graph_hash, nodes, edges, dict(semantics), grammar, portfolio,
        {"manifest": str(path.resolve()), "model": raw["model"], "target": raw["target"],
         "kernel": raw["kernel"], "constraints": constraints},
    )


def emit_weight_traversal_dot(graph: WeightTraversalGraph) -> str:
    lines = ["digraph WeightTraversalGraph {", "  rankdir=LR;"]
    for node in graph.nodes:
        lines.append(f'  "{node.id}" [label="{node.id}\\n{node.kind}"];')
    for edge in graph.edges:
        label = f"{edge.role}\\nW={edge.weight_bytes} A={edge.activation_bytes} MAC={edge.useful_macs}"
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{label}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def _grammar(raw: Any) -> dict[str, tuple[Any, ...]]:
    if not isinstance(raw, dict):
        raise ValueError("grammar must be a mapping")
    required = {
        "token_tiles", "sequence_tiles", "projection_sharing", "traversals",
        "runtime_policies", "speculative",
    }
    if set(raw) != required:
        raise ValueError("V9 grammar must contain exactly: " + ", ".join(sorted(required)))
    grammar = {key: tuple(value) for key, value in raw.items()}
    if grammar["token_tiles"] != (1, 2, 4, 8, 16):
        raise ValueError("token tile grammar must be 1,2,4,8,16")
    if grammar["sequence_tiles"] != (1, 2, 4, 8):
        raise ValueError("sequence tile grammar must be 1,2,4,8")
    return grammar


def _portfolio(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("portfolio must be a non-empty mapping")
    total = sum(float(item["weight"]) for item in raw.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError("portfolio weights must sum to one")
    required = {"interactive", "prompt", "concurrent", "kv_pressure"}
    if set(raw) != required:
        raise ValueError("portfolio requires interactive, prompt, concurrent, and kv_pressure")
    return {str(key): dict(value) for key, value in raw.items()}


def _build_nodes_edges(raw: dict[str, Any], grammar: dict[str, tuple[Any, ...]]) -> tuple[tuple[WeightTraversalNode, ...], tuple[WeightTraversalEdge, ...]]:
    kernel = raw["kernel"]
    model = raw["model"]
    input_size = int(kernel["input_dimension"])
    output_size = int(kernel["output_dimension"])
    weight_bytes = int(kernel["regional_weight_bytes"])
    macs = input_size * output_size
    nodes = [
        WeightTraversalNode("dispatch", "Dispatch", {"guards": ["phase", "ready_sequences", "queue_depth", "kv_occupancy"]}, "llama runtime batch boundary", "dispatch guard preserves lane membership"),
        WeightTraversalNode("weight", "WeightBlockLoad", {"format": "Q4_K", "bytes": weight_bytes}, "V8 representation accounting", "each required block is visited once per traversal"),
        WeightTraversalNode("metadata", "WeightMetadataDecode", {"format": "Q4_K-scale-min"}, "active Q4_K kernel", "metadata remains associated with its packed values"),
        WeightTraversalNode("activation", "ActivationTile", {"format": "Q8_K", "max_token_tile": max(grammar["token_tiles"])}, "llama repack activation plane", "one exact activation row per admitted lane"),
        WeightTraversalNode("token", "TokenLane", {"tiles": grammar["token_tiles"]}, "V9 grammar", "autoregressive future lanes require tentative state"),
        WeightTraversalNode("sequence", "SequenceLane", {"tiles": grammar["sequence_tiles"]}, "llama sequence ids", "sequence-owned state remains isolated"),
        WeightTraversalNode("accumulator", "AccumulatorBank", {"kernel_fixed": True}, "native GEMV/GEMM", "independent output accumulator per lane"),
        WeightTraversalNode("consumer", "ProjectionConsumer", {"groups": grammar["projection_sharing"]}, "projection graph boundary", "consumer observes its original lane output"),
        WeightTraversalNode("barrier", "ConsumerBarrier", {"scope": "batch"}, "llama synchronize boundary", "all outputs complete before state commit"),
        WeightTraversalNode("commit", "Commit", {"state": ["KV", "sequence_position"]}, "llama memory ownership", "accepted lanes commit in sequence order"),
        WeightTraversalNode("rollback", "Rollback", {"enabled": True}, "speculative grammar", "rejected tentative writes remain unobservable"),
        WeightTraversalNode("end", "WeightTraversalEnd", {"model_weight_bytes": int(model["size_bytes"])}, "V9 accounting boundary", "all consumers complete before traversal ends"),
    ]
    chain = ["dispatch", "weight", "metadata", "activation", "token", "sequence", "accumulator", "consumer", "barrier", "commit", "end"]
    edges = []
    for index, (src, dst) in enumerate(zip(chain, chain[1:])):
        edges.append(WeightTraversalEdge(
            f"e{index}", src, dst, "weight" if src in {"weight", "metadata"} else "activation" if src == "activation" else "control",
            weight_bytes if src == "weight" else 0, input_size * 4 if src == "activation" else 0,
            macs if src == "accumulator" else 0, None, None, "sequence-local" if src in {"sequence", "accumulator", "consumer"} else "shared-read-only",
            "program-order", "E1",
        ))
    edges.append(WeightTraversalEdge("rollback_edge", "barrier", "rollback", "tentative-control", 0, 0, 0, None, None, "sequence-local", "verification-before-commit", "E1"))
    edges.append(WeightTraversalEdge("rollback_end", "rollback", "end", "control", 0, 0, 0, None, None, "sequence-local", "rollback-before-end", "E1"))
    return tuple(nodes), tuple(edges)


def _validate_graph(nodes: tuple[WeightTraversalNode, ...], edges: tuple[WeightTraversalEdge, ...]) -> None:
    ids = {item.id for item in nodes}
    if len(ids) != len(nodes):
        raise ValueError("weight traversal node ids must be unique")
    kinds = {item.kind for item in nodes}
    if kinds != NODE_KINDS:
        raise ValueError("weight traversal graph must instantiate every V9 node kind")
    if any(edge.src not in ids or edge.dst not in ids for edge in edges):
        raise ValueError("weight traversal edge references unknown node")
    if any(edge.exactness != "E1" for edge in edges):
        raise ValueError("V9 primary graph edges must retain E1")
