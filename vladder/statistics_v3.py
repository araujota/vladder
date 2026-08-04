from __future__ import annotations

import math
import random
import bisect
from typing import Any


def empirical_quantile(samples: list[float], probability: float) -> float:
    if not samples:
        raise ValueError("quantile requires samples")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0,1]")
    ordered = sorted(samples)
    return _quantile_sorted(ordered, probability)


def _quantile_sorted(ordered: list[float], probability: float) -> float:
    rank = probability * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    fraction = rank - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def summarize_samples(process_samples: list[list[float]], bootstrap_rounds: int = 1000, seed: int = 0) -> dict[str, Any]:
    if not process_samples or any(not block for block in process_samples):
        raise ValueError("each independent process must provide samples")
    flat = [sample for block in process_samples for sample in block]
    sorted_blocks = [sorted(block) for block in process_samples]
    universe = sorted(set(flat))
    probabilities = {"p50": 0.5, "p90": 0.9, "p99": 0.99, "p99_9": 0.999, "p99_99": 0.9999}
    ordered_flat = sorted(flat)
    quantiles = {name: _quantile_sorted(ordered_flat, probability) for name, probability in probabilities.items()}
    rng = random.Random(seed)
    bootstrap = {name: [] for name in probabilities}
    for _ in range(bootstrap_rounds):
        multiplicities = [0] * len(sorted_blocks)
        for _ in sorted_blocks:
            multiplicities[rng.randrange(len(sorted_blocks))] += 1
        for name, probability in probabilities.items():
            bootstrap[name].append(_weighted_quantile(sorted_blocks, multiplicities, universe, probability))
    intervals = {name: [empirical_quantile(values, 0.025), empirical_quantile(values, 0.975)] for name, values in bootstrap.items()}
    return {
        "sample_count": len(flat),
        "process_count": len(process_samples),
        **quantiles,
        "maximum": max(flat),
        "mean": sum(flat) / len(flat),
        "bootstrap_95": intervals,
        "bootstrap_rounds": bootstrap_rounds,
        "bootstrap_seed": seed,
        "p99_99_supported": len(flat) >= 10000,
    }


def rank_hft(baseline: dict[str, float], candidate: dict[str, float]) -> dict[str, Any]:
    improvements = {metric: (baseline[metric] / candidate[metric] - 1.0) * 100.0 for metric in ("p50", "p99_9")}
    p99_99_regression = (candidate["p99_99"] / baseline["p99_99"] - 1.0) * 100.0
    p50_bounds = _improvement_bounds(baseline, candidate, "p50")
    p99_9_bounds = _improvement_bounds(baseline, candidate, "p99_9")
    p99_99_regression_bounds = _regression_bounds(baseline, candidate, "p99_99")
    # Interrupt outliers make a 99.99% interval-of-intervals unstable even with
    # tens of thousands of samples. Preserve the explicit point-estimate tail
    # constraint while requiring lower confidence bounds for the two improvement
    # thresholds.
    accepted = p50_bounds[0] >= 10.0 and p99_9_bounds[0] >= 5.0 and p99_99_regression <= 1.0
    tie = not accepted and p50_bounds[0] < 10.0 <= p50_bounds[1]
    return {
        "accepted": accepted, "classification": "accepted" if accepted else ("statistical_tie" if tie else "rejected"),
        "p50_improvement_pct": improvements["p50"], "p50_improvement_95": p50_bounds,
        "p99_9_improvement_pct": improvements["p99_9"], "p99_9_improvement_95": p99_9_bounds,
        "p99_99_regression_pct": p99_99_regression, "p99_99_regression_95": p99_99_regression_bounds,
    }


def _improvement_bounds(baseline: dict[str, Any], candidate: dict[str, Any], metric: str) -> list[float]:
    baseline_ci = baseline.get("bootstrap_95", {}).get(metric, [baseline[metric], baseline[metric]])
    candidate_ci = candidate.get("bootstrap_95", {}).get(metric, [candidate[metric], candidate[metric]])
    return [(baseline_ci[0] / candidate_ci[1] - 1.0) * 100.0, (baseline_ci[1] / candidate_ci[0] - 1.0) * 100.0]


def _regression_bounds(baseline: dict[str, Any], candidate: dict[str, Any], metric: str) -> list[float]:
    baseline_ci = baseline.get("bootstrap_95", {}).get(metric, [baseline[metric], baseline[metric]])
    candidate_ci = candidate.get("bootstrap_95", {}).get(metric, [candidate[metric], candidate[metric]])
    return [(candidate_ci[0] / baseline_ci[1] - 1.0) * 100.0, (candidate_ci[1] / baseline_ci[0] - 1.0) * 100.0]


def _weighted_quantile(sorted_blocks: list[list[float]], multiplicities: list[int], universe: list[float], probability: float) -> float:
    total = sum(len(block) * multiplicity for block, multiplicity in zip(sorted_blocks, multiplicities))
    rank = probability * (total - 1)
    low, high = int(math.floor(rank)), int(math.ceil(rank))

    def kth(index: int) -> float:
        left, right = 0, len(universe) - 1
        while left < right:
            middle = (left + right) // 2
            value = universe[middle]
            count = sum(multiplicity * bisect.bisect_right(block, value) for block, multiplicity in zip(sorted_blocks, multiplicities))
            if count > index:
                right = middle
            else:
                left = middle + 1
        return universe[left]

    low_value = kth(low)
    if low == high:
        return low_value
    fraction = rank - low
    return low_value * (1.0 - fraction) + kth(high) * fraction
