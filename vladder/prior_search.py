from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import random
from typing import Any

from .language_adapter import canonical_hash
from .prior_data import candidate_labels
from .prior_model import recommend_candidates


def select_search_budget(
    recommendation: dict[str, Any], candidates: list[dict[str, Any]], *, budget: int,
    exploration_fraction: float = 0.2, seed: int = 4242, fallback: str = "exhaustive",
) -> dict[str, Any]:
    if not 0.1 <= exploration_fraction <= 0.5: raise ValueError("exploration_fraction must be between 0.1 and 0.5")
    baseline = [item for item in candidates if item.get("baseline")]
    if len(baseline) != 1: raise ValueError("candidate set must contain exactly one baseline")
    if budget < 1: raise ValueError("search budget must retain the baseline")
    ranking = {item["candidate_id"]: item for item in recommendation["candidate_recommendations"]}
    if set(ranking) != {item["candidate_id"] for item in candidates}: raise ValueError("recommendation/candidate identity mismatch")
    if recommendation["abstention"]["required"]:
        selected = list(candidates) if fallback == "exhaustive" else [baseline[0], *[item for item in candidates if not item.get("baseline")][:max(0, budget - 1)]]
        reason = "model_abstained_exhaustive_fallback" if fallback == "exhaustive" else "model_abstained_heuristic_fallback"
        return _decision(recommendation, candidates, selected, budget, exploration_fraction, seed, reason, {})
    budget = min(budget, len(candidates))
    remaining_slots = budget - 1
    exploration_slots = (
        min(remaining_slots - 1, max(1, math.ceil(remaining_slots * exploration_fraction)))
        if remaining_slots >= 2 else 0
    )
    exploit_slots = remaining_slots - exploration_slots
    nonbaseline = [item for item in candidates if not item.get("baseline")]
    ordered = sorted(nonbaseline, key=lambda item: (-ranking[item["candidate_id"]]["rank_score"], item["candidate_id"]))
    selected = [baseline[0], *ordered[:exploit_slots]]
    selected_ids = {item["candidate_id"] for item in selected}
    pool = [item for item in nonbaseline if item["candidate_id"] not in selected_ids]
    family_counts: dict[str, int] = defaultdict(int)
    for item in selected: family_counts[str(item["action"]["family"])] += 1
    pool.sort(key=lambda item: (
        family_counts[str(item["action"]["family"])],
        -ranking[item["candidate_id"]]["uncertainty"],
        _seed_key(seed, item["candidate_id"]),
    ))
    exploration = pool[:exploration_slots]
    selected.extend(exploration)
    reasons = {item["candidate_id"]: "baseline_guarantee" for item in baseline}
    reasons.update({item["candidate_id"]: "model_priority" for item in ordered[:exploit_slots]})
    reasons.update({item["candidate_id"]: "exploration_underrepresented_or_uncertain" for item in exploration})
    return _decision(recommendation, candidates, selected, budget, exploration_fraction, seed, "model_guided_budget", reasons)


def shadow_evaluate(
    model: dict[str, Any], dataset: dict[str, Any], root_ids: list[str], *,
    budget_fraction: float = 0.10, minimum_budget: int = 2, exploration_fraction: float = 0.2, seed: int = 4242,
) -> dict[str, Any]:
    roots = {item["root_id"]: item for item in dataset["roots"]}
    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in dataset["candidates"]:
        if item["root_id"] in root_ids: by_root[item["root_id"]].append(item)
    labels = candidate_labels(dataset)
    rows = []
    winner_hits = 0; baseline_suppression = 0; total_full = 0; total_selected = 0; regrets = []
    recall_at_1 = 0; recall_at_5 = 0; recall_at_10pct = 0
    grammar_recall_at_3 = 0; ndcg_values = []; pairwise_values = []; calibration_pairs = []; abstentions = 0
    applicability_pairs = []
    for ordinal, (root_id, candidates) in enumerate(sorted(by_root.items())):
        measured = [item for item in candidates if labels[item["candidate_id"]]["physical_label"]]
        if len(measured) < 2 or not any(item.get("baseline") for item in measured): continue
        recommendation = recommend_candidates(model, roots[root_id], measured)
        abstentions += recommendation["abstention"]["required"]
        ranked_ids = [item["candidate_id"] for item in recommendation["candidate_recommendations"]]
        winner = max(measured, key=lambda item: (labels[item["candidate_id"]]["utility"], item["candidate_id"]))
        winner_index = ranked_ids.index(winner["candidate_id"])
        recall_at_1 += winner_index < 1; recall_at_5 += winner_index < min(5, len(measured)); recall_at_10pct += winner_index < max(1, math.ceil(len(measured) * 0.10))
        winner_family = winner["action"]["family"]
        grammar_recall_at_3 += winner_family in [item["family"] for item in recommendation["grammar_recommendations"][:3]]
        utilities = {item["candidate_id"]: labels[item["candidate_id"]]["utility"] for item in measured}
        ndcg_values.append(_ndcg(ranked_ids, utilities))
        pairwise_values.append(_pairwise_accuracy(ranked_ids, utilities))
        for item in recommendation["candidate_recommendations"]:
            probability = sum(item["outcome_distribution"].get(bucket, 0.0) for bucket in ("win_3_to_10", "win_10_to_50", "win_gt_50"))
            calibration_pairs.append((probability, 1.0 if utilities[item["candidate_id"]] > 0.03 else 0.0))
            applicability_pairs.append((item["applicability_probability"] >= 0.5, labels[item["candidate_id"]]["applicable"]))
        exploitation = math.ceil((len(measured) - 1) * budget_fraction)
        budget = min(len(measured), max(minimum_budget, 1 + math.ceil(exploitation / max(0.5, 1.0 - exploration_fraction))))
        decision = select_search_budget(recommendation, measured, budget=budget, exploration_fraction=exploration_fraction, seed=seed + ordinal)
        selected_ids = set(decision["selected_candidate_ids"])
        baseline_id = next(item["candidate_id"] for item in measured if item["baseline"])
        baseline_suppression += baseline_id not in selected_ids
        hit = winner["candidate_id"] in selected_ids; winner_hits += hit
        best_selected = max(labels[item["candidate_id"]]["utility"] for item in measured if item["candidate_id"] in selected_ids)
        regret = labels[winner["candidate_id"]]["utility"] - best_selected; regrets.append(regret)
        total_full += len(measured); total_selected += len(selected_ids)
        rows.append({
            "root_id": root_id, "candidate_count": len(measured), "budget": budget,
            "winner_id": winner["candidate_id"], "winner_rank": winner_index + 1,
            "winner_selected": hit, "regret": regret, "abstained": recommendation["abstention"]["required"],
            "decision_hash": decision["decision_hash"],
        })
    count = len(rows)
    report = {
        "schema_version": "vladder-prior-shadow-evaluation-v0",
        "status": "pass" if count else "insufficient_evaluation_roots",
        "root_count": count,
        "winner_recall_at_budget": winner_hits / count if count else 0.0,
        "recall_at_1": recall_at_1 / count if count else 0.0,
        "recall_at_5": recall_at_5 / count if count else 0.0,
        "recall_at_10_percent": recall_at_10pct / count if count else 0.0,
        "grammar_recall_at_3": grammar_recall_at_3 / count if count else 0.0,
        "mean_ndcg": sum(ndcg_values) / len(ndcg_values) if ndcg_values else 0.0,
        "mean_pairwise_accuracy": sum(pairwise_values) / len(pairwise_values) if pairwise_values else 0.0,
        "expected_calibration_error": _ece(calibration_pairs),
        "applicability_macro_f1": _binary_macro_f1(applicability_pairs),
        "abstention_rate": abstentions / count if count else 0.0,
        "measurement_reduction_factor": total_full / total_selected if total_selected else 0.0,
        "proof_attempt_reduction_factor": total_full / total_selected if total_selected else 0.0,
        "compilation_attempt_reduction_factor": total_full / total_selected if total_selected else 0.0,
        "median_regret": sorted(regrets)[len(regrets) // 2] if regrets else None,
        "maximum_regret": max(regrets) if regrets else None,
        "baseline_suppression_count": baseline_suppression,
        "rows": rows,
        "authority": "counterfactual shadow replay only; no executed search was pruned",
    }
    report["pilot_thresholds"] = {
        "winner_recall_95_percent": report["recall_at_10_percent"] >= 0.95,
        "measurement_reduction_5x": report["measurement_reduction_factor"] >= 5.0,
        "baseline_never_suppressed": baseline_suppression == 0,
    }
    report["evaluation_hash"] = canonical_hash(report)
    return report


def write_search_decision(report: dict[str, Any], output: Path) -> None:
    output.resolve().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _decision(recommendation: dict[str, Any], candidates: list[dict[str, Any]], selected: list[dict[str, Any]], budget: int, exploration_fraction: float, seed: int, mode: str, reasons: dict[str, str]) -> dict[str, Any]:
    selected_ids = [item["candidate_id"] for item in selected]
    report = {
        "schema_version": "vladder-prior-search-decision-v0",
        "model_hash": recommendation["model_hash"], "dataset_hash": recommendation["dataset_hash"],
        "recommendation_hash": recommendation["recommendation_hash"], "root_id": recommendation["root_id"],
        "mode": mode, "requested_budget": budget, "effective_budget": len(selected_ids),
        "exploration_fraction": exploration_fraction, "seed": seed,
        "selected_candidate_ids": selected_ids,
        "deferred_candidate_ids": sorted(item["candidate_id"] for item in candidates if item["candidate_id"] not in set(selected_ids)),
        "selection_reasons": reasons,
        "baseline_retained": any(item.get("baseline") and item["candidate_id"] in selected_ids for item in candidates),
        "abstention": recommendation["abstention"],
        "authority": "evaluation order only; every selected candidate still requires deterministic vLadder gates",
    }
    report["decision_hash"] = canonical_hash(report)
    return report


def _seed_key(seed: int, identifier: str) -> str:
    return canonical_hash({"seed": seed, "candidate_id": identifier})


def _ndcg(ranked_ids: list[str], utilities: dict[str, float]) -> float:
    floor = min(utilities.values())
    def score(order: list[str]) -> float:
        return sum((2.0 ** max(0.0, utilities[identifier] - floor) - 1.0) / math.log2(index + 2.0) for index, identifier in enumerate(order))
    ideal = sorted(ranked_ids, key=lambda identifier: (-utilities[identifier], identifier))
    denominator = score(ideal)
    return score(ranked_ids) / denominator if denominator else 1.0


def _pairwise_accuracy(ranked_ids: list[str], utilities: dict[str, float]) -> float:
    correct = 0; total = 0
    for left_index, left in enumerate(ranked_ids):
        for right in ranked_ids[left_index + 1:]:
            if abs(utilities[left] - utilities[right]) < 1e-12: continue
            total += 1; correct += utilities[left] > utilities[right]
    return correct / total if total else 1.0


def _ece(values: list[tuple[float, float]], bins: int = 10) -> float:
    if not values: return 0.0
    total = len(values); error = 0.0
    for index in range(bins):
        low = index / bins; high = (index + 1) / bins
        bucket = [(probability, label) for probability, label in values if low <= probability < high or index == bins - 1 and probability == 1.0]
        if bucket:
            confidence = sum(item[0] for item in bucket) / len(bucket); accuracy = sum(item[1] for item in bucket) / len(bucket)
            error += len(bucket) / total * abs(confidence - accuracy)
    return error


def _binary_macro_f1(values: list[tuple[bool, bool]]) -> float:
    if not values: return 0.0
    scores = []
    for positive in (False, True):
        true_positive = sum(predicted == positive and actual == positive for predicted, actual in values)
        false_positive = sum(predicted == positive and actual != positive for predicted, actual in values)
        false_negative = sum(predicted != positive and actual == positive for predicted, actual in values)
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(2 * true_positive / denominator if denominator else 1.0)
    return sum(scores) / len(scores)
