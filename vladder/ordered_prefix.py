from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from pathlib import Path
from typing import Any

from z3 import Int, Solver, unsat

from .language_adapter import (
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    obligation,
)


ORDERED_PREFIX_GRAMMAR_VERSION = "ordered-prefix-suffix-v2"


@dataclass(frozen=True)
class OrderedReductionContract:
    direction: str
    predicate: str
    element_bits: int = 8
    exact: bool = True
    maximum_length: int = 1 << 30
    operand_mode: str = "constant"
    source_binding: str = "borrowed-contiguous"

    def __post_init__(self) -> None:
        if self.direction not in {"prefix", "suffix"}:
            raise ValueError("ordered reduction direction must be prefix or suffix")
        if self.predicate not in {"equal-u8", "nonzero-u8", "equal-elements", "nonzero-element"}:
            raise ValueError("ordered reduction predicate is unsupported")
        if self.element_bits not in {8, 16, 32, 64} or self.maximum_length < 0:
            raise ValueError("ordered reductions require bounded fixed-width input")
        if self.operand_mode not in {"constant", "pair"}:
            raise ValueError("ordered reduction operand mode must be constant or pair")
        if self.operand_mode == "pair" and self.predicate != "equal-elements":
            raise ValueError("paired ordered reductions compare corresponding elements")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderedReductionCandidate:
    id: str
    factor: int
    contract: OrderedReductionContract
    language: str
    function: str
    source: str
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "contract": self.contract.to_dict(),
        }


def detect_ordered_reduction(source: str) -> OrderedReductionContract | None:
    compact = re.sub(r"\s+", " ", source)
    has_loop = bool(re.search(r"\b(?:while|for)\b\s*(?:\(|[A-Za-z_])", compact))
    has_iterator = any(token in compact for token in ("take_while", "find(|", "position(|"))
    if not has_loop and not has_iterator:
        return None

    pair_match = re.search(
        r"\b([A-Za-z_]\w*)\s*\[([^\]]+)\]\s*==\s*([A-Za-z_]\w*)\s*\[([^\]]+)\]",
        compact,
    )
    constant_match = re.search(
        r"\b([A-Za-z_]\w*)\s*\[([^\]]+)\]\s*(?:==\s*(?:needle|value|target|byte|'[^']*'|\d+)|!=\s*(?:0|false))",
        compact,
    )
    iterator_pair = bool(re.search(r"(?:zip\s*\(|take_while\s*\(\s*\|\s*\([^)]*\)\s*\|\s*[^=]+==)", compact))
    operand_mode = "pair" if (
        pair_match is not None and pair_match.group(1) != pair_match.group(3)
    ) or iterator_pair else "constant"

    compared_indices = (
        (pair_match.group(2), pair_match.group(4)) if pair_match is not None else
        (constant_match.group(2),) if constant_match is not None else ()
    )
    suffix = bool(
        re.search(r"\.rev\(\)\s*\.take_while", compact)
        or any(re.search(r"(?:length|len|size)\s*\(\s*\)\s*-\s*1\s*-", index) for index in compared_indices)
    )
    direction = "suffix" if suffix else "prefix"

    if operand_mode == "pair":
        if not (pair_match or iterator_pair):
            return None
        predicate = "equal-elements"
    else:
        equal_constant = re.search(
            r"==\s*(?:needle|value|target|byte|'[^']*'|\d+)|(?:needle|value|target|byte)\s*==",
            compact,
        )
        nonzero = re.search(r"!=\s*(?:0|false)", compact)
        if equal_constant:
            predicate = "equal-u8"
        elif nonzero:
            predicate = "nonzero-u8"
        else:
            return None

    # Require an ordered frontier result rather than accepting an arbitrary loop
    # that happens to contain an element comparison.
    bases = (
        tuple(pair_match.group(index) for index in (1, 3)) if pair_match else
        (constant_match.group(1),) if constant_match else ()
    )
    index_text = " ".join(compared_indices)
    frontier_candidates = [
        item for item in re.findall(r"\b[A-Za-z_]\w*\b", index_text)
        if item not in {*bases, "length", "len", "size"}
        and re.search(rf"(?:\+\+\s*{re.escape(item)}|{re.escape(item)}\s*\+\+|{re.escape(item)}\s*\+=\s*1)", compact)
    ]
    frontier = frontier_candidates[-1] if frontier_candidates else None
    direct_frontier = bool(
        frontier and re.search(rf"\breturn\s+{re.escape(frontier)}\s*;", compact)
    )
    direct_iterator = bool(
        re.search(r"(?:=>|\{)\s*[^{};]*\.take_while\([^{};]*\)\.count\(\)\s*;?\s*\}?\s*$", compact)
        or re.search(r"\breturn\s+[^;]*\.take_while\([^;]*\)\.count\(\)\s*;", compact)
    )
    if has_loop and not frontier:
        return None

    element_bits = _infer_element_bits(compact, bases)
    raw_bases = bool(bases) and all(_base_is_raw_pointer(compact, base) for base in bases)
    source_binding = (
        "raw-borrowed" if raw_bases else
        "borrowed-contiguous" if direct_frontier or direct_iterator else
        "embedded-bounded-subregion"
    )
    if operand_mode == "constant":
        predicate = "nonzero-element" if predicate == "nonzero-u8" and element_bits != 8 else predicate
        predicate = "equal-u8" if predicate == "equal-u8" else predicate
    return OrderedReductionContract(
        direction, predicate, element_bits=element_bits,
        operand_mode=operand_mode, source_binding=source_binding,
    )


def _base_is_raw_pointer(source: str, base: str) -> bool:
    return bool(re.search(
        rf"\b(?:const\s+)?(?:u?int(?:8|16|32|64)_t|std::u?int(?:8|16|32|64)_t|char|unsigned\s+char)\s*\*\s*{re.escape(base)}\b",
        source,
    ))


def _infer_element_bits(source: str, bases: tuple[str, ...]) -> int:
    if any(token in source for token in ("std::string", "string_view", "&str", "String")):
        return 8
    for base in bases:
        typed = re.search(
            rf"(?:u|i|uint|int)(8|16|32|64)(?:_t)?[^,;()]*\b{re.escape(base)}\b",
            source,
            re.IGNORECASE,
        )
        if typed:
            return int(typed.group(1))
    slice_type = re.search(
        r"(?:&\s*\[|\[\]\s*const\s*|Vector\{)(?:u|i|UInt|Int)(8|16|32|64)",
        source,
    )
    return int(slice_type.group(1)) if slice_type else 8


def build_ordered_reduction_graph(
    contract: OrderedReductionContract,
    *,
    language: str = "semantic",
    function: str = "ordered_reduction",
) -> SemanticFlowGraph:
    obligations = (
        obligation(
            "ordered.valid-range",
            "bounds",
            "input denotes a valid contiguous byte range for n elements",
            scope="bounded-call",
            proof_method="typed-source-contract",
            language=language,
        ),
        obligation(
            "ordered.first-failure",
            "validation",
            "the result is the exact ordered extent before the first predicate failure",
            scope="bounded-call",
            proof_method="z3-order-preserving-partition",
            language=language,
        ),
    )
    element = f"u{contract.element_bits}"
    nodes = (
        SemanticFlowNode("input", "Input", "borrowed-contiguous-sequence", (), f"{element}[]", {}, {}, (obligations[0],)),
        SemanticFlowNode(
            "rhs", "Input",
            "borrowed-contiguous-sequence" if contract.operand_mode == "pair" else "predicate-parameter",
            (), f"{element}[]" if contract.operand_mode == "pair" else element, {}, {}, (),
        ),
        SemanticFlowNode("loop", "Loop", f"ordered-{contract.direction}-traversal", ("input",), "index", {}, {}, ()),
        SemanticFlowNode("load", "Load", "load-fixed-width-element", ("input", "loop"), element, {}, {}, ()),
        SemanticFlowNode("predicate", "Compare", contract.predicate, ("load", "rhs"), "bool", {}, {}, ()),
        SemanticFlowNode("guard", "Guard", "stop-at-first-false", ("predicate",), "bool", {}, {}, (obligations[1],)),
        SemanticFlowNode("extent", "Reduce", f"ordered-{contract.direction}-extent", ("guard",), "usize", {}, {}, ()),
        SemanticFlowNode("output", "Output", "return-ordered-extent", ("extent",), "usize", {}, {}, ()),
    )
    edges = tuple(
        SemanticFlowEdge(f"e{index}", source, destination, value_type, "ephemeral", "input", "call", "ordered")
        for index, (source, destination, value_type) in enumerate((
            ("input", "loop", f"{element}[]"),
            ("loop", "load", "index"),
            ("input", "load", f"{element}[]"),
            ("load", "predicate", element),
            ("rhs", "predicate", f"{element}[]" if contract.operand_mode == "pair" else element),
            ("predicate", "guard", "bool"),
            ("guard", "extent", "bool"),
            ("extent", "output", "usize"),
        ))
    )
    return SemanticFlowGraph(
        function,
        language,
        "semantic-contract",
        "ordered-prefix-suffix",
        function,
        nodes,
        edges,
        {"ordered_reduction": contract.to_dict(), "grammar": ORDERED_PREFIX_GRAMMAR_VERSION},
        ("owning wrapper", "container mutation", "external protocol", "concurrent mutation"),
        obligations,
    )


def enumerate_ordered_candidates(
    contract: OrderedReductionContract,
    *,
    language: str = "cpp",
    function: str = "ordered_candidate",
    factors: tuple[int, ...] = (1, 2, 4, 8),
) -> tuple[OrderedReductionCandidate, ...]:
    if language not in {"c", "cpp", "rust", "zig", "julia"}:
        raise ValueError("ordered-prefix-suffix-v2 emits C, C++, Rust, Zig, and Julia candidates")
    candidates = []
    for factor in sorted(set(factors)):
        if factor < 1 or factor > 16 or factor & (factor - 1):
            raise ValueError("ordered reduction factors must be powers of two in [1, 16]")
        source = _emit_candidate(contract, factor, language, function)
        digest = hashlib.sha256(source.encode()).hexdigest()
        candidates.append(OrderedReductionCandidate(
            canonical_hash({"contract": contract.to_dict(), "factor": factor, "language": language, "source": digest}),
            factor,
            contract,
            language,
            function,
            source,
            digest,
        ))
    return tuple(candidates)


def _emit_candidate(contract: OrderedReductionContract, factor: int, language: str, function: str) -> str:
    if language == "rust":
        return _emit_rust_candidate(contract, factor, function)
    if language == "zig":
        return _emit_zig_candidate(contract, factor, function)
    if language == "julia":
        return _emit_julia_candidate(contract, factor, function)
    include = "#include <stddef.h>\n#include <stdint.h>\n" if language == "c" else "#include <cstddef>\n#include <cstdint>\n"
    size_type = "size_t" if language == "c" else "std::size_t"
    scalar = {8: "uint8_t", 16: "uint16_t", 32: "uint32_t", 64: "uint64_t"}[contract.element_bits]
    byte_type = scalar if language == "c" else f"std::{scalar}"
    linkage = "" if language == "c" else 'extern "C" '
    noexcept = "" if language == "c" else " noexcept"
    if contract.operand_mode == "pair":
        comparison = "left[{index}] == right[{index}]"
    else:
        comparison = "data[{index}] == needle" if contract.predicate.startswith("equal") else "data[{index}] != 0"
    checks = []
    if contract.direction == "prefix":
        for lane in range(factor):
            checks.append(f"        if (!({comparison.format(index=f'i + {lane}')})) return i + {lane};")
        body = f"""{size_type} i = 0;
    for (; i + {factor - 1} < n; i += {factor}) {{
{chr(10).join(checks)}
    }}
    for (; i < n; ++i) if (!({comparison.format(index='i')})) return i;
    return n;"""
    else:
        for lane in range(factor):
            offset = lane + 1
            checks.append(f"        if (!({comparison.format(index=f'i - {offset}')})) return n - (i - {offset} + 1); ")
        body = f"""{size_type} i = n;
    while (i >= {factor}) {{
{chr(10).join(checks)}
        i -= {factor};
    }}
    while (i > 0) {{
        if (!({comparison.format(index='i - 1')})) return n - i;
        --i;
    }}
    return n;"""
    arguments = (
        f"const {byte_type} *left, {size_type} left_n, const {byte_type} *right, {size_type} right_n"
        if contract.operand_mode == "pair" else
        f"const {byte_type} *data, {size_type} n, {byte_type} needle"
    )
    prelude = f"{size_type} n = left_n < right_n ? left_n : right_n;\n    " if contract.operand_mode == "pair" else ""
    return f"""{include}
{linkage}__attribute__((noinline)) {size_type} {function}({arguments}){noexcept} {{
    {prelude}{body}
}}
"""


def _emit_rust_candidate(contract: OrderedReductionContract, factor: int, function: str) -> str:
    rust_type = f"u{contract.element_bits}"
    if contract.operand_mode == "pair":
        comparison = "left[{index}] == right[{index}]"
    else:
        comparison = "data[{index}] == needle" if contract.predicate.startswith("equal") else "data[{index}] != 0"
    if contract.direction == "prefix":
        checks = "\n".join(
            f"        if !({comparison.format(index=f'i + {lane}')}) {{ return i + {lane}; }}"
            for lane in range(factor)
        )
        body = f"""let mut i: usize = 0;
    while i + {factor - 1} < n {{
{checks}
        i += {factor};
    }}
    while i < n {{
        if !({comparison.format(index='i')}) {{ return i; }}
        i += 1;
    }}
    n"""
    else:
        checks = "\n".join(
            f"        if !({comparison.format(index=f'i - {lane + 1}')}) {{ return n - (i - {lane + 1} + 1); }}"
            for lane in range(factor)
        )
        body = f"""let mut i: usize = n;
    while i >= {factor} {{
{checks}
        i -= {factor};
    }}
    while i > 0 {{
        if !({comparison.format(index='i - 1')}) {{ return n - i; }}
        i -= 1;
    }}
    n"""
    arguments = (
        f"left: *const {rust_type}, left_n: usize, right: *const {rust_type}, right_n: usize"
        if contract.operand_mode == "pair" else
        f"data: *const {rust_type}, n: usize, needle: {rust_type}"
    )
    setup = (
        "let n = core::cmp::min(left_n, right_n);\n"
        "    let left = unsafe { core::slice::from_raw_parts(left, n) };\n"
        "    let right = unsafe { core::slice::from_raw_parts(right, n) };"
        if contract.operand_mode == "pair" else
        "let data = unsafe { core::slice::from_raw_parts(data, n) };"
    )
    return f"""#![allow(clippy::missing_safety_doc)]

#[unsafe(no_mangle)]
#[inline(never)]
pub unsafe extern "C" fn {function}({arguments}) -> usize {{
    {setup}
    {body}
}}
"""


def _emit_zig_candidate(contract: OrderedReductionContract, factor: int, function: str) -> str:
    element = f"u{contract.element_bits}"
    comparison = (
        "left[{index}] == right[{index}]" if contract.operand_mode == "pair" else
        "data[{index}] == needle" if contract.predicate.startswith("equal") else
        "data[{index}] != 0"
    )
    if contract.direction == "prefix":
        checks = "\n".join(
            f"        if (!({comparison.format(index=f'i + {lane}')})) return i + {lane};"
            for lane in range(factor)
        )
        body = f"""var i: usize = 0;
    while (i + {factor - 1} < n) : (i += {factor}) {{
{checks}
    }}
    while (i < n) : (i += 1) {{
        if (!({comparison.format(index='i')})) return i;
    }}
    return n;"""
    else:
        checks = "\n".join(
            f"        if (!({comparison.format(index=f'i - {lane + 1}')})) return n - (i - {lane + 1} + 1);"
            for lane in range(factor)
        )
        body = f"""var i: usize = n;
    while (i >= {factor}) : (i -= {factor}) {{
{checks}
    }}
    while (i > 0) {{
        if (!({comparison.format(index='i - 1')})) return n - i;
        i -= 1;
    }}
    return n;"""
    arguments = (
        f"left: [*]const {element}, left_n: usize, right: [*]const {element}, right_n: usize"
        if contract.operand_mode == "pair" else
        f"data: [*]const {element}, n: usize, needle: {element}"
    )
    setup = "const n = @min(left_n, right_n);\n    " if contract.operand_mode == "pair" else ""
    return f"""export fn {function}({arguments}) callconv(.c) usize {{
    {setup}{body}
}}
"""


def _emit_julia_candidate(contract: OrderedReductionContract, factor: int, function: str) -> str:
    element = {8: "UInt8", 16: "UInt16", 32: "UInt32", 64: "UInt64"}[contract.element_bits]
    comparison = (
        "left[{index}] == right[{index}]" if contract.operand_mode == "pair" else
        "data[{index}] == needle" if contract.predicate.startswith("equal") else
        "data[{index}] != 0"
    )
    # Julia arrays are one-based; i is deliberately the zero-based semantic
    # extent so every language shares the same candidate state and proof.
    def access(index: str) -> str:
        return comparison.format(index=f"({index}) + 1")

    if contract.direction == "prefix":
        checks = "\n".join(
            f"        if !({access(f'i + {lane}')}); return i + {lane}; end"
            for lane in range(factor)
        )
        body = f"""i = 0
    while i + {factor - 1} < n
{checks}
        i += {factor}
    end
    while i < n
        if !({access('i')}); return i; end
        i += 1
    end
    return n"""
    else:
        checks = "\n".join(
            f"        if !({access(f'i - {lane + 1}')}); return n - (i - {lane + 1} + 1); end"
            for lane in range(factor)
        )
        body = f"""i = n
    while i >= {factor}
{checks}
        i -= {factor}
    end
    while i > 0
        if !({access('i - 1')}); return n - i; end
        i -= 1
    end
    return n"""
    arguments = (
        f"left::Vector{{{element}}}, right::Vector{{{element}}}"
        if contract.operand_mode == "pair" else
        f"data::Vector{{{element}}}, needle::{element}"
    )
    setup = "n = min(length(left), length(right))\n    " if contract.operand_mode == "pair" else "n = length(data)\n    "
    return f"""function {function}({arguments})::Int
    {setup}{body}
end
"""


def prove_ordered_candidate(candidate: OrderedReductionCandidate, output_directory: Path) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    n = Int("bounded_extent")
    k = Int("first_failure_extent")
    factor = candidate.factor
    block = k / factor
    lane = k % factor
    solver = Solver()
    candidate_result = block * factor + lane
    solver.add(n >= 0, k >= 0, k < n)
    solver.add(candidate_result != k)
    result = solver.check()
    smt = output_directory / f"ordered-{candidate.factor}.smt2"
    smt.write_text(solver.to_smt2())
    source_ok = hashlib.sha256(candidate.source.encode()).hexdigest() == candidate.source_sha256
    passed = result == unsat and source_ok
    return {
        "schema_version": "vladder-ordered-reduction-proof-v1",
        "status": "PASS" if passed else "FAIL",
        "proof_class": "parametric-first-failure-order-preserving-partition",
        "factor": factor,
        "direction": candidate.contract.direction,
        "predicate": candidate.contract.predicate,
        "operand_mode": candidate.contract.operand_mode,
        "element_bits": candidate.contract.element_bits,
        "source_binding": "PASS" if source_ok else "FAIL",
        "z3_result": str(result),
        "artifact": str(smt),
        "claim_boundary": (
            "all nonnegative valid lengths and first-failure positions; source binding covers the generated "
            "bounded kernel, not an owning wrapper or concurrent mutation"
        ),
    }
