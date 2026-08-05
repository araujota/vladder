from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

from .language_adapter import SemanticFlowEdge, SemanticFlowGraph, SemanticFlowNode, canonical_hash, obligation


DEEP_GRAPH_SCHEMA_VERSION = "vladder-deep-realization-graph-v1"
SUPPORTED_ARCHETYPES = frozenset({"exact-byte-predicate-reduction"})
SUPPORTED_PREDICATES = frozenset({"equal-u8", "utf8-leading-byte"})


@dataclass(frozen=True)
class ComplexityModel:
    asymptotic_work: str
    passes: int
    logical_bytes_per_element: float
    temporary_bytes_per_element: float
    scalar_operations_per_element: float
    useful_lanes_per_load: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeepKernelContract:
    archetype: str
    predicate: str
    element_bits: int = 8
    accumulator_bits: int = 64
    exact: bool = True
    allocation: str = "forbidden"
    input_min: int = 0
    input_max: int = 1 << 30
    target_isa: tuple[str, ...] = ("scalar", "avx2")

    def __post_init__(self) -> None:
        if self.archetype not in SUPPORTED_ARCHETYPES:
            raise ValueError(f"unsupported deep-kernel archetype: {self.archetype}")
        if self.predicate not in SUPPORTED_PREDICATES:
            raise ValueError(f"unsupported byte predicate: {self.predicate}")
        if self.element_bits != 8:
            raise ValueError("deep-v2 byte predicate reductions require 8-bit elements")
        if self.accumulator_bits not in {32, 64}:
            raise ValueError("deep-v2 requires a 32- or 64-bit exact accumulator")
        if self.input_min < 0 or self.input_max < self.input_min:
            raise ValueError("invalid input bounds")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "target_isa": list(self.target_isa)}


@dataclass(frozen=True)
class DeepRealizationGraph:
    realization: str
    semantic_graph: SemanticFlowGraph
    complexity: ComplexityModel
    terminal: bool
    graph_hash: str
    semantic_shape_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DEEP_GRAPH_SCHEMA_VERSION,
            "realization": self.realization,
            "terminal": self.terminal,
            "complexity": self.complexity.to_dict(),
            "semantic_graph": self.semantic_graph.to_dict(),
            "semantic_shape_hash": self.semantic_shape_hash,
            "graph_hash": self.graph_hash,
        }


@dataclass(frozen=True)
class SourceRealization:
    language: str
    function: str
    archetype: str | None
    predicate: str | None
    realization: str | None
    evidence: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def representable(self) -> bool:
        return self.archetype in SUPPORTED_ARCHETYPES and self.predicate in SUPPORTED_PREDICATES and self.realization is not None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "representable": self.representable}


def _node(
    node_id: str,
    kind: str,
    operation: str,
    inputs: tuple[str, ...],
    output_type: str | None,
    *,
    realization: str,
    obligations: tuple[str, ...] = (),
    **attributes: Any,
) -> SemanticFlowNode:
    categories = {
        "object-bounds": "bounds", "unaligned-load-legality": "memory",
        "word-equality-identity": "representation", "lane-predicate": "representation",
        "pack-bijection": "representation", "mask-population": "representation",
        "bounded-lane-accumulator": "numeric", "reduction-equivalence": "numeric",
        "no-overflow": "numeric", "tail-partition": "bounds", "footprint-coverage": "bounds",
        "no-intermediate-observer": "representation", "guard-completeness": "dispatch",
        "fallback-equivalence": "dispatch", "observable-equivalence": "validation",
    }
    typed_obligations = tuple(
        obligation(
            f"deep.{node_id}.{item}",
            categories.get(item, "validation"),
            item.replace("-", " "),
            proof_method="deep-v2-proof-registry",
            native_construct=operation,
        )
        for item in obligations
    )
    return SemanticFlowNode(
        node_id,
        kind,
        operation,
        inputs,
        output_type,
        {"realization": realization, **attributes},
        {"adapter": "deep-v2", "semantic_source": "exact-byte-predicate-reduction"},
        typed_obligations,
    )


def _edge(
    edge_id: str,
    source: str,
    destination: str,
    value_type: str,
    *,
    realization: str,
    logical_shape: tuple[int | str, ...] = (),
    physical_shape: tuple[int | str, ...] = (),
    lane_width_bits: int | None = None,
    vector_width_bits: int | None = None,
    memory_region: str = "register",
) -> SemanticFlowEdge:
    return SemanticFlowEdge(
        edge_id,
        source,
        destination,
        value_type,
        "borrowed" if memory_region == "input" else "ephemeral",
        "input" if memory_region == "input" else "none",
        "kernel-call",
        "program-order",
        logical_shape,
        physical_shape,
        lane_width_bits,
        vector_width_bits,
        realization,
        memory_region,
        "kernel-call",
    )


def _realization_properties(realization: str) -> tuple[int, str, bool, bool, bool]:
    if realization == "scalar":
        return 1, "scalar", False, False, False
    word = realization.startswith("word")
    vector = realization.startswith("simd") or realization.startswith("guarded")
    mask_popcount = "mask-popcount" in realization or realization == "guarded-avx2"
    byte_accumulate = "byte" in realization
    if word:
        return 8, "word", True, True, False
    if vector:
        return 32, "simd", True, mask_popcount, byte_accumulate
    # Intermediate derivation states retain the physical direction in their names.
    if realization.startswith("word"):
        return 8, "word", True, "mask" in realization or "reduced" in realization, False
    if realization.startswith("simd"):
        return 32, "simd", True, "mask" in realization or "popcount" in realization, "byte" in realization
    return 1, "scalar", False, False, False


def build_deep_realization_graph(
    contract: DeepKernelContract,
    realization: str,
    *,
    source_language: str = "language-neutral",
    compiler_identity: str = "unlowered",
    function_identity: str = "count_bytes",
    terminal: bool = True,
) -> DeepRealizationGraph:
    lanes, physical_kind, wide, mask_popcount, byte_accumulate = _realization_properties(realization)
    vector_bits = lanes * contract.element_bits if lanes > 1 else None
    nodes: list[SemanticFlowNode] = [
        _node("input.bytes", "Input", "byte-stream", (), "slice<u8>", realization=realization, role="authoritative-input"),
        _node("input.predicate", "Input", contract.predicate, (), "u8", realization=realization, role="predicate-parameter"),
        _node("loop", "Loop", "contiguous-forward-traversal", ("input.bytes",), "index", realization=realization, step=lanes),
        _node(
            "load",
            "Load",
            f"load-{physical_kind}",
            ("input.bytes", "loop"),
            f"u8x{lanes}" if lanes > 1 else "u8",
            realization=realization,
            obligations=("object-bounds", "unaligned-load-legality") if wide else ("object-bounds",),
            lanes=lanes,
        ),
    ]
    if wide:
        nodes.append(_node("broadcast", "Broadcast", "predicate-splat", ("input.predicate",), f"u8x{lanes}", realization=realization, lanes=lanes))
    compare_input = ("load", "broadcast") if wide else ("load", "input.predicate")
    if physical_kind == "word":
        nodes.append(_node("predicate", "Bitwise", "xor-zero-byte-equality", compare_input, f"maskx{lanes}", realization=realization, obligations=("word-equality-identity",)))
    else:
        nodes.append(_node("predicate", "LaneMap", contract.predicate, compare_input, f"boolx{lanes}", realization=realization, obligations=("lane-predicate",)))
    if wide:
        nodes.append(_node("pack", "Pack", "lane-pack", ("predicate",), f"lanesx{lanes}", realization=realization, obligations=("pack-bijection",)))
        nodes.append(_node("mask", "MaskExtract" if mask_popcount else "Mask", "extract-lane-mask" if mask_popcount else "lane-byte-mask", ("pack",), f"mask{lanes}", realization=realization, obligations=("mask-population",)))
    reduction_input = "predicate"
    if wide and mask_popcount:
        nodes.append(_node("population", "PopulationCount", "population-count", ("mask",), "usize", realization=realization, obligations=("mask-population",)))
        reduction_input = "population"
    elif wide and byte_accumulate:
        nodes.append(_node("lane_accumulators", "Reduce", "bounded-lane-byte-accumulate", ("mask",), f"u8x{lanes}", realization=realization, obligations=("bounded-lane-accumulator",), flush_period=255))
        reduction_input = "lane_accumulators"
    elif wide:
        reduction_input = "mask"
    nodes.append(_node("reduce", "HorizontalReduce" if wide else "Reduce", "exact-add", (reduction_input,), "usize", realization=realization, obligations=("reduction-equivalence", "no-overflow")))
    nodes.append(_node("tail", "Tail", "scalar-remainder", ("input.bytes", "loop", "reduce"), "usize", realization=realization, obligations=("tail-partition", "footprint-coverage"), maximum_lanes=max(0, lanes - 1)))
    nodes.append(_node("fuse", "Fuse", "predicate-reduction-fusion", ("load", "predicate", "reduce", "tail"), "usize", realization=realization, obligations=("no-intermediate-observer",)))
    if realization.startswith("guarded"):
        nodes.extend([
            _node("guard", "Guard", "target-feature-avx2", (), "bool", realization=realization, obligations=("guard-completeness",)),
            _node("dispatch", "Dispatch", "avx2-or-scalar", ("guard", "fuse"), "usize", realization=realization, obligations=("fallback-equivalence",)),
        ])
        output_input = "dispatch"
    else:
        output_input = "fuse"
    complexity = ComplexityModel(
        "O(n)",
        1,
        1.0,
        0.0,
        3.0 if lanes == 1 else (1.0 if physical_kind == "word" else 0.25),
        lanes,
    )
    nodes.extend([
        _node("complexity", "ComplexityBound", "linear-single-pass", (output_input,), "contract", realization=realization, work="O(n)", passes=1, logical_bytes_per_element=1),
        _node("output", "Output", "exact-count", (output_input,), "usize", realization=realization, obligations=("observable-equivalence",)),
    ])

    edges: list[SemanticFlowEdge] = []
    for node in nodes:
        for ordinal, dependency in enumerate(node.inputs):
            edges.append(_edge(
                f"{dependency}->{node.id}:{ordinal}",
                dependency,
                node.id,
                node.output_type or "control",
                realization=realization,
                logical_shape=("n",),
                physical_shape=(lanes,),
                lane_width_bits=contract.element_bits if lanes > 1 else None,
                vector_width_bits=vector_bits,
                memory_region="input" if dependency == "input.bytes" else "register",
            ))
    graph = SemanticFlowGraph(
        f"{contract.archetype}:{contract.predicate}:{realization}",
        source_language,
        compiler_identity,
        "deep-realization-v2",
        function_identity,
        tuple(nodes),
        tuple(edges),
        contract.to_dict(),
        ("language ownership and external protocols", "whole-program equivalence"),
    )
    shape_payload = {
        "archetype": contract.archetype,
        "predicate": contract.predicate,
        "realization": realization,
        "nodes": [(
            node.kind,
            node.operation,
            node.output_type,
            sorted((item.id, item.category, item.statement) for item in node.semantic_obligations),
        ) for node in nodes],
        "edges": [(edge.source, edge.destination, edge.value_type, edge.logical_shape, edge.physical_shape) for edge in edges],
        "complexity": complexity.to_dict(),
    }
    semantic_shape_hash = canonical_hash(shape_payload)
    payload = {
        "schema_version": DEEP_GRAPH_SCHEMA_VERSION,
        "realization": realization,
        "terminal": terminal,
        "semantic_graph_hash": graph.graph_hash,
        "semantic_shape_hash": semantic_shape_hash,
        "complexity": complexity.to_dict(),
    }
    return DeepRealizationGraph(realization, graph, complexity, terminal, canonical_hash(payload), semantic_shape_hash)


def inspect_source_realization(source: str, language: str, function: str) -> SourceRealization:
    normalized = re.sub(r"\s+", " ", source)
    evidence: list[str] = []
    blockers: list[str] = []
    if language not in {"c", "cpp", "rust", "zig", "julia"}:
        blockers.append(f"unsupported source language: {language}")
    predicate: str | None = None
    utf8_shift_predicate = bool(re.search(
        r"(?:\*?\s*[A-Za-z_][A-Za-z0-9_]*\s*>>\s*6\s*\)?)\s*!=\s*(?:0b10|2)(?:u8)?",
        normalized,
    ))
    if utf8_shift_predicate or any(token in source for token in ("0b1100_0000", "0xC0", "0xC0u8", "is_leading_utf8_byte", "vladder_utf8_leading")):
        predicate = "utf8-leading-byte"
        evidence.append("UTF-8 leading-byte predicate" if not utf8_shift_predicate else "normalized shift-and-compare UTF-8 leading-byte predicate")
    elif any(token in source for token in ("== needle", "==needle", "== needles", "simd_eq", "cmpeq_epi8", "bytewise_equal", "vladder_word_equal", "vladder_mask_popcount", "vladder_lane_byte_accumulate")):
        predicate = "equal-u8"
        evidence.append("byte equality predicate")
    else:
        blockers.append("no supported exact byte predicate detected")
    realization: str | None
    if any(token in source for token in ("is_x86_feature_detected", "__builtin_cpu_supports", "vladder_deployment_avx2")):
        realization = "guarded-avx2-byte" if any(token in source for token in ("sad_epu8", "vladder_lane_byte_accumulate")) else "guarded-avx2"
        evidence.append("runtime or deployment ISA dispatch")
    elif any(token in source for token in ("_mm256_sad_epu8", "_mm256_sub_epi8", "vladder_lane_byte_accumulate")):
        realization = "simd-byte-accumulate-final"
        evidence.append("AVX2 lane-byte accumulation and horizontal SAD")
    elif any(token in source for token in ("_mm256_movemask_epi8", "movemask_epi8", "to_bitmask", "vladder_mask_popcount")):
        realization = "simd-mask-popcount"
        evidence.append("SIMD comparison mask and population reduction")
    elif any(token in source for token in ("usize_load_unchecked", "uint64_t", "UInt64", "u64", "bytewise_equal", "zero_byte", "is_leading_utf8_byte", "u64::from_ne_bytes", "vladder_word_equal")) and any(token in source for token in ("count_ones", "@popCount", "popcount", "sum_usize", "bytewise_equal", "is_leading_utf8_byte", "vladder_word_equal")):
        realization = "word-swar"
        evidence.append("packed-word lane predicate")
    elif any(token in normalized for token in (".filter(", ".fold(", "for (", "for ", "while ")):
        realization = "scalar"
        evidence.append("scalar traversal and reduction")
    else:
        realization = None
        blockers.append("no supported physical realization detected")
    return SourceRealization(language, function, "exact-byte-predicate-reduction" if predicate else None, predicate, realization, tuple(evidence), tuple(blockers))
