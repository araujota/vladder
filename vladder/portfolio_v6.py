from __future__ import annotations

from dataclasses import asdict, dataclass
import random
from typing import Any

from .statistics_v3 import empirical_quantile


@dataclass(frozen=True)
class WorkloadResult:
    name: str
    weight: float
    baseline_tokens_per_second: float
    candidate_tokens_per_second: float
    relative_performance: float
    minimum_relative_performance: float
    accepted: bool
    improvement_95: tuple[float, float]


def rank_portfolio(manifest: dict[str, Any], measurements: dict[str, Any], *, bootstrap_rounds: int = 4000, seed: int = 0) -> dict[str, Any]:
    workloads = manifest.get("workloads")
    if not isinstance(workloads, dict) or not workloads:
        raise ValueError("portfolio manifest requires workloads")
    total_weight = sum(float(item["weight"]) for item in workloads.values())
    if abs(total_weight - 1.0) > 1e-9:
        raise ValueError("portfolio workload weights must sum to 1")
    rows: list[WorkloadResult] = []
    portfolio_improvement_samples: list[float] = []
    rng = random.Random(seed)
    normalized: dict[str, tuple[list[float], list[float], float, float]] = {}
    for name, spec in workloads.items():
        result = measurements.get(name)
        if not isinstance(result, dict):
            raise ValueError(f"missing measurements for {name}")
        baseline = _samples(result, "baseline")
        candidate = _samples(result, "candidate")
        normalized[name] = (baseline, candidate, float(spec["weight"]), float(spec.get("minimum_relative_performance", 0.0)))
    for _ in range(bootstrap_rounds):
        score = 0.0
        for baseline, candidate, weight, _ in normalized.values():
            base_mean = sum(baseline[rng.randrange(len(baseline))] for _ in baseline) / len(baseline)
            cand_mean = sum(candidate[rng.randrange(len(candidate))] for _ in candidate) / len(candidate)
            score += weight * (cand_mean / base_mean - 1.0) * 100.0
        portfolio_improvement_samples.append(score)
    for name, (baseline, candidate, weight, minimum) in normalized.items():
        base_mean = sum(baseline) / len(baseline)
        cand_mean = sum(candidate) / len(candidate)
        ratio = cand_mean / base_mean
        local_rng = random.Random(f"{seed}:{name}")
        improvement_samples = []
        for _ in range(bootstrap_rounds):
            base = sum(baseline[local_rng.randrange(len(baseline))] for _ in baseline) / len(baseline)
            cand = sum(candidate[local_rng.randrange(len(candidate))] for _ in candidate) / len(candidate)
            improvement_samples.append((cand / base - 1.0) * 100.0)
        interval = (empirical_quantile(improvement_samples, 0.025), empirical_quantile(improvement_samples, 0.975))
        rows.append(WorkloadResult(name, weight, base_mean, cand_mean, ratio, minimum, ratio >= minimum, interval))
    portfolio_point = sum(row.weight * (row.relative_performance - 1.0) * 100.0 for row in rows)
    portfolio_ci = [empirical_quantile(portfolio_improvement_samples, 0.025), empirical_quantile(portfolio_improvement_samples, 0.975)]
    required_gain = float(manifest.get("minimum_portfolio_improvement_percent", 5.0))
    accepted = all(row.accepted for row in rows) and portfolio_ci[0] >= required_gain
    return {
        "schema_version": "vladder-portfolio-rank-v6.0",
        "classification": "accepted" if accepted else ("statistical_tie" if portfolio_ci[0] <= required_gain <= portfolio_ci[1] else "rejected"),
        "accepted": accepted,
        "portfolio_improvement_percent": portfolio_point,
        "portfolio_improvement_95": portfolio_ci,
        "required_improvement_percent": required_gain,
        "workloads": [asdict(row) for row in rows],
        "bootstrap_rounds": bootstrap_rounds,
        "bootstrap_seed": seed,
        "rule": "no aggregate score may conceal a workload below its declared performance floor",
    }


def _samples(result: dict[str, Any], key: str) -> list[float]:
    values = [float(value) for value in result.get(key, [])]
    if len(values) < 2 or any(value <= 0.0 for value in values):
        raise ValueError(f"{key} requires at least two positive independent-process samples")
    return values
