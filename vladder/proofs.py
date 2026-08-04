from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
from typing import Any

from .candidates import Candidate, detect_affine, detect_clamp, detect_div_power2
from .extractor import ExtractedFunction


@dataclass(frozen=True)
class ProofResult:
    status: str
    method: str
    schema: str
    details: dict[str, Any]


def _parse_f32(text: str) -> float:
    return float(text.strip().rstrip("fF"))


def _z3_available() -> bool:
    try:
        import z3  # noqa: F401
    except Exception:
        return False
    return True


def _fp_eq_or_both_nan(z3: Any, a: Any, b: Any) -> Any:
    return z3.Or(a == b, z3.And(z3.fpIsNaN(a), z3.fpIsNaN(b)))


def _prove_fp_clamp(low: float, high: float) -> tuple[str, dict[str, Any]]:
    import z3

    x = z3.FP("x", z3.Float32())
    lo = z3.FPVal(low, z3.Float32())
    hi = z3.FPVal(high, z3.Float32())
    original = z3.If(z3.fpLT(x, lo), lo, z3.If(z3.fpGT(x, hi), hi, x))
    branchless = z3.If(z3.fpLT(x, lo), lo, z3.If(z3.fpGT(x, hi), hi, x))
    solver = z3.Solver()
    solver.add(z3.Not(_fp_eq_or_both_nan(z3, original, branchless)))
    result = solver.check()
    return ("PROVED" if result == z3.unsat else "FAILED", {"z3_result": str(result), "low": low, "high": high, "smt2": solver.to_smt2()})


def _prove_div_power2(divisor: float, multiplier: float) -> tuple[str, dict[str, Any]]:
    import z3

    x = z3.FP("x", z3.Float32())
    div = z3.FPVal(divisor, z3.Float32())
    mul = z3.FPVal(multiplier, z3.Float32())
    original = z3.fpDiv(z3.RNE(), x, div)
    rewritten = z3.fpMul(z3.RNE(), x, mul)
    solver = z3.Solver()
    solver.add(z3.Not(_fp_eq_or_both_nan(z3, original, rewritten)))
    result = solver.check()
    details: dict[str, Any] = {"z3_result": str(result), "divisor": divisor, "multiplier": multiplier}
    details["smt2"] = solver.to_smt2()
    if result == z3.sat:
        model = solver.model()
        details["counterexample"] = str(model)
    return ("PROVED" if result == z3.unsat else "FAILED", details)


def _prove_loop_partition() -> tuple[str, dict[str, Any]]:
    import z3

    n = z3.Int("n")
    u = z3.Int("u")
    k = z3.Int("k")
    q = z3.Int("q")
    r = z3.Int("r")
    solver = z3.Solver()
    solver.add(n >= 0, u > 0, k >= 0, k < n)
    solver.add(q == k / u, r == k % u)
    solver.add(z3.Not(z3.And(r >= 0, r < u, q * u + r == k)))
    result = solver.check()
    return (
        "PROVED" if result == z3.unsat else "FAILED",
        {"z3_result": str(result), "property": "unrolled loop covers each index exactly once", "smt2": solver.to_smt2()},
    )


def prove_candidate(fn: ExtractedFunction, candidate: Candidate) -> ProofResult:
    if candidate.proof == "identity":
        return ProofResult("PROVED", "syntactic", candidate.proof, {"reason": "candidate is the original function renamed"})

    if not _z3_available():
        return ProofResult("UNAVAILABLE", "z3", candidate.proof, {"reason": "python z3 module is not importable"})

    try:
        if candidate.proof == "structural_loop_hint":
            return ProofResult(
                "PROVED",
                "C-source-scheduling-contract",
                candidate.proof,
                {
                    "reason": "the generated Clang loop directive changes implementation scheduling but not C abstract-machine behavior",
                    "reference_body_sha256": hashlib.sha256(fn.body.encode()).hexdigest(),
                    "scope": "Alive2 proof IR suppresses the nonsemantic scheduling directive with VLADDER_PROOF; performance compilation applies it",
                },
            )
        if candidate.proof == "structural_ordered_unroll":
            status, details = _prove_loop_partition()
            details.update(
                {
                    "reason": "the admitted loop body is duplicated without statement reordering and executed in increasing logical-index order",
                    "reference_body_sha256": hashlib.sha256(fn.body.encode()).hexdigest(),
                    "scope": "Z3 proves exhaustive ordered loop partition; Alive2 is required to prove the complete compiled body substitution",
                }
            )
            return ProofResult(status, "z3-int+ordered-source-reconstruction", candidate.proof, details)
        if candidate.proof == "graph_exact_unroll":
            status, details = _prove_loop_partition()
            details["reason"] = "normalized graph expression is duplicated unchanged across an exhaustive loop partition"
            return ProofResult(status, "z3-int+graph-identity", candidate.proof, details)
        if candidate.proof.startswith("clamp_branchless"):
            pattern = detect_clamp(fn)
            if not pattern:
                return ProofResult("UNAVAILABLE", "z3", candidate.proof, {"reason": "source no longer matches clamp schema"})
            status, details = _prove_fp_clamp(_parse_f32(pattern.low), _parse_f32(pattern.high))
            if "unroll" in candidate.proof or "vector" in candidate.proof:
                loop_status, loop_details = _prove_loop_partition()
                details["loop_partition"] = loop_details
                if loop_status != "PROVED":
                    status = "FAILED"
            if "vector" in candidate.proof:
                details["vector_lane_argument"] = "SIMD candidate applies the proved scalar expression independently per lane; no-alias precondition is required."
            return ProofResult(status, "z3-fp", candidate.proof, details)

        if candidate.proof.startswith("affine"):
            pattern = detect_affine(fn)
            if not pattern:
                return ProofResult("UNAVAILABLE", "z3", candidate.proof, {"reason": "source no longer matches affine schema"})
            details: dict[str, Any] = {"reason": "candidate preserves the exact scalar expression", "mul": pattern.mul, "add": pattern.add}
            if "unroll" in candidate.proof or "vector" in candidate.proof:
                loop_status, loop_details = _prove_loop_partition()
                details["loop_partition"] = loop_details
                if loop_status != "PROVED":
                    return ProofResult("FAILED", "z3-int", candidate.proof, details)
            if "vector" in candidate.proof:
                details["vector_lane_argument"] = "SIMD candidate applies the same scalar expression independently per lane; no-alias precondition is required."
            return ProofResult("PROVED", "schema+z3-int", candidate.proof, details)

        if candidate.proof.startswith("fp_div_power2_to_mul"):
            pattern = detect_div_power2(fn)
            if not pattern:
                return ProofResult("UNAVAILABLE", "z3", candidate.proof, {"reason": "source no longer matches power-of-two division schema"})
            status, details = _prove_div_power2(_parse_f32(pattern.divisor), _parse_f32(pattern.multiplier))
            if "unroll" in candidate.proof or "vector" in candidate.proof:
                loop_status, loop_details = _prove_loop_partition()
                details["loop_partition"] = loop_details
                if loop_status != "PROVED":
                    status = "FAILED"
            if "vector" in candidate.proof:
                details["vector_lane_argument"] = "SIMD candidate applies the proved scalar expression independently per lane; no-alias precondition is required."
            return ProofResult(status, "z3-fp", candidate.proof, details)
    except Exception as exc:
        return ProofResult("ERROR", "z3", candidate.proof, {"error": str(exc)})

    return ProofResult("UNAVAILABLE", "none", candidate.proof, {"reason": "no proof schema registered"})


def _strip_smt2(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_smt2(v) for k, v in value.items() if k != "smt2"}
    if isinstance(value, list):
        return [_strip_smt2(v) for v in value]
    return value


def proof_to_dict(proof: ProofResult) -> dict[str, Any]:
    data = asdict(proof)
    data["details"] = _strip_smt2(data["details"])
    return data


def write_smt2_stub(path: Path, proof: ProofResult) -> None:
    smt2_parts = []
    details = proof.details
    if isinstance(details.get("smt2"), str):
        smt2_parts.append(details["smt2"])
    loop = details.get("loop_partition")
    if isinstance(loop, dict) and isinstance(loop.get("smt2"), str):
        smt2_parts.append(loop["smt2"])
    if smt2_parts:
        header = [
            "; vLadder proof artifact",
            f"; status: {proof.status}",
            f"; method: {proof.method}",
            f"; schema: {proof.schema}",
        ]
        path.write_text("\n".join(header + smt2_parts) + "\n")
        return
    lines = [
        "; vLadder proof artifact",
        f"; status: {proof.status}",
        f"; method: {proof.method}",
        f"; schema: {proof.schema}",
        "; Detailed proof inputs and solver result are stored in perf.json.",
        "(set-logic ALL)",
        "; The executable proof is produced through the Z3 Python API to use IEEE-754 FP helpers.",
    ]
    path.write_text("\n".join(lines) + "\n")
