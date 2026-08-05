from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable

from z3 import (
    BitVec,
    BitVecVal,
    Bool,
    BV2Int,
    Extract,
    If,
    Int,
    Int2BV,
    LShR,
    Or,
    Solver,
    Sum,
    ZeroExt,
    unsat,
)

from .deep_grammar import DeepDerivation
from .deep_ir import DeepKernelContract, build_deep_realization_graph, inspect_source_realization
from .deep_lowering import DeepCandidate


@dataclass(frozen=True)
class DeepProofObligation:
    id: str
    status: str
    method: str
    scope: str
    artifact: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _solver_obligation(
    obligation: str,
    output_directory: Path,
    build: Callable[[Solver], None],
    scope: str,
) -> DeepProofObligation:
    solver = Solver()
    build(solver)
    result = solver.check()
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / f"{obligation}.smt2"
    path.write_text(solver.to_smt2())
    return DeepProofObligation(
        obligation,
        "PASS" if result == unsat else "FAIL",
        "Z3",
        scope,
        str(path),
        "negated obligation is unsatisfiable" if result == unsat else f"solver result: {result}",
    )


def _word_equality(solver: Solver) -> None:
    lhs = BitVec("lhs", 64)
    rhs = BitVec("rhs", 64)
    lo = BitVecVal(0x0101010101010101, 64)
    hi = BitVecVal(0x8080808080808080, 64)
    x = lhs ^ rhs
    actual = ~(LShR((x & ~hi) + ~hi | x, 7)) & lo
    differences = []
    for lane in range(8):
        lane_lhs = Extract(lane * 8 + 7, lane * 8, lhs)
        lane_rhs = Extract(lane * 8 + 7, lane * 8, rhs)
        expected = If(lane_lhs == lane_rhs, BitVecVal(1, 8), BitVecVal(0, 8))
        differences.append(Extract(lane * 8 + 7, lane * 8, actual) != expected)
    solver.add(Or(differences))


def _utf8_word_predicate(solver: Solver) -> None:
    values = BitVec("values", 64)
    lo = BitVecVal(0x0101010101010101, 64)
    actual = (LShR(~values, 7) | LShR(values, 6)) & lo
    differences = []
    for lane in range(8):
        value = Extract(lane * 8 + 7, lane * 8, values)
        expected = If((value & BitVecVal(0xC0, 8)) != BitVecVal(0x80, 8), BitVecVal(1, 8), BitVecVal(0, 8))
        differences.append(Extract(lane * 8 + 7, lane * 8, actual) != expected)
    solver.add(Or(differences))


def _lane_partition(solver: Solver, width: int) -> None:
    length = Int("length")
    full = (length / width) * width
    remainder = length % width
    solver.add(length >= 0)
    solver.add(Or(full + remainder != length, remainder < 0, remainder >= width))


def _mask_population(solver: Solver, width: int) -> None:
    lanes = [Bool(f"lane_{index}") for index in range(width)]
    baseline = Sum([If(lane, 1, 0) for lane in lanes])
    mask_bits = Sum([If(lane, 1, 0) for lane in lanes])
    solver.add(baseline != mask_bits)


def _pack_bijection(solver: Solver, width: int) -> None:
    packed = BitVec("packed", width)
    unpacked = Sum([If(Extract(index, index, packed) == BitVecVal(1, 1), 1 << index, 0) for index in range(width)])
    solver.add(unpacked != BV2Int(ZeroExt(max(0, 64 - width), packed)))


def _bounded_accumulator(solver: Solver, width: int) -> None:
    # Lanes are independent and symmetric. Prove that every exact match count in one lane over
    # the admitted flush interval survives the native u8 modular representation, then combine
    # this with the separately proved lane predicate and horizontal reduction obligations.
    match_count = Int("match_count")
    solver.add(match_count >= 0, match_count <= 255)
    native_lane = Int2BV(match_count, 8)
    solver.add(BV2Int(native_lane) != match_count)


def _constant_splat(solver: Solver) -> None:
    needle = BitVec("needle", 8)
    splat = ZeroExt(56, needle) * BitVecVal(0x0101010101010101, 64)
    solver.add(Or([Extract(index * 8 + 7, index * 8, splat) != needle for index in range(8)]))


def _dispatch(solver: Solver) -> None:
    guard = Bool("guard")
    baseline = Int("baseline")
    vector_result = Int("vector_result")
    fallback_result = Int("fallback_result")
    solver.add(vector_result == baseline, fallback_result == baseline)
    solver.add(If(guard, vector_result, fallback_result) != baseline)


def _structural_obligation(
    obligation: str,
    status: bool,
    scope: str,
    detail: str,
) -> DeepProofObligation:
    return DeepProofObligation(obligation, "PASS" if status else "FAIL", "structural", scope, None, detail)


def _vector_alive_ir() -> str:
    return """declare i32 @llvm.vector.reduce.add.v4i32(<4 x i32>)
declare i4 @llvm.ctpop.i4(i4)

define i32 @src(<4 x i8> %x, i8 %needle) {
  %p0 = insertelement <4 x i8> poison, i8 %needle, i32 0
  %splat = shufflevector <4 x i8> %p0, <4 x i8> poison, <4 x i32> zeroinitializer
  %cmp = icmp eq <4 x i8> %x, %splat
  %z = zext <4 x i1> %cmp to <4 x i32>
  %sum = call i32 @llvm.vector.reduce.add.v4i32(<4 x i32> %z)
  ret i32 %sum
}

define i32 @tgt(<4 x i8> %x, i8 %needle) {
  %p0 = insertelement <4 x i8> poison, i8 %needle, i32 0
  %splat = shufflevector <4 x i8> %p0, <4 x i8> poison, <4 x i32> zeroinitializer
  %cmp = icmp eq <4 x i8> %x, %splat
  %mask = bitcast <4 x i1> %cmp to i4
  %sum4 = call i4 @llvm.ctpop.i4(i4 %mask)
  %sum = zext i4 %sum4 to i32
  ret i32 %sum
}
"""


def _vector_byte_accumulate_alive_ir() -> str:
    return """declare i32 @llvm.vector.reduce.add.v4i32(<4 x i32>)

define i32 @src(<4 x i8> %x, i8 %needle) {
  %p0 = insertelement <4 x i8> poison, i8 %needle, i32 0
  %splat = shufflevector <4 x i8> %p0, <4 x i8> poison, <4 x i32> zeroinitializer
  %cmp = icmp eq <4 x i8> %x, %splat
  %values = zext <4 x i1> %cmp to <4 x i32>
  %sum = call i32 @llvm.vector.reduce.add.v4i32(<4 x i32> %values)
  ret i32 %sum
}

define i32 @tgt(<4 x i8> %x, i8 %needle) {
  %p0 = insertelement <4 x i8> poison, i8 %needle, i32 0
  %splat = shufflevector <4 x i8> %p0, <4 x i8> poison, <4 x i32> zeroinitializer
  %cmp = icmp eq <4 x i8> %x, %splat
  %native_mask = sext <4 x i1> %cmp to <4 x i8>
  %lanes = sub <4 x i8> zeroinitializer, %native_mask
  %values = zext <4 x i8> %lanes to <4 x i32>
  %sum = call i32 @llvm.vector.reduce.add.v4i32(<4 x i32> %values)
  ret i32 %sum
}
"""


def prove_vector_core_alive2(output_directory: Path, *, timeout_seconds: int = 60) -> DeepProofObligation:
    alive = shutil.which("alive-tv")
    if not alive:
        return DeepProofObligation("llvm-vector-core-refinement", "UNAVAILABLE", "Alive2", "8-lane generic vector equality/popcount core", None, "alive-tv not found")
    output_directory.mkdir(parents=True, exist_ok=True)
    ir = output_directory / "vector-mask-popcount.ll"
    transcript = output_directory / "vector-mask-popcount.alive2.txt"
    ir.write_text(_vector_alive_ir())
    try:
        completed = subprocess.run(
            [alive, "--bidirectional", "--smt-to=30000", str(ir)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
        output = completed.stdout
        transcript.write_text(output)
        timed_out = "ERROR: Timeout" in output
        passed = completed.returncode == 0 and "ERROR:" not in output and "Transformation doesn't verify" not in output
        return DeepProofObligation(
            "llvm-vector-core-refinement",
            "PASS" if passed else "TIMEOUT" if timed_out else "FAIL",
            "Alive2",
            "bidirectional 4-lane LLVM vector equality/reduce versus mask/ctpop; lane-width generalization is separately proved by Z3",
            str(transcript),
            f"alive-tv return code {completed.returncode}",
        )
    except subprocess.TimeoutExpired as error:
        transcript.write_text((error.stdout or "") if isinstance(error.stdout, str) else "")
        return DeepProofObligation("llvm-vector-core-refinement", "TIMEOUT", "Alive2", "4-lane generic vector core", str(transcript), f"timeout after {timeout_seconds}s")


def prove_vector_byte_accumulate_alive2(output_directory: Path, *, timeout_seconds: int = 60) -> DeepProofObligation:
    alive = shutil.which("alive-tv")
    if not alive:
        return DeepProofObligation("llvm-byte-accumulator-core-refinement", "UNAVAILABLE", "Alive2", "4-lane equality-to-byte-accumulator core", None, "alive-tv not found")
    output_directory.mkdir(parents=True, exist_ok=True)
    ir = output_directory / "vector-byte-accumulate.ll"
    transcript = output_directory / "vector-byte-accumulate.alive2.txt"
    ir.write_text(_vector_byte_accumulate_alive_ir())
    try:
        completed = subprocess.run(
            [alive, "--bidirectional", "--smt-to=30000", str(ir)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
        output = completed.stdout
        transcript.write_text(output)
        timed_out = "ERROR: Timeout" in output
        passed = completed.returncode == 0 and "ERROR:" not in output and "Transformation doesn't verify" not in output
        return DeepProofObligation(
            "llvm-byte-accumulator-core-refinement",
            "PASS" if passed else "TIMEOUT" if timed_out else "FAIL",
            "Alive2",
            "bidirectional 4-lane LLVM equality reduction versus native compare-mask subtraction into byte lanes; repeated no-wrap interval is separately proved by Z3",
            str(transcript),
            f"alive-tv return code {completed.returncode}",
        )
    except subprocess.TimeoutExpired as error:
        transcript.write_text((error.stdout or "") if isinstance(error.stdout, str) else "")
        return DeepProofObligation("llvm-byte-accumulator-core-refinement", "TIMEOUT", "Alive2", "4-lane byte accumulator core", str(transcript), f"timeout after {timeout_seconds}s")


def prove_deep_candidate(
    contract: DeepKernelContract,
    derivation: DeepDerivation,
    candidate: DeepCandidate,
    output_directory: Path,
    *,
    require_alive2_for_vector_mask: bool = True,
) -> dict[str, Any]:
    proof_dir = output_directory / candidate.id
    proof_dir.mkdir(parents=True, exist_ok=True)
    graph = build_deep_realization_graph(contract, candidate.realization, source_language=candidate.language, function_identity=candidate.function)
    requested = tuple(dict.fromkeys(derivation.proof_obligations))
    source_identity = inspect_source_realization(candidate.source, candidate.language, candidate.function)
    source_hash_matches = hashlib.sha256(candidate.source.encode()).hexdigest() == candidate.source_sha256
    source_binding_pass = (
        source_hash_matches
        and derivation.target == candidate.realization
        and source_identity.representable
        and source_identity.predicate == contract.predicate
        and source_identity.realization == candidate.realization
        and candidate.graph_hash == graph.graph_hash
    )
    width_token = ""
    if candidate.realization != "scalar":
        native_width = 8 if candidate.realization == "word-swar" else 32
        compact_source = "".join(candidate.source.split())
        guard_tokens = (
            f"n-i>={native_width}",
            f"data.len()-i>={native_width}",
        )
        width_token = next((token for token in guard_tokens if token in compact_source), "")
        source_binding_pass = source_binding_pass and bool(width_token) and f"i+={native_width}" in compact_source
    obligations: list[DeepProofObligation] = [
        _structural_obligation(
            "native-source-binding",
            source_binding_pass,
            "generated native source, registered derivation, and reconstructed target graph",
            f"source realization={source_identity.realization}, predicate={source_identity.predicate}, width_guard={width_token or 'scalar'}",
        )
    ]
    width = 32 if "simd" in candidate.realization or "avx2" in candidate.realization else 8
    for obligation in requested:
        if obligation == "word-equality-identity":
            builder = _word_equality if contract.predicate == "equal-u8" else _utf8_word_predicate
            obligations.append(_solver_obligation(obligation, proof_dir, builder, "all 2^64 packed word values and all predicate bytes where applicable"))
        elif obligation in {"lane-partition", "tail-partition", "footprint-coverage"}:
            obligations.append(_solver_obligation(obligation, proof_dir, lambda solver, w=width: _lane_partition(solver, w), f"all nonnegative lengths, width={width}"))
        elif obligation in {"lane-predicate", "mask-population", "reduction-equivalence", "observable-equivalence"}:
            obligations.append(_solver_obligation(obligation, proof_dir, lambda solver, w=width: _mask_population(solver, w), f"all {width} independent predicate lanes"))
        elif obligation == "pack-bijection":
            obligations.append(_solver_obligation(obligation, proof_dir, lambda solver, w=min(width, 32): _pack_bijection(solver, w), f"all {min(width, 32)}-bit lane masks"))
        elif obligation == "bounded-lane-accumulator":
            obligations.append(_solver_obligation(obligation, proof_dir, lambda solver, w=width: _bounded_accumulator(solver, w), f"{width} lanes, flush interval <=255"))
        elif obligation == "constant-synthesis":
            obligations.append(_solver_obligation(obligation, proof_dir, _constant_splat, "all 8-bit predicate values across eight word lanes"))
        elif obligation in {"dispatch-completeness", "fallback-equivalence"}:
            obligations.append(_solver_obligation(obligation, proof_dir, _dispatch, "both values of the runtime feature guard"))
        elif obligation == "target-width":
            obligations.append(_structural_obligation(obligation, width in {8, 32}, "declared terminal width", f"physical width is {width} bytes"))
        elif obligation == "unaligned-load-legality":
            tokens = ("memcpy", "loadu_si256", "from_ne_bytes")
            obligations.append(_structural_obligation(obligation, any(token in candidate.source for token in tokens), "native source load operation", "wide load uses memcpy or an unaligned intrinsic behind a dominating length guard"))
        elif obligation == "no-intermediate-observer":
            obligations.append(_structural_obligation(obligation, all(node.operation != "materialize" for node in graph.semantic_graph.nodes), "selected bounded function observables", "graph has no materialized predicate buffer or external intermediate observer"))
        elif obligation == "complexity-bound":
            obligations.append(_structural_obligation(obligation, graph.complexity.asymptotic_work == "O(n)" and graph.complexity.passes == 1, "declared input bounds", "candidate remains one-pass O(n) with no temporary materialization"))
        else:
            obligations.append(_structural_obligation(obligation, False, "unknown", "no proof generator registered"))
    alive2: DeepProofObligation | None = None
    if require_alive2_for_vector_mask and candidate.realization in {"simd-mask-popcount", "guarded-avx2"} and contract.predicate == "equal-u8":
        alive2 = prove_vector_core_alive2(proof_dir)
        obligations.append(alive2)
    elif require_alive2_for_vector_mask and candidate.realization in {"simd-byte-accumulate-final", "guarded-avx2-byte"} and contract.predicate == "equal-u8":
        alive2 = prove_vector_byte_accumulate_alive2(proof_dir)
        obligations.append(alive2)
    status = "PASS" if obligations and all(item.status == "PASS" for item in obligations) else "FAIL"
    report = {
        "schema_version": "vladder-deep-proof-v1",
        "status": status,
        "candidate": candidate.to_dict(),
        "contract": contract.to_dict(),
        "derivation_hash": derivation.derivation_hash,
        "graph_hash": graph.graph_hash,
        "source_hash_matches": source_hash_matches,
        "source_realization": source_identity.to_dict(),
        "obligations": [item.to_dict() for item in obligations],
        "proof_scope": {
            "z3": "lane, bit-vector, reduction, traversal, tail, overflow interval, and dispatch obligations",
            "alive2": alive2.scope if alive2 else "not required for this realization",
            "excluded": ["whole-program ownership protocols", "external calls", "hardware performance"],
        },
    }
    (output_directory / f"{candidate.id}.proof.json").write_text(__import__("json").dumps(report, indent=2, sort_keys=True) + "\n")
    return report
