from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Any


class VerificationPolicy(str, Enum):
    """Promotion policies for generated source replacements."""

    STRICT = "strict"
    BALANCED = "balanced"
    EXPLORATORY = "exploratory"


@dataclass(frozen=True)
class PromotionDecision:
    promotable: bool
    policy: VerificationPolicy
    reasons: tuple[str, ...]
    evidence: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "promotable": self.promotable,
            "policy": self.policy.value,
            "reasons": list(self.reasons),
            "evidence": self.evidence,
        }


def _nested_status(candidate: Mapping[str, Any], key: str) -> str:
    value = candidate.get(key)
    if isinstance(value, Mapping):
        return str(value.get("status", "missing"))
    return "missing"


def evaluate_promotion(
    candidate: Mapping[str, Any] | None,
    policy: VerificationPolicy | str,
    minimum_speedup_pct: float,
) -> PromotionDecision:
    selected = VerificationPolicy(policy)
    if candidate is None:
        return PromotionDecision(False, selected, ("no candidate passed execution",), {})

    candidate_name = str(candidate.get("candidate", "unknown"))
    proof = _nested_status(candidate, "proof")
    memory = _nested_status(candidate, "memory_proof")
    alive2 = _nested_status(candidate, "alive2")
    execution = str(candidate.get("status", "missing"))
    differential = "passed" if execution == "PASS" else "failed"
    speedup = float(candidate.get("speedup_vs_baseline_pct", 0.0) or 0.0)
    evidence = {
        "candidate": candidate_name,
        "schema_or_smt_proof": proof,
        "memory_proof": memory,
        "alive2": alive2,
        "differential_execution": differential,
        "speedup_vs_baseline_pct": f"{speedup:.6f}",
        "minimum_speedup_pct": f"{minimum_speedup_pct:.6f}",
    }

    reasons: list[str] = []
    if candidate_name == "baseline_o3":
        reasons.append("the baseline remains the fastest verified implementation")
    if execution != "PASS":
        reasons.append("candidate did not pass differential execution")
    if memory != "proved":
        reasons.append(f"memory legality is {memory}")
    if speedup < minimum_speedup_pct:
        reasons.append(f"measured speedup {speedup:.3f}% is below {minimum_speedup_pct:.3f}%")

    if selected is VerificationPolicy.STRICT:
        if proof != "PROVED":
            reasons.append(f"schema/SMT proof is {proof}")
        if alive2 != "correct":
            reasons.append(f"Alive2 translation validation is {alive2}")
    elif selected is VerificationPolicy.BALANCED:
        if proof != "PROVED" and alive2 != "correct":
            reasons.append("neither schema/SMT nor Alive2 established equivalence")
    else:
        reasons.append("exploratory policy never promotes source replacements")

    return PromotionDecision(not reasons, selected, tuple(reasons), evidence)
