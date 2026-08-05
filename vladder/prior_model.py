from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import random
import statistics
from typing import Any, Iterable

from .language_adapter import canonical_hash
from .prior_data import SPEED_BUCKETS, candidate_labels, dataset_statistics


PRIOR_MODEL_SCHEMA = "vladder-prior-model-v0"
PRIOR_RECOMMENDATION_SCHEMA = "vladder-prior-recommendation-v0"
DEFAULT_DIMENSION = 1024


def extract_prior_features(
    root: dict[str, Any], candidate: dict[str, Any], *, include_language: bool = False,
) -> tuple[dict[int, float], set[str]]:
    tokens: list[tuple[str, float]] = []
    summary = root.get("summary", {})
    for key in ("node_count", "edge_count", "obligation_count", "effect_count", "protocol_count", "claim_count"):
        value = float(summary.get(key, 0))
        tokens.append((f"root.numeric.{key}", math.log2(1.0 + max(0.0, value))))
    for kind, count in summary.get("node_kinds", {}).items(): tokens.append((f"root.node_kind.{kind}", float(count)))
    for operation, count in summary.get("operations", {}).items(): tokens.append((f"root.operation.{operation}", float(count)))
    for relation, count in summary.get("edge_relations", {}).items(): tokens.append((f"root.edge_relation.{relation}", float(count)))
    _flatten_tokens("graph.feature_inventory", root.get("canonical_graph", {}).get("feature_inventory", {}), tokens)
    _flatten_tokens("contract", root.get("contract", {}), tokens)
    _flatten_tokens("action", candidate.get("action", {}), tokens)
    _flatten_tokens("hardware", candidate.get("hardware", {}), tokens)
    _flatten_tokens("workload", candidate.get("workload", {}), tokens)
    family = str(candidate.get("action", {}).get("family", "unknown"))
    for kind in summary.get("node_kinds", {}): tokens.append((f"interaction.kind_family.{kind}.{family}", 1.0))
    parameters = candidate.get("action", {}).get("parameters", {})
    action_isa = str(parameters.get("isa", "portable"))
    variant = str(parameters.get("variant", "none"))
    semantic_family = str(root.get("contract", {}).get("semantic_family", "unknown"))
    tokens.append((f"interaction.contract_action_family.{semantic_family}.{family}", 1.0))
    tokens.append((f"interaction.contract_action_variant.{semantic_family}.{family}.{variant}", 1.0))
    architecture = str(candidate.get("hardware", {}).get("architecture", "unknown"))
    tokens.append((f"interaction.family_variant_architecture.{semantic_family}.{family}.{variant}.{architecture}", 1.0))
    for isa in candidate.get("hardware", {}).get("isa", []):
        tokens.append((f"interaction.hardware_action_isa.{isa}.{action_isa}", 1.0))
    if include_language:
        for provenance in root.get("provenance", []):
            tokens.append((f"diagnostic.language.{provenance.get('source_language', 'unknown')}", 1.0))
    sparse: dict[int, float] = defaultdict(float)
    categorical: set[str] = set()
    for token, value in tokens:
        index, sign = _hash_feature(token, DEFAULT_DIMENSION)
        sparse[index] += sign * value
        if abs(value - 1.0) < 1e-12: categorical.add(token)
    norm = math.sqrt(sum(value * value for value in sparse.values())) or 1.0
    return {index: value / norm for index, value in sparse.items()}, categorical


def train_prior_model(
    dataset: dict[str, Any], split: dict[str, Any], output_directory: Path, *,
    ensemble_size: int = 5, epochs: int = 80, learning_rate: float = 0.08, seed: int = 4242,
) -> dict[str, Any]:
    output_directory = output_directory.resolve(); output_directory.mkdir(parents=True, exist_ok=True)
    root_by_id = {item["root_id"]: item for item in dataset["roots"]}
    candidates = {item["candidate_id"]: item for item in dataset["candidates"]}
    labels = candidate_labels(dataset)
    train_ids = set(split["train"]); calibration_ids = set(split.get("calibration", []))
    train_examples = [(item, *extract_prior_features(root_by_id[item["root_id"]], item), labels[item["candidate_id"]]) for item in candidates.values() if item["root_id"] in train_ids]
    if not train_examples: raise ValueError("prior training split has no candidates")
    physical = [item for item in train_examples if item[3]["physical_label"]]
    if not physical: raise ValueError("prior training split has no physical candidate labels")
    pairs = _ranking_pairs(physical)
    if not pairs: raise ValueError("prior training data has no distinct within-root ranking pairs")
    members = []
    for member in range(ensemble_size):
        rng = random.Random(seed + member * 7919)
        sampled_pairs = [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
        rank = _train_pairwise(sampled_pairs, epochs, learning_rate, rng)
        sampled = [train_examples[rng.randrange(len(train_examples))] for _ in range(len(train_examples))]
        applicable = _train_binary([(item[1], 1.0 if item[3]["applicable"] else 0.0) for item in sampled], epochs, learning_rate, rng)
        proof = _train_binary([(item[1], 1.0 if item[3]["proof_pass"] else 0.0) for item in sampled], epochs, learning_rate, rng)
        outcomes = {
            bucket: _train_binary([(item[1], 1.0 if item[3]["speed_bucket"] == bucket else 0.0) for item in sampled if item[3]["physical_label"]], epochs, learning_rate, rng)
            for bucket in SPEED_BUCKETS
        }
        members.append({"rank": rank, "applicable": applicable, "proof": proof, "outcomes": outcomes})
    signatures = [{"root_id": root_id, "tokens": sorted(_root_signature(root_by_id[root_id]))} for root_id in sorted(train_ids)]
    hardware_profiles = sorted({canonical_hash(_hardware_capability(item[0]["hardware"])) for item in train_examples})
    calibration = _calibrate(members, root_by_id, candidates, labels, calibration_ids, signatures)
    statistics_payload = dataset_statistics(dataset)
    model = {
        "schema_version": PRIOR_MODEL_SCHEMA,
        "model_version": "vladder-prior-v0.linear-ensemble.1",
        "feature_schema": "semantic-flow-open-pooled-hash-v1",
        "dimension": DEFAULT_DIMENSION,
        "dataset_hash": dataset.get("dataset_hash", canonical_hash(dataset)),
        "split_hash": split.get("split_hash", canonical_hash(split)),
        "training": {"seed": seed, "epochs": epochs, "learning_rate": learning_rate, "ensemble_size": ensemble_size, "pair_count": len(pairs), "candidate_count": len(train_examples)},
        "members": members,
        "training_signatures": signatures,
        "hardware_profiles": hardware_profiles,
        "canonical_graph_schemas": sorted({root_by_id[root_id].get("canonical_graph", {}).get("schema_version", "unknown") for root_id in train_ids}),
        "calibration": calibration,
        "production_acceptance": statistics_payload["production_acceptance"],
        "authority": "search-order advisory only; legality, proof, measurement, and promotion remain external",
    }
    model["model_hash"] = canonical_hash({key: value for key, value in model.items() if key != "model_hash"})
    model_path = output_directory / "prior-model.json"
    model_path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    report = {
        "schema_version": "vladder-prior-training-v0", "status": "pass", "model": str(model_path),
        "model_hash": model["model_hash"], "dataset_hash": model["dataset_hash"],
        "pilot_model_ready": True, "production_model_status": model["production_acceptance"]["status"],
        "statistics": statistics_payload, "training": model["training"], "calibration": calibration,
        "claim_boundary": "deterministic pooled-graph pilot; relational graph transformer and production acceptance require the minimum corpus",
    }
    (output_directory / "training-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def load_prior_model(path: Path) -> dict[str, Any]:
    model = json.loads(path.read_text())
    if model.get("schema_version") != PRIOR_MODEL_SCHEMA: raise ValueError("unsupported prior model schema")
    expected = canonical_hash({key: value for key, value in model.items() if key != "model_hash"})
    if model.get("model_hash") != expected: raise ValueError("prior model hash mismatch")
    return model


def recommend_candidates(
    model: dict[str, Any], root: dict[str, Any], candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not candidates: raise ValueError("prior recommendation requires candidates")
    if any(item["root_id"] != root["root_id"] for item in candidates): raise ValueError("candidate/root identity mismatch")
    rows = []
    root_tokens = _root_signature(root)
    ood_distance = min((_jaccard_distance(root_tokens, set(item["tokens"])) for item in model["training_signatures"]), default=1.0)
    threshold = float(model["calibration"].get("ood_distance_threshold", 0.55))
    hardware_unseen = any(canonical_hash(_hardware_capability(item["hardware"])) not in model["hardware_profiles"] for item in candidates)
    graph_schema_unseen = root.get("canonical_graph", {}).get("schema_version", "unknown") not in model.get("canonical_graph_schemas", [])
    for candidate in candidates:
        features, _ = extract_prior_features(root, candidate)
        rank_scores = [_dot(member["rank"], features) for member in model["members"]]
        applicability = statistics.fmean(_sigmoid(_dot(member["applicable"], features)) for member in model["members"])
        proof_pass = statistics.fmean(_sigmoid(_dot(member["proof"], features)) for member in model["members"])
        bucket_logits = {bucket: statistics.fmean(_dot(member["outcomes"][bucket], features) for member in model["members"]) for bucket in SPEED_BUCKETS}
        distribution = _softmax(bucket_logits, float(model["calibration"].get("temperature", 1.0)))
        uncertainty = statistics.pstdev(rank_scores) if len(rank_scores) > 1 else 0.0
        contributions = _top_contributions(model["members"], features)
        rows.append({
            "candidate_id": candidate["candidate_id"], "family": candidate["action"]["family"], "baseline": candidate["baseline"],
            "rank_score": statistics.fmean(rank_scores), "uncertainty": uncertainty,
            "applicability_probability": applicability, "likely_provable": proof_pass,
            "proof_risk": {"likely_provable": proof_pass, "failure_or_unknown": 1.0 - proof_pass},
            "outcome_distribution": distribution,
            "search_outcome": "benchmark_top_k" if candidate["baseline"] else _search_outcome(applicability, statistics.fmean(rank_scores), uncertainty),
            "contributing_features": _advisory_features(root, candidate),
            "contributing_feature_indices": contributions,
        })
    rows.sort(key=lambda item: (-item["rank_score"], item["candidate_id"]))
    uncertainty_threshold = float(model["calibration"].get("uncertainty_threshold", 1.0))
    high_uncertainty = all(item["uncertainty"] > uncertainty_threshold for item in rows)
    abstain_reasons = []
    if ood_distance > threshold: abstain_reasons.append("semantic_graph_out_of_distribution")
    if hardware_unseen: abstain_reasons.append("unseen_hardware_capability_profile")
    if graph_schema_unseen: abstain_reasons.append("unseen_canonical_graph_schema")
    if high_uncertainty: abstain_reasons.append("ensemble_uncertainty_above_calibrated_threshold")
    if abstain_reasons:
        for item in rows:
            if not item["baseline"]: item["search_outcome"] = "abstain_out_of_distribution"
    grammar: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in rows: grammar[item["family"]].append(item)
    grammar_rows = [{
        "family": family,
        "priority": max(item["rank_score"] for item in values),
        "uncertainty": statistics.fmean(item["uncertainty"] for item in values),
        "applicability_probability": max(item["applicability_probability"] for item in values),
        "expected_search_value": _grammar_value(values),
    } for family, values in grammar.items()]
    grammar_rows.sort(key=lambda item: (-item["priority"], item["family"]))
    report = {
        "schema_version": PRIOR_RECOMMENDATION_SCHEMA,
        "model_version": model["model_version"], "model_hash": model["model_hash"], "dataset_hash": model["dataset_hash"],
        "root_id": root["root_id"], "distribution_status": {"in_distribution": not abstain_reasons, "graph_distance": ood_distance, "threshold": threshold, "hardware_seen": not hardware_unseen},
        "grammar_recommendations": grammar_rows, "candidate_recommendations": rows,
        "abstention": {"required": bool(abstain_reasons), "reasons": abstain_reasons, "fallback": "existing_exhaustive_or_heuristic_search"},
        "authority": "priority only; this is not legality, equivalence, runtime, or promotion evidence",
    }
    report["recommendation_hash"] = canonical_hash(report)
    return report


def _ranking_pairs(examples: list[tuple[Any, dict[int, float], set[str], dict[str, Any]]]) -> list[tuple[dict[int, float], dict[int, float], float]]:
    by_context: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for item in examples:
        candidate = item[0]
        by_context[(candidate["root_id"], candidate["hardware_id"], candidate["workload_id"])].append(item)
    pairs = []
    for values in by_context.values():
        for left_index, left in enumerate(values):
            for right in values[left_index + 1:]:
                delta = left[3]["utility"] - right[3]["utility"]
                if abs(delta) < 1e-6: continue
                winner, loser = (left, right) if delta > 0 else (right, left)
                pairs.append((winner[1], loser[1], min(2.0, max(0.1, abs(delta) * 10.0))))
    return pairs


def _train_pairwise(pairs: list[tuple[dict[int, float], dict[int, float], float]], epochs: int, rate: float, rng: random.Random) -> list[float]:
    weights = [0.0] * DEFAULT_DIMENSION
    for epoch in range(epochs):
        rng.shuffle(pairs)
        step = rate / math.sqrt(1.0 + epoch)
        for winner, loser, confidence in pairs:
            difference = _subtract(winner, loser)
            gradient = _sigmoid(-_dot(weights, difference)) * confidence
            for index, value in difference.items(): weights[index] += step * (gradient * value - 1e-5 * weights[index])
    return weights


def _train_binary(examples: list[tuple[dict[int, float], float]], epochs: int, rate: float, rng: random.Random) -> list[float]:
    weights = [0.0] * DEFAULT_DIMENSION
    if not examples: return weights
    positives = sum(label >= 0.5 for _, label in examples); negatives = len(examples) - positives
    positive_weight = len(examples) / (2.0 * positives) if positives else 1.0
    negative_weight = len(examples) / (2.0 * negatives) if negatives else 1.0
    for epoch in range(epochs):
        rng.shuffle(examples); step = rate / math.sqrt(1.0 + epoch)
        for features, label in examples:
            class_weight = positive_weight if label >= 0.5 else negative_weight
            error = (label - _sigmoid(_dot(weights, features))) * class_weight
            for index, value in features.items(): weights[index] += step * (error * value - 1e-5 * weights[index])
    return weights


def _calibrate(members: list[dict[str, Any]], roots: dict[str, Any], candidates: dict[str, Any], labels: dict[str, Any], calibration_ids: set[str], signatures: list[dict[str, Any]]) -> dict[str, Any]:
    distances = []; uncertainties = []; residuals = []
    for candidate in candidates.values():
        if candidate["root_id"] not in calibration_ids: continue
        features, _ = extract_prior_features(roots[candidate["root_id"]], candidate)
        scores = [_dot(member["rank"], features) for member in members]
        uncertainties.append(statistics.pstdev(scores) if len(scores) > 1 else 0.0)
        if labels[candidate["candidate_id"]]["physical_label"]:
            residuals.append(abs(statistics.fmean(scores) - labels[candidate["candidate_id"]]["utility"]))
    for root_id in calibration_ids:
        token_set = _root_signature(roots[root_id])
        distances.append(min((_jaccard_distance(token_set, set(item["tokens"])) for item in signatures), default=1.0))
    return {
        "method": "held-out-root ensemble-plus-distance-v0",
        "ood_distance_threshold": _quantile(distances, 0.95, 0.55),
        "uncertainty_threshold": _quantile(uncertainties, 0.95, 1.0),
        "conformal_residual_q95": _quantile(residuals, 0.95, 1.0),
        "temperature": 1.0,
        "calibration_root_count": len(calibration_ids),
    }


def _root_signature(root: dict[str, Any]) -> set[str]:
    result = {f"kind:{key}" for key in root.get("summary", {}).get("node_kinds", {})}
    result.update(f"contract:{key}" for key in root.get("contract", {}))
    result.update(f"graph:{key}" for key in root.get("canonical_graph", {}))
    return result


def _hardware_capability(hardware: dict[str, Any]) -> dict[str, Any]:
    return {"architecture": hardware.get("architecture"), "vendor": hardware.get("vendor"), "isa": sorted(hardware.get("isa", [])), "device_class": hardware.get("device_class", "cpu")}


def _flatten_tokens(prefix: str, value: Any, output: list[tuple[str, float]]) -> None:
    if isinstance(value, dict):
        for key, item in sorted(value.items()): _flatten_tokens(f"{prefix}.{key}", item, output)
    elif isinstance(value, list):
        for item in value: _flatten_tokens(prefix, item, output)
    elif isinstance(value, bool): output.append((f"{prefix}={str(value).lower()}", 1.0))
    elif isinstance(value, (int, float)) and math.isfinite(float(value)):
        output.append((f"{prefix}.numeric", math.copysign(math.log2(1.0 + abs(float(value))), float(value))))
    elif value is not None: output.append((f"{prefix}={value}", 1.0))


def _hash_feature(token: str, dimension: int) -> tuple[int, float]:
    digest = __import__("hashlib").sha256(token.encode()).digest()
    return int.from_bytes(digest[:8], "little") % dimension, 1.0 if digest[8] & 1 else -1.0


def _dot(weights: list[float], features: dict[int, float]) -> float:
    return sum(weights[index] * value for index, value in features.items())


def _subtract(left: dict[int, float], right: dict[int, float]) -> dict[int, float]:
    result = dict(left)
    for index, value in right.items(): result[index] = result.get(index, 0.0) - value
    return {index: value for index, value in result.items() if value}


def _sigmoid(value: float) -> float:
    if value >= 0: return 1.0 / (1.0 + math.exp(-min(value, 60.0)))
    exponent = math.exp(max(value, -60.0)); return exponent / (1.0 + exponent)


def _softmax(logits: dict[str, float], temperature: float) -> dict[str, float]:
    scaled = {key: value / max(0.05, temperature) for key, value in logits.items()}; maximum = max(scaled.values())
    values = {key: math.exp(value - maximum) for key, value in scaled.items()}; total = sum(values.values())
    return {key: value / total for key, value in values.items()}


def _jaccard_distance(left: set[str], right: set[str]) -> float:
    union = left | right
    return 0.0 if not union else 1.0 - len(left & right) / len(union)


def _quantile(values: list[float], q: float, default: float) -> float:
    if not values: return default
    ordered = sorted(values); index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1)); return ordered[index]


def _top_contributions(members: list[dict[str, Any]], features: dict[int, float]) -> list[dict[str, float | int]]:
    mean_weights = [statistics.fmean(member["rank"][index] for member in members) for index in range(DEFAULT_DIMENSION)]
    values = sorted(((index, mean_weights[index] * value) for index, value in features.items()), key=lambda item: -abs(item[1]))[:8]
    return [{"feature_index": index, "contribution": value} for index, value in values]


def _search_outcome(applicability: float, rank_score: float, uncertainty: float) -> str:
    if applicability < 0.35: return "do_not_expand"
    if uncertainty > 1.0: return "expand_low_priority"
    if rank_score > 0.25: return "benchmark_top_k"
    if rank_score > 0.0: return "expand_high_priority"
    return "expand_low_priority"


def _grammar_value(values: list[dict[str, Any]]) -> str:
    if max(item["applicability_probability"] for item in values) < 0.35: return "low"
    best = max(item["rank_score"] for item in values)
    return "high" if best > 0.25 else "medium" if best > 0.0 else "low"


def _advisory_features(root: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    features = [
        f"semantic_family:{root.get('contract', {}).get('semantic_family', 'unknown')}",
        f"action_family:{candidate.get('action', {}).get('family', 'unknown')}",
        f"architecture:{candidate.get('hardware', {}).get('architecture', 'unknown')}",
    ]
    features.extend(f"node_kind:{kind}" for kind in sorted(root.get("summary", {}).get("node_kinds", {}))[:5])
    features.extend(f"isa:{isa}" for isa in sorted(candidate.get("hardware", {}).get("isa", []))[:3])
    return features
