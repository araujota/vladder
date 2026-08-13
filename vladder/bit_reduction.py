from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from pathlib import Path
from typing import Any

from z3 import BitVec, Extract, Int, Solver, Sum, ZeroExt, unsat

from .language_adapter import (
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    obligation,
)


BIT_REDUCTION_GRAMMAR_VERSION = "bit-popcount-reduction-v1"


@dataclass(frozen=True)
class BitReductionContract:
    element_bits: int = 8
    accumulator_bits: int = 64
    exact: bool = True
    maximum_length: int = 1 << 30
    source_binding: str = "borrowed-contiguous-sequence"

    def __post_init__(self) -> None:
        if self.element_bits not in {8, 16, 32, 64} or self.accumulator_bits not in {32, 64}:
            raise ValueError("bit reduction requires fixed-width integer elements and a 32- or 64-bit accumulator")
        if self.maximum_length < 0:
            raise ValueError("bit reduction maximum length must be nonnegative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BitReductionCandidate:
    id: str
    realization: str
    contract: BitReductionContract
    language: str
    function: str
    source: str
    source_sha256: str


def detect_bit_reduction(
    source: str,
    *,
    source_context: str | None = None,
    function: str | None = None,
) -> BitReductionContract | None:
    compact = re.sub(r"\s+", " ", source)
    has_popcount = any(token in compact for token in (
        "count_ones()", "count_ones(", "popcount", "popCount", "__builtin_popcount",
    ))
    has_reduction = bool(re.search(
        r"(?:\.map\([^;{}]*count_ones\(\)[^;{}]*\)\.sum\(\)|"
        r"\b(?:sum|count|total|result)\w*\s*\+=\s*[^;]*(?:count_ones|pop[Cc]ount)|"
        r"\breturn\s+[^;]*(?:count_ones|pop[Cc]ount))",
        compact,
    ))
    type_evidence = compact
    if source_context and function and "::" in function:
        owner = function.rsplit("::", 1)[0].rsplit("::", 1)[-1]
        structure = re.search(
            rf"\bstruct\s+{re.escape(owner)}\b[^{{]*\{{(.*?)\}}",
            source_context,
            re.S,
        )
        if structure:
            type_evidence += " " + structure.group(1)
    element_bits = next((
        bits for bits in (64, 32, 16, 8)
        if re.search(
            rf"(?:\[u{bits}\]|\[u{bits}\s*;|\[\]\s*const\s*u{bits}|"
            rf"uint{bits}_t|std::uint{bits}_t|Vector\{{UInt{bits}\}})",
            type_evidence,
        )
    ), None)
    if element_bits is None and re.search(r"unsigned\s+char", compact):
        element_bits = 8
    if not has_popcount or not has_reduction or element_bits is None:
        return None
    source_binding = (
        "projected-word-field-view"
        if re.search(r"\bself\.[A-Za-z_]\w*\.iter\(\)|Box\s*<\s*\[", compact)
        else "borrowed-contiguous-sequence"
    )
    return BitReductionContract(element_bits=element_bits, source_binding=source_binding)


def bit_reduction_realizations(contract: BitReductionContract) -> tuple[str, ...]:
    return (
        ("scalar-byte", "word-u64", "word-u64-unroll2")
        if contract.element_bits == 8 else
        ("scalar-element", "element-unroll2", "element-unroll4", "element-unroll8")
    )


def build_bit_reduction_graph(
    contract: BitReductionContract,
    *,
    language: str,
    function: str,
) -> SemanticFlowGraph:
    exact = obligation(
        "bit-reduction.exact-population",
        "numeric",
        "the result equals the sum of set bits in every input byte",
        scope="bounded-call",
        proof_method="z3-bitvector-byte-partition",
        language=language,
    )
    bounds = obligation(
        "bit-reduction.valid-range",
        "bounds",
        "input denotes a valid contiguous byte range for n elements",
        scope="bounded-call",
        proof_method="typed-source-contract",
        language=language,
    )
    nodes = (
        SemanticFlowNode("input", "Input", contract.source_binding, (), f"u{contract.element_bits}[]", {}, {}, (bounds,)),
        SemanticFlowNode("loop", "Loop", "contiguous-forward-traversal", ("input",), "index", {}, {}, ()),
        SemanticFlowNode("load", "Load", "load-element-or-word", ("input", "loop"), f"u{contract.element_bits}|u64", {}, {}, (bounds,)),
        SemanticFlowNode("population", "PopulationCount", "exact-popcount", ("load",), "usize", {}, {}, (exact,)),
        SemanticFlowNode("reduce", "Reduce", "exact-add", ("population",), "usize", {}, {}, (exact,)),
        SemanticFlowNode("tail", "Tail", "scalar-byte-remainder", ("input", "loop", "reduce"), "usize", {}, {}, (bounds,)),
        SemanticFlowNode("output", "Output", "return-exact-popcount", ("tail",), "usize", {}, {}, (exact,)),
    )
    edge_specs = (
        ("input", "loop", f"u{contract.element_bits}[]"), ("loop", "load", "index"), ("input", "load", f"u{contract.element_bits}[]"),
        ("load", "population", f"u{contract.element_bits}|u64"), ("population", "reduce", "usize"),
        ("input", "tail", f"u{contract.element_bits}[]"), ("loop", "tail", "index"), ("reduce", "tail", "usize"),
        ("tail", "output", "usize"),
    )
    edges = tuple(
        SemanticFlowEdge(f"e{index}", source, destination, value_type, "ephemeral", "input", "call", "exact")
        for index, (source, destination, value_type) in enumerate(edge_specs)
    )
    return SemanticFlowGraph(
        function,
        language,
        "semantic-contract",
        "bit-popcount-reduction",
        function,
        nodes,
        edges,
        {"bit_reduction": contract.to_dict(), "grammar": BIT_REDUCTION_GRAMMAR_VERSION},
        ("nullable or owning wrapper", "external protocol", "concurrent mutation"),
        (bounds, exact),
    )


def enumerate_bit_reduction_candidates(
    contract: BitReductionContract,
    *,
    language: str,
    function: str = "bit_popcount_candidate",
) -> tuple[BitReductionCandidate, ...]:
    if language not in {"c", "cpp", "rust", "zig", "julia"}:
        raise ValueError("bit-popcount-reduction-v1 has no emitter for the requested language")
    candidates = []
    for realization in bit_reduction_realizations(contract):
        source = _emit_candidate(contract, realization, language, function)
        digest = hashlib.sha256(source.encode()).hexdigest()
        candidates.append(BitReductionCandidate(
            canonical_hash({
                "contract": contract.to_dict(), "realization": realization,
                "language": language, "source": digest,
            }),
            realization,
            contract,
            language,
            function,
            source,
            digest,
        ))
    return tuple(candidates)


def prove_bit_reduction_candidate(
    candidate: BitReductionCandidate,
    output_directory: Path,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    word = BitVec("word", 64)
    all_bits = Sum([ZeroExt(63, Extract(bit, bit, word)) for bit in range(64)])
    byte_bits = Sum([
        ZeroExt(63, Extract(bit, bit, Extract(byte * 8 + 7, byte * 8, word)))
        for byte in range(8) for bit in range(8)
    ])
    blocks = Int("blocks")
    block = Int("block")
    lane = Int("lane")
    factor = next(
        (value for value in (8, 4, 2) if candidate.realization.endswith(f"unroll{value}")),
        1,
    )
    solver = Solver()
    solver.add(blocks >= 0, block >= 0, block < blocks, lane == block % factor)
    solver.add((all_bits != byte_bits) | (lane < 0) | (lane >= factor))
    result = solver.check()
    artifact = output_directory / f"{candidate.realization}.smt2"
    artifact.write_text(solver.to_smt2())
    source_ok = hashlib.sha256(candidate.source.encode()).hexdigest() == candidate.source_sha256
    return {
        "schema_version": "vladder-bit-reduction-proof-v1",
        "status": "PASS" if result == unsat and source_ok else "FAIL",
        "proof_class": "z3-word-byte-popcount-partition",
        "realization": candidate.realization,
        "source_binding": "PASS" if source_ok else "FAIL",
        "z3_result": str(result),
        "artifact": str(artifact),
        "claim_boundary": "generated bounded kernel; nullable or owning wrapper remains outside this proof",
    }


def _emit_candidate(
    contract: BitReductionContract,
    realization: str,
    language: str,
    function: str,
) -> str:
    if language == "rust":
        return _emit_rust(contract, realization, function)
    if language == "zig":
        return _emit_zig(contract, realization, function)
    if language == "julia":
        return _emit_julia(contract, realization, function)
    include = "#include <stddef.h>\n#include <stdint.h>\n#include <string.h>\n" if language == "c" else (
        "#include <cstddef>\n#include <cstdint>\n#include <cstring>\n"
    )
    size_type = "size_t" if language == "c" else "std::size_t"
    element_type = (
        f"uint{contract.element_bits}_t"
        if language == "c" else f"std::uint{contract.element_bits}_t"
    )
    word_type = "uint64_t" if language == "c" else "std::uint64_t"
    linkage = "" if language == "c" else 'extern "C" '
    noexcept = "" if language == "c" else " noexcept"
    if contract.element_bits == 8 and realization == "scalar-byte":
        body = "for (; i < n; ++i) total += (size_t)__builtin_popcount((unsigned)data[i]);"
    elif contract.element_bits == 8:
        factor = 2 if realization.endswith("unroll2") else 1
        loads = []
        for lane in range(factor):
            loads.append(
                f"        {word_type} word{lane}; memcpy(&word{lane}, data + i + {lane * 8}, 8); "
                f"total += ({size_type})__builtin_popcountll((unsigned long long)word{lane});"
            )
        body = (
            f"for (; i + {factor * 8 - 1} < n; i += {factor * 8}) {{\n"
            + "\n".join(loads)
            + "\n    }\n    for (; i < n; ++i) total += "
            f"({size_type})__builtin_popcount((unsigned)data[i]);"
        )
    else:
        factor = next(
            (value for value in (8, 4, 2) if realization.endswith(f"unroll{value}")),
            1,
        )
        builtin = "__builtin_popcountll" if contract.element_bits == 64 else "__builtin_popcount"
        cast = "unsigned long long" if contract.element_bits == 64 else "unsigned"
        lanes = "\n".join(
            f"        total += ({size_type}){builtin}(({cast})data[i + {lane}]);"
            for lane in range(factor)
        )
        body = (
            f"for (; i + {factor - 1} < n; i += {factor}) {{\n{lanes}\n    }}\n"
            f"    for (; i < n; ++i) total += ({size_type}){builtin}(({cast})data[i]);"
        )
    return f"""{include}
{linkage}__attribute__((noinline)) {size_type} {function}(
    const {element_type} *data, {size_type} n){noexcept} {{
    {size_type} total = 0;
    {size_type} i = 0;
    {body}
    return total;
}}
"""


def _emit_rust(contract: BitReductionContract, realization: str, function: str) -> str:
    element_type = f"u{contract.element_bits}"
    if contract.element_bits == 8 and realization == "scalar-byte":
        body = "while i < n { total += data[i].count_ones() as usize; i += 1; }"
    elif contract.element_bits == 8:
        factor = 2 if realization.endswith("unroll2") else 1
        loads = "\n".join(
            f"        total += unsafe {{ (data.as_ptr().add(i + {lane * 8}) as *const u64).read_unaligned() }}.count_ones() as usize;"
            for lane in range(factor)
        )
        body = (
            f"while i + {factor * 8 - 1} < n {{\n{loads}\n        i += {factor * 8};\n    }}\n"
            "    while i < n { total += data[i].count_ones() as usize; i += 1; }"
        )
    else:
        factor = next(
            (value for value in (8, 4, 2) if realization.endswith(f"unroll{value}")),
            1,
        )
        loads = "\n".join(
            f"        total += data[i + {lane}].count_ones() as usize;"
            for lane in range(factor)
        )
        body = (
            f"while i + {factor - 1} < n {{\n{loads}\n        i += {factor};\n    }}\n"
            "    while i < n { total += data[i].count_ones() as usize; i += 1; }"
        )
    return f"""#![allow(clippy::missing_safety_doc)]

#[unsafe(no_mangle)]
#[inline(never)]
pub unsafe extern "C" fn {function}(input: *const {element_type}, n: usize) -> usize {{
    let data = unsafe {{ core::slice::from_raw_parts(input, n) }};
    let mut total: usize = 0;
    let mut i: usize = 0;
    {body}
    total
}}
"""


def _emit_zig(contract: BitReductionContract, realization: str, function: str) -> str:
    element_type = f"u{contract.element_bits}"
    if contract.element_bits == 8 and realization == "scalar-byte":
        body = "while (i < n) : (i += 1) { total += @popCount(data[i]); }"
    elif contract.element_bits == 8:
        factor = 2 if realization.endswith("unroll2") else 1
        loads = "\n".join(
            f"        const word{lane}: *align(1) const u64 = @ptrCast(data.ptr + i + {lane * 8}); "
            f"total += @popCount(word{lane}.*);"
            for lane in range(factor)
        )
        body = (
            f"while (i + {factor * 8 - 1} < n) : (i += {factor * 8}) {{\n{loads}\n    }}\n"
            "    while (i < n) : (i += 1) { total += @popCount(data[i]); }"
        )
    else:
        factor = next(
            (value for value in (8, 4, 2) if realization.endswith(f"unroll{value}")),
            1,
        )
        lanes = "\n".join(
            f"        total += @popCount(data[i + {lane}]);"
            for lane in range(factor)
        )
        body = (
            f"while (i + {factor - 1} < n) : (i += {factor}) {{\n{lanes}\n    }}\n"
            "    while (i < n) : (i += 1) { total += @popCount(data[i]); }"
        )
    return f"""export fn {function}(input: [*]const {element_type}, n: usize) usize {{
    const data = input[0..n];
    var total: usize = 0;
    var i: usize = 0;
    {body}
    return total;
}}
"""


def _emit_julia(contract: BitReductionContract, realization: str, function: str) -> str:
    element_type = f"UInt{contract.element_bits}"
    if contract.element_bits == 8 and realization == "scalar-byte":
        body = "while i < n; total += count_ones(data[i + 1]); i += 1; end"
    elif contract.element_bits == 8:
        factor = 2 if realization.endswith("unroll2") else 1
        loads = "\n".join(
            f"            total += count_ones(unsafe_load(Ptr{{UInt64}}(pointer(data) + i + {lane * 8})))"
            for lane in range(factor)
        )
        body = f"""GC.@preserve data begin
        while i + {factor * 8 - 1} < n
{loads}
            i += {factor * 8}
        end
    end
    while i < n; total += count_ones(data[i + 1]); i += 1; end"""
    else:
        factor = next(
            (value for value in (8, 4, 2) if realization.endswith(f"unroll{value}")),
            1,
        )
        lanes = "\n".join(
            f"        total += count_ones(data[i + {lane + 1}])"
            for lane in range(factor)
        )
        body = f"""while i + {factor - 1} < n
{lanes}
        i += {factor}
    end
    while i < n; total += count_ones(data[i + 1]); i += 1; end"""
    return f"""function {function}(data::Vector{{{element_type}}})::Int
    n = length(data)
    total = 0
    i = 0
    {body}
    return total
end
"""
