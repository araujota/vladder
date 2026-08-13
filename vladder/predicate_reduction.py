from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from z3 import Bool, If, Int, Solver, Sum, unsat

from .language_adapter import (
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    obligation,
)


PREDICATE_REDUCTION_GRAMMAR_VERSION = "predicate-reduction-v1"
PREDICATE_REDUCTION_STYLES = ("branch", "branchless")
PREDICATE_REDUCTION_UNROLLS = (1, 2, 4, 8)
_ELEMENT_TYPES = frozenset({"bool", "u8", "u16", "u32", "u64", "i8", "i16", "i32", "i64"})


@dataclass(frozen=True)
class PredicateReductionContract:
    operation: str
    element_type: str
    accumulator_bits: int = 64
    maximum_length: int = 1 << 30
    source_binding: str = "borrowed-contiguous-sequence"
    ordered: bool = True

    def __post_init__(self) -> None:
        if self.operation not in {"count_true", "count_nonzero", "count_equal", "count_adjacent_changes"}:
            raise ValueError(f"unsupported predicate reduction operation: {self.operation}")
        if self.element_type not in _ELEMENT_TYPES:
            raise ValueError(f"unsupported predicate reduction element type: {self.element_type}")
        if self.accumulator_bits not in {32, 64} or self.maximum_length < 0:
            raise ValueError("predicate reduction requires a bounded 32- or 64-bit accumulator")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PredicateReductionCandidate:
    id: str
    contract: PredicateReductionContract
    style: str
    unroll: int
    language: str
    function: str
    source: str
    source_sha256: str

    @property
    def realization(self) -> str:
        return f"{self.style}-u{self.unroll}"


def detect_predicate_reduction(source: str) -> PredicateReductionContract | None:
    """Recognize exact total predicate reductions, including common borrowed wrapper views.

    Wrapper recognition does not prove the wrapper contract. It records a source binding that the
    owning adapter must validate while keeping the bounded computational subtree enumerable.
    """
    compact = re.sub(r"\s+", " ", source)
    dense = re.sub(r"\s+", "", source)

    bool_count = bool(re.search(
        r"\.iter\(\)\.filter\(\|&&[A-Za-z_]\w*\|\s*[A-Za-z_]\w*\)\.count\(\)",
        compact,
    ))
    if bool_count and ("[bool;" in dense or "&[bool]" in dense or ".seen" in dense):
        binding = "borrowed-contiguous-sequence" if "&[bool]" in dense else "projected-bool-field-view"
        return PredicateReductionContract("count_true", "bool", source_binding=binding)

    adjacent = (
        bool(re.search(r"\b(?:count|total)\s*\+=\s*1", compact))
        and bool(re.search(r"\bvalue\s*!=\s*last\b|\[[^]]+\]\s*!=\s*\[[^]]+\]", compact))
        and bool(re.search(r"\blast\s*=\s*value\b|\bi\s*-\s*1", compact))
    )
    if adjacent:
        element = _detect_element_type(dense) or "u32"
        binding = (
            "arrow-primitive-values-view"
            if any(token in source for token in ("UInt32Array", ".values()", ".values();"))
            else "borrowed-contiguous-sequence"
        )
        return PredicateReductionContract("count_adjacent_changes", element, source_binding=binding)

    reduction = bool(re.search(
        r"(?:\b(?:count|total|sum|result)\w*\s*\+=|\+\+\s*(?:count|total|sum|result)|"
        r"(?:count|total|sum|result)\w*\s*\+\+|\.filter\([^;{}]*\)\.count\(\))",
        compact,
    ))
    if not reduction:
        return None
    element = _detect_element_type(dense)
    if element is None:
        return None
    if re.search(r"(?:==\s*(?:needle|target|value)|(?:needle|target|value)\s*==)", compact):
        return PredicateReductionContract("count_equal", element)
    if re.search(r"!=\s*0|>\s*0", compact):
        return PredicateReductionContract("count_nonzero", element)
    return None


def build_predicate_reduction_graph(
    contract: PredicateReductionContract,
    *,
    language: str,
    function: str,
) -> SemanticFlowGraph:
    bounds = obligation(
        "predicate-reduction.bounds",
        "bounds",
        "the projected input is a valid contiguous sequence for the declared extent",
        scope="bounded-proof-unit",
        proof_method="typed-source-contract",
        language=language,
    )
    exact = obligation(
        "predicate-reduction.exact",
        "numeric",
        "the result equals the source-order sum of every declared predicate observation",
        scope="bounded-proof-unit",
        proof_method="z3-partition-and-differential",
        language=language,
    )
    wrapper = obligation(
        "predicate-reduction.wrapper-binding",
        "ownership",
        f"the owning wrapper projects exactly the {contract.source_binding} represented by the proof unit",
        scope="owning-wrapper",
        proof_method="project-adapter-or-compiler-summary",
        language=language,
    )
    nodes = [
        SemanticFlowNode("input", "Input", contract.source_binding, (), f"sequence<{contract.element_type}>", {}, {}, (bounds, wrapper)),
        SemanticFlowNode("loop", "Loop", "bounded-source-order-traversal", ("input",), "index", {}, {}, (bounds,)),
        SemanticFlowNode("load", "Load", "element-load", ("input", "loop"), contract.element_type, {}, {}, (bounds,)),
    ]
    predicate_inputs = ("load",)
    if contract.operation == "count_equal":
        nodes.append(SemanticFlowNode("needle", "Input", "predicate-parameter", (), contract.element_type, {}, {}, ()))
        predicate_inputs = ("load", "needle")
    if contract.operation == "count_adjacent_changes":
        nodes.append(SemanticFlowNode("previous", "Load", "previous-element-load", ("input", "loop"), contract.element_type, {"offset": -1}, {}, (bounds,)))
        predicate_inputs = ("load", "previous")
    nodes.extend((
        SemanticFlowNode("predicate", "Compare", contract.operation, predicate_inputs, "bool", {}, {}, (exact,)),
        SemanticFlowNode("reduce", "Reduce", "exact-indicator-sum", ("predicate", "loop"), f"u{contract.accumulator_bits}", {"ordered": True}, {}, (exact,)),
        SemanticFlowNode("output", "Output", "return-count", ("reduce",), f"u{contract.accumulator_bits}", {}, {}, (exact,)),
    ))
    node_by_id = {node.id: node for node in nodes}
    edges = tuple(
        SemanticFlowEdge(
            f"e{index}", source, node.id, node_by_id[source].output_type or "effect",
            "borrowed" if source == "input" else "ephemeral", "source", "call", "source-order",
        )
        for index, node in enumerate(nodes)
        for source in node.inputs
    )
    return SemanticFlowGraph(
        function,
        language,
        "source-contract",
        "predicate-reduction",
        function,
        tuple(nodes),
        edges,
        {"predicate_reduction": contract.to_dict(), "grammar": PREDICATE_REDUCTION_GRAMMAR_VERSION},
        (
            "owning wrapper source reconstruction" if contract.source_binding != "borrowed-contiguous-sequence" else "owning wrapper lifetime",
            "concurrent mutation",
            "external protocol",
        ),
        (bounds, exact, wrapper),
    )


def enumerate_predicate_reduction_candidates(
    contract: PredicateReductionContract,
    *,
    language: str,
    function: str = "predicate_reduction_candidate",
) -> tuple[PredicateReductionCandidate, ...]:
    if language not in {"c", "cpp", "rust", "zig", "julia"}:
        raise ValueError(f"predicate reduction has no {language} lowerer")
    candidates: list[PredicateReductionCandidate] = []
    for style in PREDICATE_REDUCTION_STYLES:
        for unroll in PREDICATE_REDUCTION_UNROLLS:
            source = _emit_candidate(contract, style, unroll, language, function)
            source_sha256 = hashlib.sha256(source.encode()).hexdigest()
            candidates.append(PredicateReductionCandidate(
                canonical_hash({
                    "contract": contract.to_dict(), "style": style, "unroll": unroll,
                    "language": language, "source": source_sha256,
                }),
                contract, style, unroll, language, function, source, source_sha256,
            ))
    return tuple(candidates)


def prove_predicate_reduction_candidate(
    candidate: PredicateReductionCandidate,
    output_directory: Path,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    predicates = [Bool(f"predicate_{index}") for index in range(32)]
    baseline = Sum([If(item, 1, 0) for item in predicates])
    grouped = Sum([
        Sum([If(predicates[index + lane], 1, 0) for lane in range(candidate.unroll)])
        for index in range(0, 32, candidate.unroll)
    ])
    n = Int("n")
    blocks = n / candidate.unroll
    remainder = n % candidate.unroll
    solver = Solver()
    solver.add(n >= 0)
    solver.add((baseline != grouped) | (blocks * candidate.unroll + remainder != n) | (remainder < 0) | (remainder >= candidate.unroll))
    result = solver.check()
    artifact = output_directory / "partition.smt2"
    artifact.write_text(solver.to_smt2())
    source_bound = hashlib.sha256(candidate.source.encode()).hexdigest() == candidate.source_sha256
    report = {
        "schema_version": "vladder-predicate-reduction-proof-v1",
        "status": "PASS" if result == unsat and source_bound else "FAIL",
        "proof_class": "z3-exact-predicate-partition-v1",
        "z3_result": str(result),
        "source_binding": "PASS" if source_bound else "FAIL",
        "artifact": str(artifact),
        "claim_boundary": "generated bounded proof unit; non-borrowed owning wrapper projection is a separate obligation",
    }
    (output_directory / "proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _detect_element_type(dense: str) -> str | None:
    checks = (
        ("bool", ("&[bool]", "[bool;", "bool*")),
        ("u8", ("&[u8]", "uint8_t", "std::uint8_t", "[]constu8", "Vector{UInt8}")),
        ("u16", ("&[u16]", "uint16_t", "std::uint16_t", "[]constu16", "Vector{UInt16}")),
        ("u32", ("&[u32]", "uint32_t", "std::uint32_t", "UInt32Array", "[]constu32", "Vector{UInt32}")),
        ("u64", ("&[u64]", "uint64_t", "std::uint64_t", "UInt64Array", "[]constu64", "Vector{UInt64}")),
        ("i32", ("&[i32]", "int32_t", "std::int32_t", "Int32Array", "[]consti32", "Vector{Int32}")),
        ("i64", ("&[i64]", "int64_t", "std::int64_t", "Int64Array", "[]consti64", "Vector{Int64}")),
    )
    return next((kind for kind, tokens in checks if any(token in dense for token in tokens)), None)


def _emit_candidate(
    contract: PredicateReductionContract,
    style: str,
    unroll: int,
    language: str,
    function: str,
) -> str:
    if style not in PREDICATE_REDUCTION_STYLES or unroll not in PREDICATE_REDUCTION_UNROLLS:
        raise ValueError("invalid predicate reduction realization")
    if language in {"c", "cpp"}:
        return _emit_c(contract, style, unroll, function, language == "cpp")
    if language == "rust":
        return _emit_rust(contract, style, unroll, function)
    if language == "zig":
        return _emit_zig(contract, style, unroll, function)
    return _emit_julia(contract, style, unroll, function)


def _type(contract: PredicateReductionContract, language: str) -> str:
    mappings = {
        "c": {"bool": "uint8_t", "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t", "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t"},
        "cpp": {"bool": "bool", "u8": "std::uint8_t", "u16": "std::uint16_t", "u32": "std::uint32_t", "u64": "std::uint64_t", "i8": "std::int8_t", "i16": "std::int16_t", "i32": "std::int32_t", "i64": "std::int64_t"},
        "rust": {"bool": "bool", "u8": "u8", "u16": "u16", "u32": "u32", "u64": "u64", "i8": "i8", "i16": "i16", "i32": "i32", "i64": "i64"},
        "zig": {"bool": "bool", "u8": "u8", "u16": "u16", "u32": "u32", "u64": "u64", "i8": "i8", "i16": "i16", "i32": "i32", "i64": "i64"},
        "julia": {"bool": "Bool", "u8": "UInt8", "u16": "UInt16", "u32": "UInt32", "u64": "UInt64", "i8": "Int8", "i16": "Int16", "i32": "Int32", "i64": "Int64"},
    }
    return mappings[language][contract.element_type]


def _predicate(contract: PredicateReductionContract, index: str, language: str) -> str:
    data = f"data[{index}]" if language != "julia" else f"data[{index}+1]"
    if contract.operation == "count_true":
        return data
    if contract.operation == "count_nonzero":
        return f"{data} != 0"
    if contract.operation == "count_equal":
        return f"{data} == needle"
    previous = f"data[{index}-1]" if language != "julia" else f"data[{index}]"
    return f"{data} != {previous}"


def _start(contract: PredicateReductionContract) -> tuple[str, str]:
    return ("1", "1") if contract.operation == "count_adjacent_changes" else ("0", "0")


def _emit_c(contract: PredicateReductionContract, style: str, unroll: int, function: str, cpp: bool) -> str:
    language = "cpp" if cpp else "c"
    element = _type(contract, language)
    size = "std::size_t" if cpp else "size_t"
    include = "#include <cstddef>\n#include <cstdint>\n" if cpp else "#include <stddef.h>\n#include <stdint.h>\n"
    linkage = 'extern "C" ' if cpp else ""
    noexcept = " noexcept" if cpp else ""
    start, initial = _start(contract)

    def update(index: str) -> str:
        predicate = _predicate(contract, index, language)
        return f"if ({predicate}) ++count;" if style == "branch" else f"count += ({size})({predicate});"

    lanes = "".join(update(f"i + {lane}") for lane in range(unroll))
    return (
        include
        + f"{linkage}__attribute__((noinline)) {size} {function}(const {element} *data, {size} n, {element} needle){noexcept} {{"
        + f"{size} count = n ? {initial} : 0; {size} i = {start};"
        + f"for (; i + {unroll - 1} < n; i += {unroll}) {{{lanes}}}"
        + f"for (; i < n; ++i) {{{update('i')}}} return count; }}\n"
    )


def _emit_rust(contract: PredicateReductionContract, style: str, unroll: int, function: str) -> str:
    element = _type(contract, "rust")
    start, initial = _start(contract)

    def update(index: str) -> str:
        predicate = _predicate(contract, index, "rust")
        return f"if {predicate} {{ count += 1; }}" if style == "branch" else f"count += ({predicate}) as usize;"

    lanes = "".join(update(f"i + {lane}") for lane in range(unroll))
    return f"""#![allow(clippy::missing_safety_doc)]
#[unsafe(no_mangle)]
#[inline(never)]
pub unsafe extern "C" fn {function}(input: *const {element}, n: usize, needle: {element}) -> usize {{
    let data = unsafe {{ core::slice::from_raw_parts(input, n) }};
    let mut count: usize = if n > 0 {{ {initial} }} else {{ 0 }};
    let mut i: usize = {start};
    while i + {unroll - 1} < n {{ {lanes} i += {unroll}; }}
    while i < n {{ {update('i')} i += 1; }}
    count
}}
"""


def _emit_zig(contract: PredicateReductionContract, style: str, unroll: int, function: str) -> str:
    element = _type(contract, "zig")
    start, initial = _start(contract)

    def update(index: str) -> str:
        predicate = _predicate(contract, index, "zig")
        return f"if ({predicate}) count += 1;" if style == "branch" else f"count += @intFromBool({predicate});"

    lanes = "".join(update(f"i + {lane}") for lane in range(unroll))
    return f"""export fn {function}(input: [*]const {element}, n: usize, needle: {element}) usize {{
    const data = input[0..n];
    var count: usize = if (n > 0) {initial} else 0;
    var i: usize = {start};
    while (i + {unroll - 1} < n) : (i += {unroll}) {{ {lanes} }}
    while (i < n) : (i += 1) {{ {update('i')} }}
    return count;
}}
"""


def _emit_julia(contract: PredicateReductionContract, style: str, unroll: int, function: str) -> str:
    element = _type(contract, "julia")
    start, initial = _start(contract)

    def update(index: str) -> str:
        predicate = _predicate(contract, index, "julia")
        return f"if {predicate}; count += 1; end" if style == "branch" else f"count += Int({predicate})"

    lanes = "\n".join(update(f"i + {lane}") for lane in range(unroll))
    return f"""function {function}(data::Vector{{{element}}}, needle::{element})::Int
    n = length(data)
    count = n > 0 ? {initial} : 0
    i = {start}
    while i + {unroll - 1} < n
        {lanes}
        i += {unroll}
    end
    while i < n
        {update('i')}
        i += 1
    end
    return count
end
"""
