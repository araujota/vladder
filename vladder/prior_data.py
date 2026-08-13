from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable

from .language_adapter import canonical_hash


PRIOR_DATASET_SCHEMA = "vladder-prior-dataset-v0"
ROOT_SCHEMA = "vladder-prior-root-v0"
CANDIDATE_SCHEMA = "vladder-prior-candidate-v0"
OBSERVATION_SCHEMA = "vladder-prior-observation-v0"
TRAINING_TEMPLATE_SCHEMA = "vladder-prior-training-template-v1"
CANONICAL_GRAPH_SCHEMA = "prior-canonical-semantic-graph-v1"

SEMANTIC_OUTCOMES = frozenset({
    "inapplicable", "missing_contract", "semantic_mismatch", "illegal",
    "proof_failed", "proof_unknown", "proof_passed",
})
PHYSICAL_OUTCOMES = frozenset({
    "compiler_identical", "measured_regression", "statistical_tie",
    "small_win_below_floor", "material_regional_win", "composed_regression",
    "composed_win", "resource_regression",
})
SEARCH_OUTCOMES = frozenset({
    "do_not_expand", "expand_low_priority", "expand_high_priority",
    "benchmark_top_k", "abstain_out_of_distribution",
})
OBSERVATION_KINDS = frozenset({
    "grammar_disposition", "proof", "differential", "compilation", "assembly",
    "static_cost", "benchmark", "hardware_counter", "composition",
})
QUALITY_GRADES = frozenset({"A", "B", "C", "D"})
SPEED_BUCKETS = (
    "regression_gt_10", "regression_3_to_10", "tie_minus3_plus3",
    "win_3_to_10", "win_10_to_50", "win_gt_50",
)


def canonical_semantic_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Return a language/provenance-free structural graph signature.

    Weisfeiler-Lehman-style refinement avoids relying on frontend-specific node identifiers while
    retaining typed operations and dependency structure. This is an identity aid, not a graph
    equivalence proof.
    """
    nodes = [item for item in graph.get("nodes", []) if isinstance(item, dict)]
    node_by_id = {str(item.get("id")): item for item in nodes}
    edges = [item for item in graph.get("edges", []) if isinstance(item, dict)]
    incoming: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for edge in edges:
        incoming[str(edge.get("destination"))].append((str(edge.get("source")), edge))
    node_payloads = {identifier: _node_semantic_payload(node) for identifier, node in node_by_id.items()}
    edge_payloads = [_edge_semantic_payload(edge) for edge in edges]
    labels = {identifier: canonical_hash(payload) for identifier, payload in node_payloads.items()}
    for _ in range(3):
        labels = {
            identifier: canonical_hash({
                "self": labels[identifier],
                "incoming": sorted((labels.get(source, "external"), canonical_hash(_edge_semantic_payload(edge))) for source, edge in incoming.get(identifier, [])),
            })
            for identifier in node_by_id
        }
    node_multiset = [[key, count] for key, count in sorted(Counter(labels.values()).items())]
    edge_multiset = [[key, count] for key, count in sorted(Counter(
        canonical_hash({
            "source": labels.get(str(edge.get("source")), "external"),
            "destination": labels.get(str(edge.get("destination")), "external"),
            "edge": _edge_semantic_payload(edge),
        }) for edge in edges
    ).items())]
    feature_inventory = Counter()
    for payload in node_payloads.values(): feature_inventory.update(_semantic_feature_tokens("node", payload))
    for payload in edge_payloads: feature_inventory.update(_semantic_feature_tokens("edge", payload))
    feature_inventory.update(_semantic_feature_tokens("graph.contract", graph.get("contracts", {})))
    feature_inventory.update(_semantic_feature_tokens("graph.obligation", graph.get("obligations", [])))
    feature_inventory.update(_semantic_feature_tokens("graph.effect", graph.get("effects", [])))
    feature_inventory.update(_semantic_feature_tokens("graph.protocol", graph.get("protocols", [])))
    return {
        "schema_version": CANONICAL_GRAPH_SCHEMA,
        "nodes": node_multiset,
        "edges": edge_multiset,
        "feature_inventory": dict(sorted(feature_inventory.items())),
        "obligations": [[list(key), count] for key, count in sorted(Counter(
            (str(item.get("category")), str(item.get("scope")), str(item.get("proof_method")))
            for item in graph.get("obligations", []) if isinstance(item, dict)
        ).items())],
        "effects": [[list(key), count] for key, count in sorted(Counter(
            (str(item.get("kind")), str(item.get("phase")), str(item.get("ordering")))
            for item in graph.get("effects", []) if isinstance(item, dict)
        ).items())],
        "protocols": [[list(key), count] for key, count in sorted(Counter(
            (str(item.get("protocol")), str(item.get("source_state")), str(item.get("target_state")))
            for item in graph.get("protocols", []) if isinstance(item, dict)
        ).items())],
        "claims": [[list(key), count] for key, count in sorted(Counter(
            (str(item.get("status")), str(item.get("scope")))
            for item in graph.get("claims", []) if isinstance(item, dict)
        ).items())],
        "contracts": _semantic_value(graph.get("contracts", {})),
    }


def make_root(
    graph: dict[str, Any],
    contract: dict[str, Any],
    provenance: list[dict[str, Any]],
    *,
    project_id: str,
    graph_version: str = "semantic-flow-v2",
) -> dict[str, Any]:
    semantic_graph = _semantic_graph_record(graph)
    canonical_graph = canonical_semantic_graph(semantic_graph)
    root_id = canonical_hash({"graph": canonical_graph, "contract": _semantic_value(contract)})
    record = {
        "schema_version": ROOT_SCHEMA,
        "root_id": root_id,
        "project_id": project_id,
        "graph_version": graph_version,
        "canonicalizer_version": CANONICAL_GRAPH_SCHEMA,
        "semantic_graph": semantic_graph,
        "canonical_graph": canonical_graph,
        "contract": _semantic_value(contract),
        "provenance": sorted((_provenance_value(item) for item in provenance), key=canonical_hash),
        "summary": graph_summary(graph),
    }
    validate_root(record)
    return record


def make_candidate(
    root_id: str,
    action: dict[str, Any],
    hardware: dict[str, Any],
    workload: dict[str, Any],
    *,
    baseline: bool = False,
    derivation: list[str] | None = None,
) -> dict[str, Any]:
    normalized_action = _normalize_action(action)
    hardware = _semantic_value(hardware)
    workload = _semantic_value(workload)
    candidate_id = canonical_hash({
        "root_id": root_id, "action": normalized_action, "hardware": hardware,
        "workload": workload, "baseline": baseline, "derivation": derivation or [],
    })
    record = {
        "schema_version": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "root_id": root_id,
        "action": normalized_action,
        "hardware": hardware,
        "hardware_id": canonical_hash(hardware),
        "workload": workload,
        "workload_id": canonical_hash(workload),
        "baseline": bool(baseline),
        "derivation": list(derivation or []),
    }
    validate_candidate(record)
    return record


def make_observation(
    candidate_id: str,
    kind: str,
    outcome: str,
    payload: dict[str, Any],
    *,
    quality_grade: str,
    artifact_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = {
        "candidate_id": candidate_id,
        "kind": kind,
        "outcome": outcome,
        "payload": _semantic_value(payload),
        "quality_grade": quality_grade,
        "artifact_hashes": dict(sorted((artifact_hashes or {}).items())),
    }
    record = {"schema_version": OBSERVATION_SCHEMA, "observation_id": canonical_hash(body), **body}
    validate_observation(record)
    return record


class PriorExperienceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        metadata = self.root / "metadata.json"
        expected = {
            "schema_version": PRIOR_DATASET_SCHEMA,
            "storage": "immutable-jsonl-v0",
            "descriptor_policy": {
                "semantic_graph": "open typed node/edge payload captured by canonical graph v1",
                "grammar_action": "structured open descriptor with family, version, primitives, parameters, and namespaced extensions",
                "hardware_workload": "structured open descriptors",
                "observation": "stable canonical outcome plus extensible payload",
            },
            "canonical_graph_schema": CANONICAL_GRAPH_SCHEMA,
        }
        if metadata.exists():
            current = json.loads(metadata.read_text())
            if current.get("schema_version") != PRIOR_DATASET_SCHEMA or current.get("storage") != "immutable-jsonl-v0":
                raise ValueError("experience store metadata is incompatible")
            return
        metadata.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")

    def append(self, kind: str, records: Iterable[dict[str, Any]]) -> dict[str, int]:
        validators = {"roots": validate_root, "candidates": validate_candidate, "observations": validate_observation}
        identifiers = {"roots": "root_id", "candidates": "candidate_id", "observations": "observation_id"}
        if kind not in validators:
            raise ValueError(f"unknown experience record kind {kind!r}")
        self.initialize()
        path = self.root / f"{kind}.jsonl"
        existing = {item[identifiers[kind]]: item for item in _read_jsonl(path)}
        added = 0
        with path.open("a") as handle:
            for record in records:
                validators[kind](record)
                identifier = record[identifiers[kind]]
                if identifier in existing:
                    if existing[identifier] != record:
                        raise ValueError(f"immutable {kind} record {identifier} conflicts with stored content")
                    continue
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                existing[identifier] = record
                added += 1
        return {"added": added, "total": len(existing)}

    def load(self) -> dict[str, Any]:
        roots = _read_jsonl(self.root / "roots.jsonl")
        candidates = _read_jsonl(self.root / "candidates.jsonl")
        observations = _read_jsonl(self.root / "observations.jsonl")
        dataset = {
            "schema_version": PRIOR_DATASET_SCHEMA,
            "roots": roots,
            "candidates": candidates,
            "observations": observations,
        }
        report = validate_dataset(dataset)
        if report["status"] != "pass":
            raise ValueError("invalid experience store: " + "; ".join(report["errors"]))
        dataset["dataset_hash"] = canonical_hash(dataset)
        return dataset


def ingest_bundle(manifest_path: Path, store_path: Path) -> dict[str, Any]:
    raw = json.loads(manifest_path.read_text()) if manifest_path.suffix == ".json" else __import__("yaml").safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("prior bundle manifest must be a mapping")
    base = manifest_path.resolve().parent
    def records(name: str) -> list[dict[str, Any]]:
        value = raw.get(name, [])
        if isinstance(value, str):
            path = (base / value).resolve()
            return _read_jsonl(path) if path.suffix == ".jsonl" else list(json.loads(path.read_text()))
        return list(value)
    store = PriorExperienceStore(store_path)
    result = {name: store.append(name, records(name)) for name in ("roots", "candidates", "observations")}
    dataset = store.load()
    return {"schema_version": PRIOR_DATASET_SCHEMA, "status": "pass", "ingested": result, "dataset_hash": dataset["dataset_hash"], "statistics": dataset_statistics(dataset)}


def materialize_training_template(manifest_path: Path, store_path: Path) -> dict[str, Any]:
    raw = json.loads(manifest_path.read_text()) if manifest_path.suffix == ".json" else __import__("yaml").safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or raw.get("schema_version") != TRAINING_TEMPLATE_SCHEMA:
        raise ValueError(f"training template must use {TRAINING_TEMPLATE_SCHEMA}")
    root_records = []; candidate_records = []; observation_records = []
    roots: dict[str, dict[str, Any]] = {}
    candidates: dict[str, dict[str, Any]] = {}
    for item in raw.get("roots", []):
        reference = str(item.get("ref", ""))
        if not reference or reference in roots: raise ValueError(f"invalid or duplicate root ref {reference!r}")
        record = make_root(
            item["graph"], item.get("contract", {}), list(item.get("provenance", [])),
            project_id=str(item["project_id"]), graph_version=str(item.get("graph_version", "semantic-flow-v2")),
        )
        roots[reference] = record; root_records.append(record)
    for item in raw.get("candidates", []):
        reference = str(item.get("ref", "")); root_ref = str(item.get("root_ref", ""))
        if not reference or reference in candidates: raise ValueError(f"invalid or duplicate candidate ref {reference!r}")
        if root_ref not in roots: raise ValueError(f"candidate {reference!r} references unknown root {root_ref!r}")
        record = make_candidate(
            roots[root_ref]["root_id"], item["action"], item.get("hardware", {}), item.get("workload", {}),
            baseline=bool(item.get("baseline", False)), derivation=list(item.get("derivation", [])),
        )
        candidates[reference] = record; candidate_records.append(record)
    for item in raw.get("observations", []):
        candidate_ref = str(item.get("candidate_ref", ""))
        if candidate_ref not in candidates: raise ValueError(f"observation references unknown candidate {candidate_ref!r}")
        observation_records.append(make_observation(
            candidates[candidate_ref]["candidate_id"], str(item["kind"]), str(item["outcome"]),
            item.get("payload", {}), quality_grade=str(item["quality_grade"]),
            artifact_hashes=item.get("artifact_hashes", {}),
        ))
    store = PriorExperienceStore(store_path)
    ingested = {
        "roots": store.append("roots", root_records),
        "candidates": store.append("candidates", candidate_records),
        "observations": store.append("observations", observation_records),
    }
    dataset = store.load()
    return {
        "schema_version": "vladder-prior-template-materialization-v1", "status": "pass",
        "template": str(manifest_path.resolve()), "store": str(store.root), "ingested": ingested,
        "root_refs": {key: value["root_id"] for key, value in sorted(roots.items())},
        "candidate_refs": {key: value["candidate_id"] for key, value in sorted(candidates.items())},
        "dataset_hash": dataset["dataset_hash"], "statistics": dataset_statistics(dataset),
    }


def validate_dataset(dataset: dict[str, Any], partitions: dict[str, list[str]] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    roots = dataset.get("roots", [])
    candidates = dataset.get("candidates", [])
    observations = dataset.get("observations", [])
    for item in roots:
        try: validate_root(item)
        except ValueError as exc: errors.append(str(exc))
    for item in candidates:
        try: validate_candidate(item)
        except ValueError as exc: errors.append(str(exc))
    for item in observations:
        try: validate_observation(item)
        except ValueError as exc: errors.append(str(exc))
    root_ids = {item.get("root_id") for item in roots}
    candidate_by_id = {item.get("candidate_id"): item for item in candidates}
    if len(root_ids) != len(roots): errors.append("duplicate root_id")
    if len(candidate_by_id) != len(candidates): errors.append("duplicate candidate_id")
    for item in candidates:
        if item.get("root_id") not in root_ids: errors.append(f"candidate {item.get('candidate_id')} references unknown root")
    seen_observations: set[str] = set()
    for item in observations:
        if item.get("observation_id") in seen_observations: errors.append(f"duplicate observation {item.get('observation_id')}")
        seen_observations.add(item.get("observation_id"))
        if item.get("candidate_id") not in candidate_by_id: errors.append(f"observation {item.get('observation_id')} references unknown candidate")
    if partitions:
        owner: dict[str, str] = {}
        split_names = ("train", "calibration", "test")
        for partition in split_names:
            ids = partitions.get(partition, [])
            for root_id in ids:
                if root_id in owner: errors.append(f"root {root_id} leaks across {owner[root_id]} and {partition}")
                owner[root_id] = partition
        project_partition: dict[str, set[str]] = defaultdict(set)
        roots_by_id = {item["root_id"]: item for item in roots}
        for partition in split_names:
            ids = partitions.get(partition, [])
            for root_id in ids:
                if root_id not in roots_by_id: errors.append(f"partition {partition} references unknown root {root_id}")
                else: project_partition[roots_by_id[root_id]["project_id"]].add(partition)
        for project, values in project_partition.items():
            if len(values) > 1 and partitions.get("split_method") == "project": errors.append(f"project {project} leaks across partitions {sorted(values)}")
    return {"schema_version": "vladder-prior-validation-v0", "status": "pass" if not errors else "fail", "errors": errors, "statistics": dataset_statistics(dataset)}


def build_splits(
    dataset: dict[str, Any], *, method: str = "root", seed: int = 4242,
    test_fraction: float = 0.2, calibration_fraction: float = 0.2,
    holdout: str | None = None,
) -> dict[str, Any]:
    if method not in {"root", "project", "language", "hardware", "temporal"}:
        raise ValueError("split method must be root, project, language, hardware, or temporal; candidate split is prohibited")
    roots = dataset["roots"]
    candidates_by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in dataset["candidates"]: candidates_by_root[item["root_id"]].append(item)
    groups: dict[str, list[str]] = defaultdict(list)
    for root in roots:
        if method == "root": key = root["root_id"]
        elif method == "project": key = root["project_id"]
        elif method == "language": key = ",".join(sorted({str(item.get("source_language", "unknown")) for item in root.get("provenance", [])}))
        elif method == "hardware": key = ",".join(sorted({item["hardware_id"] for item in candidates_by_root[root["root_id"]]}))
        else: key = max((str(item.get("source_commit", "unknown")) for item in root.get("provenance", [])), default="unknown")
        groups[key].append(root["root_id"])
    if holdout is not None:
        test_groups = [key for key in groups if holdout in key]
        if not test_groups: raise ValueError(f"holdout {holdout!r} does not match a {method} group")
        remaining = sorted(set(groups) - set(test_groups))
    else:
        remaining = sorted(groups)
        random.Random(seed).shuffle(remaining)
        test_count = max(1, round(len(remaining) * test_fraction)) if len(remaining) >= 3 else 1
        test_groups, remaining = remaining[:test_count], remaining[test_count:]
    calibration_count = max(1, round(len(remaining) * calibration_fraction)) if len(remaining) >= 2 else 0
    calibration_groups = remaining[:calibration_count]
    train_groups = remaining[calibration_count:]
    if not train_groups: raise ValueError("split leaves no training roots")
    result = {
        "schema_version": "vladder-prior-split-v0", "status": "pass", "split_method": method, "seed": seed,
        "train": sorted(root for key in train_groups for root in groups[key]),
        "calibration": sorted(root for key in calibration_groups for root in groups[key]),
        "test": sorted(root for key in test_groups for root in groups[key]),
    }
    validation = validate_dataset(dataset, result)
    if validation["status"] != "pass": raise ValueError("invalid split: " + "; ".join(validation["errors"]))
    result["split_hash"] = canonical_hash(result)
    return result


def dataset_statistics(dataset: dict[str, Any]) -> dict[str, Any]:
    roots = dataset.get("roots", []); candidates = dataset.get("candidates", []); observations = dataset.get("observations", [])
    physical = [item for item in observations if item.get("kind") in {"benchmark", "composition"} and item.get("quality_grade") != "D"]
    production_physical = [
        item for item in physical
        if item.get("quality_grade") in {"A", "B"}
        and not bool(item.get("payload", {}).get("synthetic", False))
    ]
    languages = {str(prov.get("source_language")) for root in roots for prov in root.get("provenance", []) if prov.get("source_language")}
    projects = {item.get("project_id") for item in roots}
    hardware = {item.get("hardware_id") for item in candidates}
    outcomes = Counter(item.get("outcome") for item in observations)
    stats = {
        "root_count": len(roots), "candidate_count": len(candidates), "observation_count": len(observations),
        "physical_observation_count": len(physical),
        "production_physical_observation_count": len(production_physical),
        "project_count": len(projects),
        "language_count": len(languages), "hardware_count": len(hardware),
        "languages": sorted(languages), "outcomes": dict(sorted(outcomes.items())),
    }
    requirements = {"roots": 2500, "projects": 20, "languages": 3, "hardware": 2, "physical_observations": 25000}
    actual = {
        "roots": len(roots), "projects": len(projects), "languages": len(languages),
        "hardware": len(hardware), "physical_observations": len(production_physical),
    }
    stats["production_acceptance"] = {
        "status": "eligible_for_model_evaluation" if all(actual[key] >= value for key, value in requirements.items()) else "insufficient_dataset",
        "requirements": requirements, "actual": actual,
        "physical_evidence_policy": "only non-synthetic Grade A/B benchmark or composition observations count",
    }
    return stats


def candidate_labels(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    observations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in dataset["observations"]: observations[item["candidate_id"]].append(item)
    result: dict[str, dict[str, Any]] = {}
    for candidate in dataset["candidates"]:
        items = observations.get(candidate["candidate_id"], [])
        semantic = [item for item in items if item["outcome"] in SEMANTIC_OUTCOMES]
        physical = [item for item in items if item["outcome"] in PHYSICAL_OUTCOMES and item["quality_grade"] != "D"]
        speedups = [float(item["payload"].get("paired_speedup", {}).get("median", item["payload"].get("speedup", 0.0))) for item in physical]
        proof_pass = any(item["outcome"] == "proof_passed" for item in semantic)
        illegal = any(item["outcome"] in {"inapplicable", "missing_contract", "semantic_mismatch", "illegal", "proof_failed"} for item in semantic)
        result[candidate["candidate_id"]] = {
            "applicable": not illegal,
            "proof_pass": proof_pass,
            "proof_risk": 0.0 if proof_pass else 1.0 if semantic else 0.5,
            "utility": max(speedups) if speedups else 0.0,
            "speed_bucket": speed_bucket(max(speedups) if speedups else 0.0),
            "physical_label": bool(physical),
            "outcomes": sorted({item["outcome"] for item in items}),
        }
    return result


def speed_bucket(speedup: float) -> str:
    if speedup < -0.10: return SPEED_BUCKETS[0]
    if speedup < -0.03: return SPEED_BUCKETS[1]
    if speedup <= 0.03: return SPEED_BUCKETS[2]
    if speedup <= 0.10: return SPEED_BUCKETS[3]
    if speedup <= 0.50: return SPEED_BUCKETS[4]
    return SPEED_BUCKETS[5]


def graph_summary(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = [item for item in graph.get("nodes", []) if isinstance(item, dict)]
    edges = [item for item in graph.get("edges", []) if isinstance(item, dict)]
    kinds = Counter(str(item.get("kind", "unknown")) for item in nodes)
    operations = Counter(str(item.get("operation", "unknown")) for item in nodes)
    edge_relations = Counter(str(item.get("relation", item.get("kind", "data"))) for item in edges)
    return {
        "node_count": len(nodes), "edge_count": len(edges), "node_kinds": dict(sorted(kinds.items())),
        "operations": dict(sorted(operations.items())), "edge_relations": dict(sorted(edge_relations.items())),
        "obligation_count": len(graph.get("obligations", [])), "effect_count": len(graph.get("effects", [])),
        "protocol_count": len(graph.get("protocols", [])), "claim_count": len(graph.get("claims", [])),
    }


def validate_root(record: dict[str, Any]) -> None:
    if record.get("schema_version") != ROOT_SCHEMA: raise ValueError("invalid prior root schema")
    expected = canonical_hash({"graph": record.get("canonical_graph"), "contract": record.get("contract")})
    if record.get("root_id") != expected: raise ValueError(f"root identity mismatch: {record.get('root_id')}")
    if not record.get("project_id") or not isinstance(record.get("provenance"), list): raise ValueError("prior root lacks project/provenance")
    if record.get("semantic_graph") is not None:
        rebuilt = canonical_semantic_graph(record["semantic_graph"])
        if rebuilt != record.get("canonical_graph"): raise ValueError(f"root semantic graph/canonical graph mismatch: {record.get('root_id')}")


def validate_candidate(record: dict[str, Any]) -> None:
    if record.get("schema_version") != CANDIDATE_SCHEMA: raise ValueError("invalid prior candidate schema")
    expected = canonical_hash({
        "root_id": record.get("root_id"), "action": record.get("action"), "hardware": record.get("hardware"),
        "workload": record.get("workload"), "baseline": bool(record.get("baseline")), "derivation": record.get("derivation", []),
    })
    if record.get("candidate_id") != expected: raise ValueError(f"candidate identity mismatch: {record.get('candidate_id')}")
    if not isinstance(record.get("action"), dict) or "family" not in record["action"]: raise ValueError("candidate action must name a family")
    if not isinstance(record["action"].get("parameters", {}), dict): raise ValueError("candidate action parameters must be a mapping")
    if not isinstance(record["action"].get("primitives", []), list): raise ValueError("candidate action primitives must be a list")


def validate_observation(record: dict[str, Any]) -> None:
    if record.get("schema_version") != OBSERVATION_SCHEMA: raise ValueError("invalid prior observation schema")
    if record.get("kind") not in OBSERVATION_KINDS: raise ValueError(f"invalid observation kind {record.get('kind')}")
    if record.get("quality_grade") not in QUALITY_GRADES: raise ValueError("invalid observation quality grade")
    if record.get("outcome") not in SEMANTIC_OUTCOMES | PHYSICAL_OUTCOMES: raise ValueError(f"invalid observation outcome {record.get('outcome')}")
    body = {key: record[key] for key in ("candidate_id", "kind", "outcome", "payload", "quality_grade", "artifact_hashes")}
    if record.get("observation_id") != canonical_hash(body): raise ValueError(f"observation identity mismatch: {record.get('observation_id')}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _normalize_type(value: Any) -> str | None:
    if value is None: return None
    return " ".join(str(value).replace("std::", "").split())


def _semantic_value(value: Any) -> Any:
    if isinstance(value, dict):
        ignored = {"source_language", "compiler_identity", "semantic_ir", "graph_hash", "graph_sha256", "function_identity", "source_provenance", "language_binding", "path", "artifact"}
        return {str(key): _semantic_value(item) for key, item in sorted(value.items()) if key not in ignored}
    if isinstance(value, (list, tuple)): return [_semantic_value(item) for item in value]
    if isinstance(value, float): return value if math.isfinite(value) else str(value)
    return value


def _provenance_value(value: Any) -> Any:
    if isinstance(value, dict): return {str(key): _provenance_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)): return [_provenance_value(item) for item in value]
    return value


def _node_semantic_payload(node: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in node.items() if key not in {"id", "inputs", "source_provenance"}}
    if "output_type" in payload: payload["output_type"] = _normalize_type(payload["output_type"])
    return _semantic_value(payload)


def _semantic_graph_record(graph: dict[str, Any]) -> dict[str, Any]:
    return _semantic_value({
        "schema_version": graph.get("schema_version", "semantic-flow-v2"),
        "nodes": graph.get("nodes", []), "edges": graph.get("edges", []),
        "obligations": graph.get("obligations", []), "effects": graph.get("effects", []),
        "protocols": graph.get("protocols", []), "claims": graph.get("claims", []),
        "contracts": graph.get("contracts", {}),
    })


def _edge_semantic_payload(edge: dict[str, Any]) -> dict[str, Any]:
    return _semantic_value({key: value for key, value in edge.items() if key not in {"id", "source", "destination", "source_provenance"}})


def _semantic_feature_tokens(prefix: str, value: Any) -> list[str]:
    if isinstance(value, dict):
        result = []
        for key, item in sorted(value.items()): result.extend(_semantic_feature_tokens(f"{prefix}.{key}", item))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value: result.extend(_semantic_feature_tokens(prefix, item))
        return result
    if isinstance(value, bool): return [f"{prefix}={str(value).lower()}"]
    if isinstance(value, (int, float)): return [f"{prefix}.numeric"]
    return [f"{prefix}={value}"]


def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict) or not str(action.get("family", "")).strip():
        raise ValueError("candidate action must name a nonempty family")
    normalized = _semantic_value(action)
    normalized.setdefault("descriptor_version", "grammar-action-v1")
    normalized.setdefault("family_version", normalized.get("version", "unversioned"))
    normalized.setdefault("primitives", [])
    normalized.setdefault("parameters", {})
    normalized.setdefault("extensions", {})
    return normalized
