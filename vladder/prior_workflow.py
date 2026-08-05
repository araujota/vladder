from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .consent import CANONICAL_TRAINING_DATA, contribution_stage
from .prior_data import (
    TRAINING_TEMPLATE_SCHEMA, PriorExperienceStore, build_splits, dataset_statistics,
    ingest_bundle, materialize_training_template, validate_dataset,
)
from .prior_model import load_prior_model, recommend_candidates, train_prior_model
from .prior_search import select_search_budget, shadow_evaluate
from .prior_synthetic import generate_synthetic_prior_corpus


PRIOR_WORKFLOW_SCHEMA = "vladder-prior-workflow-v0"
PRIOR_SUMMARY_SCHEMA = "vladder-prior-workflow-summary-v0"


def prior_support() -> dict[str, Any]:
    return {
        "schema_version": "vladder-prior-support-v0",
        "status": "pass",
        "dataset": "immutable canonical roots/actions/candidates/observations operational",
        "vocabulary": "open typed graph fields plus versioned action primitives/parameters/namespaced extensions",
        "split_methods": ["root", "project", "language", "hardware", "temporal"],
        "pilot_model": "deterministic hashed pooled-graph linear ensemble operational",
        "future_model": "heterogeneous relational graph transformer gated on minimum viable corpus",
        "uncertainty": "ensemble disagreement, held-out graph distance, conformal residual summary",
        "search": "shadow and baseline/exploration-preserving budget selection operational",
        "generalization": "independent root/project/language/hardware/temporal train-and-shadow matrix operational",
        "authority": "search prior only; never legality, proof, measurement, source generation, or promotion",
    }


def initialize_prior_manifest(output: Path) -> dict[str, Any]:
    manifest = {
        "schema_version": PRIOR_WORKFLOW_SCHEMA,
        "name": "prior-pilot",
        "dataset": {"mode": "controlled_synthetic", "root_count": 60},
        "split": {
            "method": "project", "seed": 4242, "test_fraction": 0.2,
            "calibration_fraction": 0.2, "holdout": None,
        },
        "model": {"ensemble_size": 3, "epochs": 80, "learning_rate": 0.08, "seed": 4242},
        "evaluation": {
            "partition": "test", "budget_fraction": 0.10,
            "exploration_fraction": 0.20, "seed": 4242,
        },
    }
    output = output.resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def initialize_prior_training_template(output: Path) -> dict[str, Any]:
    template = {
        "schema_version": TRAINING_TEMPLATE_SCHEMA,
        "vocabulary": {
            "semantic_graph": "semantic-flow-v2+prior-canonical-semantic-graph-v1-open-typed-extensions",
            "grammar": "replace-with-current-grammar-hash",
            "extension_policy": "place family-specific data under structured fields or namespaced extensions",
        },
        "roots": [{
            "ref": "root.example", "project_id": "opaque-project-id", "graph_version": "semantic-flow-v2",
            "provenance": [{"source_language": "cpp", "frontend_version": "frontend-version", "source_commit": "commit-hash", "source_region_hash": "region-hash"}],
            "contract": {"semantic_family": "future_family", "exact": True, "observables": ["output", "extent"]},
            "graph": {
                "schema_version": "semantic-flow-v2", "name": "future-root", "nodes": [
                    {"id": "input", "kind": "Input", "operation": "load", "output_type": "u32", "attributes": {}, "semantic_obligations": []},
                    {"id": "future", "kind": "FutureTypedNode", "operation": "future.transform", "output_type": "u32", "attributes": {"domain_specific_dimension": 4}, "semantic_obligations": []},
                ],
                "edges": [{"id": "edge.0", "source": "input", "destination": "future", "relation": "future-data-relation", "value_type": "u32", "ownership": "borrowed", "lifetime": "call", "ordering": "program-order"}],
                "obligations": [], "effects": [], "protocols": [], "claims": [], "contracts": {},
            },
        }],
        "candidates": [
            {"ref": "candidate.baseline", "root_ref": "root.example", "baseline": True, "action": {"family": "baseline", "family_version": 1, "primitives": [], "parameters": {}}, "hardware": {"architecture": "x86_64", "isa": ["avx2"]}, "workload": {"input_size_bucket": 1024}},
            {"ref": "candidate.future", "root_ref": "root.example", "action": {"family": "future_family", "family_version": 1, "primitives": ["future.transform"], "parameters": {"tile": 4}, "extensions": {"org.example.future": {"schema_version": 1, "policy": "bounded"}}}, "hardware": {"architecture": "x86_64", "isa": ["avx2"]}, "workload": {"input_size_bucket": 1024}},
        ],
        "observations": [
            {"candidate_ref": "candidate.baseline", "kind": "proof", "outcome": "proof_passed", "quality_grade": "C", "payload": {"method": "replace-with-proof-artifact"}},
            {"candidate_ref": "candidate.future", "kind": "proof", "outcome": "proof_unknown", "quality_grade": "D", "payload": {"reason": "not-yet-evaluated"}},
        ],
    }
    output = output.resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(template, sort_keys=False))
    return template


def materialize_prior_dataset_template(manifest: Path, store: Path) -> dict[str, Any]:
    return materialize_training_template(manifest.resolve(), store.resolve())


def run_prior_workflow(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(); output_directory = output_directory.resolve()
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or raw.get("schema_version") != PRIOR_WORKFLOW_SCHEMA:
        raise ValueError(f"prior workflow manifest must use {PRIOR_WORKFLOW_SCHEMA}")
    output_directory.mkdir(parents=True, exist_ok=True)
    dataset_config = raw.get("dataset", {})
    mode = str(dataset_config.get("mode", "controlled_synthetic"))
    if mode == "controlled_synthetic":
        corpus_directory = output_directory / "corpus"
        corpus = generate_prior_dataset(corpus_directory, int(dataset_config.get("root_count", 60)))
        store = corpus_directory / "experience"
    elif mode == "existing_store":
        value = dataset_config.get("store")
        if not value: raise ValueError("existing_store mode requires dataset.store")
        path = Path(str(value)); store = path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()
        corpus = {"status": "existing_store", "experience_store": str(store)}
    else:
        raise ValueError("dataset.mode must be controlled_synthetic or existing_store")
    validation = validate_prior_dataset(store)
    if validation["status"] != "pass": raise ValueError("prior dataset validation failed: " + "; ".join(validation["errors"]))
    split_config = raw.get("split", {})
    split_path = output_directory / "split.json"
    split = split_prior_dataset(
        store, split_path, method=str(split_config.get("method", "project")),
        seed=int(split_config.get("seed", 4242)), test_fraction=float(split_config.get("test_fraction", 0.2)),
        calibration_fraction=float(split_config.get("calibration_fraction", 0.2)),
        holdout=str(split_config["holdout"]) if split_config.get("holdout") is not None else None,
    )
    model_config = raw.get("model", {})
    model_directory = output_directory / "model"
    training = train_prior(
        store, split_path, model_directory,
        ensemble_size=int(model_config.get("ensemble_size", 3)), epochs=int(model_config.get("epochs", 80)),
        learning_rate=float(model_config.get("learning_rate", 0.08)), seed=int(model_config.get("seed", 4242)),
    )
    evaluation_config = raw.get("evaluation", {})
    evaluation_path = output_directory / "shadow-evaluation.json"
    evaluation = evaluate_prior(
        model_directory / "prior-model.json", store, split_path, evaluation_path,
        partition=str(evaluation_config.get("partition", "test")),
        budget_fraction=float(evaluation_config.get("budget_fraction", 0.10)),
        exploration_fraction=float(evaluation_config.get("exploration_fraction", 0.20)),
        seed=int(evaluation_config.get("seed", 4242)),
    )
    summary = {
        "schema_version": PRIOR_SUMMARY_SCHEMA,
        "status": "pass",
        "workflow_completed": True,
        "dataset_valid": validation["status"] == "pass",
        "model_trained": training["status"] == "pass",
        "shadow_evaluation_completed": evaluation["status"] == "pass",
        "production_model_status": training["production_model_status"],
        "live_search_pruned": False,
        "pilot_thresholds": evaluation.get("pilot_thresholds", {}),
        "metrics": {
            key: evaluation.get(key) for key in (
                "winner_recall_at_budget", "recall_at_10_percent", "grammar_recall_at_3",
                "measurement_reduction_factor", "median_regret", "expected_calibration_error",
                "applicability_macro_f1", "baseline_suppression_count", "abstention_rate",
            )
        },
        "decisive_artifacts": [
            str(output_directory / "corpus/synthetic-corpus-report.json") if mode == "controlled_synthetic" else str(store / "metadata.json"),
            str(split_path), str(model_directory / "training-report.json"),
            str(model_directory / "prior-model.json"), str(evaluation_path),
        ],
        "next_action": (
            "collect non-synthetic Grade A/B experience until the production corpus gate is met; continue shadow mode"
            if training["production_model_status"] == "insufficient_dataset" else
            "run project/root/language/hardware holdouts in shadow mode before enabling budgeted search"
        ),
        "authority": "workflow and counterfactual search evidence only; no legality, proof, measurement, or promotion gate was bypassed",
        "optional_canonical_training_contribution": contribution_stage(CANONICAL_TRAINING_DATA),
        "dataset": corpus,
        "split_hash": split["split_hash"],
        "model_hash": training["model_hash"],
        "evaluation_hash": evaluation["evaluation_hash"],
    }
    (output_directory / "prior-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def generate_prior_dataset(output_directory: Path, root_count: int) -> dict[str, Any]:
    return generate_synthetic_prior_corpus(output_directory, root_count=root_count)


def ingest_prior_dataset(manifest: Path, store: Path) -> dict[str, Any]:
    return ingest_bundle(manifest.resolve(), store.resolve())


def validate_prior_dataset(store: Path, split_path: Path | None = None) -> dict[str, Any]:
    dataset = PriorExperienceStore(store).load()
    split = json.loads(split_path.read_text()) if split_path else None
    report = validate_dataset(dataset, split)
    report["dataset_hash"] = dataset["dataset_hash"]
    report["production_acceptance"] = dataset_statistics(dataset)["production_acceptance"]
    return report


def split_prior_dataset(store: Path, output: Path, *, method: str, seed: int, test_fraction: float, calibration_fraction: float, holdout: str | None) -> dict[str, Any]:
    dataset = PriorExperienceStore(store).load()
    report = build_splits(dataset, method=method, seed=seed, test_fraction=test_fraction, calibration_fraction=calibration_fraction, holdout=holdout)
    output.resolve().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def train_prior(store: Path, split_path: Path, output_directory: Path, *, ensemble_size: int, epochs: int, learning_rate: float, seed: int) -> dict[str, Any]:
    dataset = PriorExperienceStore(store).load(); split = json.loads(split_path.read_text())
    return train_prior_model(dataset, split, output_directory, ensemble_size=ensemble_size, epochs=epochs, learning_rate=learning_rate, seed=seed)


def recommend_prior(model_path: Path, store: Path, root_id: str, output: Path) -> dict[str, Any]:
    model = load_prior_model(model_path); dataset = PriorExperienceStore(store).load()
    root = next((item for item in dataset["roots"] if item["root_id"] == root_id), None)
    if root is None: raise ValueError(f"unknown root {root_id}")
    candidates = [item for item in dataset["candidates"] if item["root_id"] == root_id]
    report = recommend_candidates(model, root, candidates)
    output.resolve().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def select_prior(recommendation_path: Path, store: Path, root_id: str, output: Path, *, budget: int, exploration_fraction: float, seed: int) -> dict[str, Any]:
    recommendation = json.loads(recommendation_path.read_text()); dataset = PriorExperienceStore(store).load()
    candidates = [item for item in dataset["candidates"] if item["root_id"] == root_id]
    report = select_search_budget(recommendation, candidates, budget=budget, exploration_fraction=exploration_fraction, seed=seed)
    output.resolve().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def evaluate_prior(model_path: Path, store: Path, split_path: Path, output: Path, *, partition: str, budget_fraction: float, exploration_fraction: float, seed: int) -> dict[str, Any]:
    model = load_prior_model(model_path); dataset = PriorExperienceStore(store).load(); split = json.loads(split_path.read_text())
    if partition not in {"train", "calibration", "test"}: raise ValueError("partition must be train, calibration, or test")
    report = shadow_evaluate(model, dataset, split[partition], budget_fraction=budget_fraction, exploration_fraction=exploration_fraction, seed=seed)
    report["production_model_status"] = dataset_statistics(dataset)["production_acceptance"]["status"]
    output.resolve().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def evaluate_prior_generalization(
    store: Path, output_directory: Path, *, methods: tuple[str, ...] = ("root", "project", "language", "hardware", "temporal"),
    ensemble_size: int = 3, epochs: int = 40, learning_rate: float = 0.08, seed: int = 4242,
    budget_fraction: float = 0.10, exploration_fraction: float = 0.20,
) -> dict[str, Any]:
    output_directory = output_directory.resolve(); output_directory.mkdir(parents=True, exist_ok=True)
    views = {}
    for ordinal, method in enumerate(methods):
        view_directory = output_directory / method; view_directory.mkdir(parents=True, exist_ok=True)
        split_path = view_directory / "split.json"
        split = split_prior_dataset(
            store, split_path, method=method, seed=seed + ordinal,
            test_fraction=0.2, calibration_fraction=0.2, holdout=None,
        )
        training = train_prior(
            store, split_path, view_directory / "model", ensemble_size=ensemble_size,
            epochs=epochs, learning_rate=learning_rate, seed=seed + ordinal,
        )
        evaluation = evaluate_prior(
            view_directory / "model/prior-model.json", store, split_path,
            view_directory / "shadow-evaluation.json", partition="test",
            budget_fraction=budget_fraction, exploration_fraction=exploration_fraction,
            seed=seed + ordinal,
        )
        views[method] = {
            "split_hash": split["split_hash"], "model_hash": training["model_hash"],
            "production_model_status": training["production_model_status"],
            "root_count": evaluation["root_count"],
            "winner_recall_at_budget": evaluation["winner_recall_at_budget"],
            "recall_at_10_percent": evaluation["recall_at_10_percent"],
            "measurement_reduction_factor": evaluation["measurement_reduction_factor"],
            "median_regret": evaluation["median_regret"],
            "applicability_macro_f1": evaluation["applicability_macro_f1"],
            "abstention_rate": evaluation["abstention_rate"],
            "baseline_suppression_count": evaluation["baseline_suppression_count"],
        }
    report = {
        "schema_version": "vladder-prior-generalization-matrix-v0", "status": "pass",
        "views": views,
        "claim_boundary": "each view uses its own root-grouped split and trained pilot; controlled data is not production generalization evidence",
    }
    (output_directory / "generalization-summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
