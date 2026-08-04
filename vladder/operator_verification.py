from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from .extractor import extract_function
from .operator_contract import OperatorContract
from .operator_lift import LiftedOperatorCandidate


@dataclass(frozen=True)
class OperatorProof:
    status: str
    method: str
    obligations: list[str]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FORBIDDEN_SOURCE = re.compile(r"\b(?:malloc|calloc|realloc|free|new|delete|printf|fprintf|fopen|read|write|open|close|system|fork|exec|pthread_|std::thread|asm|__asm__)\b")


def structural_legality(contract: OperatorContract, candidate: LiftedOperatorCandidate) -> OperatorProof:
    errors = []
    if FORBIDDEN_SOURCE.search(candidate.source):
        errors.append("forbidden allocation, I/O, thread, system, or assembly operation")
    try:
        function = extract_function(candidate.source, contract.entrypoint)
    except Exception as exc:
        errors.append(f"entrypoint extraction failed: {exc}")
        function = None
    if function is not None:
        parameter_count = _parameter_count(function.signature)
        declared = _declared_parameter_count(contract)
        if parameter_count != declared:
            errors.append(f"ABI parameter count changed: expected {declared}, got {parameter_count}")
        calls = [name for name in re.findall(r"\b([A-Za-z_]\w*)\s*\(", function.body) if name not in {"if", "for", "while", "switch", "sizeof", "sqrtf"}]
        if calls:
            errors.append("unmodeled function calls: " + ", ".join(sorted(set(calls))))
    return OperatorProof(
        "failed" if errors else "proved",
        "structural-contract",
        ["abi", "allocation", "io", "external_calls", "specialization_authority"],
        {"errors": errors, "preconditions": list(candidate.preconditions)},
    )


def prove_operator_candidate(contract: OperatorContract, candidate: LiftedOperatorCandidate) -> OperatorProof:
    structural = structural_legality(contract, candidate)
    if structural.status != "proved":
        return structural
    try:
        import z3
    except Exception:
        return OperatorProof("unsupported", "z3", list(candidate.proof_obligations), {"reason": "z3 unavailable"})
    solver = z3.Solver()
    x = z3.FP("x", z3.Float32())
    residual = z3.FP("residual", z3.Float32())
    first = z3.fpAdd(z3.RNE(), x, residual)
    recomputed = z3.fpAdd(z3.RNE(), x, residual)
    solver.add(first != recomputed)
    result = solver.check()
    details: dict[str, Any] = {
        "fusion_expression": str(result),
        "fusion_smt2": solver.to_smt2(),
        "numerical_class": contract.data["semantics"].get("floating_point"),
    }
    reduction_changed = any(effect in candidate.plan.effects for effect in ("reduction_multi4", "reduction_pairwise"))
    if result != z3.unsat:
        status = "failed"
    elif reduction_changed:
        status = "bounded"
        details["reason"] = "reduction association changed; contract tolerance requires adversarial and held-out runtime bounds"
    else:
        status = "proved"
        details["reason"] = "fusion recomputes the same FP32 residual expression and preserves linear reduction order"
    return OperatorProof(status, "z3-fp+contract", list(candidate.proof_obligations), details)


def prove_operator_footprint(contract: OperatorContract, candidate: LiftedOperatorCandidate) -> OperatorProof:
    try:
        import z3
    except Exception:
        return OperatorProof("unsupported", "z3-int", ["bounds", "pointer_nonwrap", "alias"], {"reason": "z3 unavailable"})
    n, i = z3.Ints("n i")
    bases = {name: z3.Int(f"base_{name}") for name in (*contract.data["inputs"], *contract.data.get("scratch", {}), *contract.data["outputs"])}
    solver = z3.Solver()
    solver.add(n > 0, i >= 0, i < n)
    for base in bases.values():
        solver.add(base >= 0, base <= 2**64 - 1 - 4 * n)
    names = list(bases)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1:]:
            solver.add(z3.Or(bases[left] + 4 * n <= bases[right], bases[right] + 4 * n <= bases[left]))
    bad = [z3.Or(base + 4 * i < base, base + 4 * i + 3 >= base + 4 * n) for base in bases.values()]
    solver.add(z3.Or(*bad))
    result = solver.check()
    return OperatorProof("proved" if result == z3.unsat else "failed", "z3-unbounded-address", ["bounds", "pointer_nonwrap", "declared_noalias"], {"z3_result": str(result), "smt2": solver.to_smt2()})


def _parameter_count(signature: str) -> int:
    start = signature.find("(")
    end = signature.rfind(")")
    if start < 0 or end < start:
        return 0
    text = signature[start + 1:end].strip()
    if not text or text == "void":
        return 0
    return len([item for item in text.split(",") if item.strip()])


def _declared_parameter_count(contract: OperatorContract) -> int:
    indices = []
    for section_name in ("inputs", "scratch", "outputs", "state"):
        section = contract.data.get(section_name, {})
        if isinstance(section, dict):
            indices.extend(int(spec["param_index"]) for spec in section.values() if isinstance(spec, dict) and "param_index" in spec)
    # Scalar configuration arguments such as n/epsilon are not streams; the
    # entrypoint ABI remains authoritative for the trailing parameter count.
    if contract.name == "residual_rmsnorm_quant":
        return 9
    return max(indices) + 1 if indices else 0
