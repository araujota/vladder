from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .language_adapter import canonical_hash
from .prior_data import PriorExperienceStore, make_candidate, make_observation, make_root
from .schema_registry import validate_artifact


MODEL_TRAINING_SCHEMA_VERSION = "vladder-model-training-bundle-v2"


def ingest_model_training_bundle(bundle_path: Path, store_path: Path) -> dict[str, Any]:
    """Import a validated, de-identified v2 bundle into the canonical prior store."""
    validation = validate_artifact("model-training-bundle", bundle_path)
    if validation["status"] != "pass":
        raise ValueError(f"model-training bundle failed validation: {validation['errors']}")
    bundle = json.loads(bundle_path.resolve().read_text())
    roots: list[dict[str, Any]] = []
    root_ids: dict[str, str] = {}
    for item in bundle["roots"]:
        graph = _restore_graph(item["graph"])
        # PriorExperienceStore v0 keys roots by semantic identity. Normalize occurrence metadata so
        # multilingual/project clones can collapse without creating immutable-record conflicts.
        # The topology-preserving graph_learning_examples path retains each transmitted occurrence.
        semantic_project = f"deidentified-semantic:{canonical_hash({'graph': item['graph'], 'contract': item['contract_features']})}"
        root = make_root(
            graph,
            _restore_feature_set(item["contract_features"], prefix="contract."),
            [{"source_language": "other"}],
            project_id=semantic_project,
            graph_version=item["graph_version"],
        )
        roots.append(root)
        root_ids[item["root_id"]] = root["root_id"]

    candidates: list[dict[str, Any]] = []
    candidate_ids: dict[str, str] = {}
    for item in bundle["candidates"]:
        action = item["action"]
        parameters = {
            **{feature["name"]: feature["value"] for feature in action["numeric_parameters"]},
            **{feature["name"]: feature["value"] for feature in action["categorical_parameters"]},
        }
        candidate = make_candidate(
            root_ids[item["root_id"]],
            {
                "family": action["family"],
                "family_version": action["family_version"],
                "primitives": action["primitives"],
                "parameters": parameters,
                "extensions": {
                    namespace: {"public_training_schema": True} for namespace in action["extension_namespaces"]
                },
            },
            _restore_feature_set(item["hardware"], prefix="hardware."),
            _restore_feature_set(item["workload"], prefix="workload."),
            baseline=item["baseline"],
            derivation=["deidentified_model_training_v2"],
        )
        candidates.append(candidate)
        candidate_ids[item["candidate_id"]] = candidate["candidate_id"]

    observations: list[dict[str, Any]] = []
    for item in bundle["observations"]:
        payload: dict[str, Any] = {
            "proof_class": item["proof_class"],
            "benchmark_scope": item["benchmark_scope"],
            "sample_count": item["sample_count"],
            "resources": _restore_feature_set(item["resource_features"], prefix="resource."),
        }
        if item["speedup_percent"] is not None:
            payload["paired_speedup"] = {
                "median": item["speedup_percent"] / 100.0,
                "bootstrap_ci_low": (
                    item["ci_lower_percent"] / 100.0 if item["ci_lower_percent"] is not None else None
                ),
                "bootstrap_ci_high": (
                    item["ci_upper_percent"] / 100.0 if item["ci_upper_percent"] is not None else None
                ),
            }
        observations.append(make_observation(
            candidate_ids[item["candidate_id"]],
            item["kind"],
            item["outcome"],
            payload,
            quality_grade=item["quality_grade"],
        ))

    store = PriorExperienceStore(store_path)
    ingested = {
        "roots": store.append("roots", roots),
        "candidates": store.append("candidates", candidates),
        "observations": store.append("observations", observations),
    }
    dataset = store.load()
    return {
        "schema_version": "vladder-model-training-ingestion-v1",
        "status": "pass",
        "bundle": str(bundle_path.resolve()),
        "store": str(store.root),
        "ingested": ingested,
        "input_counts": {
            "roots": len(bundle["roots"]), "candidates": len(bundle["candidates"]),
            "observations": len(bundle["observations"]),
        },
        "compatibility_note": (
            "PriorExperienceStore v0 collapses exact semantic clones; graph_learning_examples "
            "retains every project/language occurrence and is the authoritative GNN input"
        ),
        "dataset_hash": dataset["dataset_hash"],
    }


def graph_learning_examples(bundle_path: Path) -> list[dict[str, Any]]:
    """Return topology-preserving candidate examples for GNN/GraphML data loaders.

    The baseline and alternatives for a root share one ranking_group. Labels remain an observation
    sequence so proof failures, ties, regressions, and composed outcomes are not collapsed.
    """
    validation = validate_artifact("model-training-bundle", bundle_path)
    if validation["status"] != "pass":
        raise ValueError(f"model-training bundle failed validation: {validation['errors']}")
    bundle = json.loads(bundle_path.resolve().read_text())
    roots = {item["root_id"]: item for item in bundle["roots"]}
    observations: dict[str, list[dict[str, Any]]] = {}
    for item in bundle["observations"]:
        observations.setdefault(item["candidate_id"], []).append(item)
    result = []
    for candidate in bundle["candidates"]:
        root = roots[candidate["root_id"]]
        graph = root["graph"]
        hardware_key = canonical_hash(candidate["hardware"])
        workload_key = canonical_hash(candidate["workload"])
        result.append({
            "schema_version": "vladder-graph-learning-example-v1",
            "root_id": root["root_id"],
            "candidate_id": candidate["candidate_id"],
            "ranking_group": canonical_hash({
                "root": root["root_id"], "hardware": hardware_key, "workload": workload_key,
            }),
            "graph": {
                "node_features": [{key: value for key, value in node.items() if key != "index"} for node in graph["nodes"]],
                "edge_index": [
                    [edge["source"] for edge in graph["edges"]],
                    [edge["destination"] for edge in graph["edges"]],
                ],
                "edge_features": [
                    {key: value for key, value in edge.items() if key not in {"source", "destination"}}
                    for edge in graph["edges"]
                ],
                "obligations": graph["obligations"],
                "effects": graph["effects"],
                "protocols": graph["protocols"],
                "claims": graph["claims"],
            },
            "action": candidate["action"],
            "hardware": candidate["hardware"],
            "workload": candidate["workload"],
            "baseline": candidate["baseline"],
            "labels": observations.get(candidate["candidate_id"], []),
        })
    return result


def write_graph_learning_jsonl(bundle_path: Path, output_path: Path) -> dict[str, Any]:
    examples = graph_learning_examples(bundle_path)
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        for example in examples:
            stream.write(json.dumps(example, sort_keys=True, separators=(",", ":")) + "\n")
    return {
        "schema_version": "vladder-graph-learning-export-v1",
        "status": "pass",
        "bundle": str(bundle_path.resolve()),
        "output": str(output_path),
        "candidate_example_count": len(examples),
        "ranking_group_count": len({item["ranking_group"] for item in examples}),
        "authority": "training input only; no legality, proof, performance, or promotion authority",
    }


def _restore_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    for item in graph["nodes"]:
        output_type = _type_name(item["type_class"], item["bit_width"], item["vector_lanes"])
        node = {
            "id": f"node:{item['index']}", "kind": item["kind"],
            "operation": item["operation"], "output_type": output_type,
        }
        node.update(_feature_items(item["numeric_features"], item["categorical_features"]))
        nodes.append(node)
    edges = []
    for item in graph["edges"]:
        edge = {
            "source": f"node:{item['source']}", "destination": f"node:{item['destination']}",
            "relation": item["relation"], "ordering": item["ordering"],
        }
        edge.update(_feature_items(item["numeric_features"], item["categorical_features"]))
        edges.append(edge)
    return {
        "nodes": nodes, "edges": edges,
        "obligations": graph["obligations"], "effects": graph["effects"],
        "protocols": graph["protocols"], "claims": graph["claims"],
    }


def _restore_feature_set(value: dict[str, Any], *, prefix: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for feature in value["numeric"]:
        output[_strip_prefix(feature["name"], prefix)] = feature["value"]
    for feature in value["categorical"]:
        key = _strip_prefix(feature["name"], prefix)
        current = output.get(key)
        if current is None:
            output[key] = feature["value"]
        elif isinstance(current, list):
            current.append(feature["value"])
        else:
            output[key] = [current, feature["value"]]
    return output


def _feature_items(numeric: list[dict[str, Any]], categorical: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **{feature["name"]: feature["value"] for feature in numeric},
        **{feature["name"]: feature["value"] for feature in categorical},
    }


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def _type_name(type_class: str, bit_width: int | None, lanes: int | None) -> str:
    scalar = {
        "boolean": "i1", "integer": f"i{bit_width or 32}", "float": f"f{bit_width or 32}",
        "pointer": "ptr", "aggregate": "aggregate", "unknown": "unknown", "other": "other",
    }[type_class]
    return f"<{lanes} x {scalar}>" if lanes is not None else scalar
