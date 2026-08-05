from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vladder.prior_data import (
    PriorExperienceStore, build_splits, dataset_statistics, ingest_bundle, make_candidate,
    make_observation, make_root, validate_dataset,
)
from vladder.prior_model import extract_prior_features, load_prior_model, recommend_candidates, train_prior_model
from vladder.prior_search import select_search_budget, shadow_evaluate
from vladder.prior_synthetic import generate_synthetic_prior_corpus
from vladder.prior_workflow import evaluate_prior_generalization, initialize_prior_manifest, run_prior_workflow
from vladder.prior_workflow import initialize_prior_training_template, materialize_prior_dataset_template


def graph(kind: str = "Compare") -> dict:
    return {
        "schema_version": "semantic-flow-v2", "name": "test", "source_language": "ignored",
        "nodes": [
            {"id": "a", "kind": "Input", "operation": "input", "output_type": "u8", "attributes": {}, "semantic_obligations": []},
            {"id": "b", "kind": kind, "operation": "predicate", "output_type": "bool", "attributes": {}, "semantic_obligations": []},
        ],
        "edges": [{"source": "a", "destination": "b", "value_type": "u8", "ownership": "borrowed", "lifetime": "call", "ordering": "program-order", "realization": "semantic", "memory_region": "argument", "validity_scope": "call"}],
        "contracts": {}, "obligations": [], "effects": [], "protocols": [], "claims": [],
    }


class PriorV0Tests(unittest.TestCase):
    def test_language_provenance_does_not_change_semantic_root_identity(self) -> None:
        left = make_root(graph(), {"exact": True}, [{"source_language": "cpp"}], project_id="left")
        right_graph = graph(); right_graph["source_language"] = "rust"; right_graph["compiler_identity"] = "rustc"
        right = make_root(right_graph, {"exact": True}, [{"source_language": "rust"}], project_id="right")
        self.assertEqual(left["root_id"], right["root_id"])
        self.assertNotEqual(left["provenance"], right["provenance"])
        candidate = make_candidate(left["root_id"], {"family": "baseline", "parameters": {}}, {"architecture": "x86_64"}, {"size": 8}, baseline=True)
        self.assertEqual(extract_prior_features(left, candidate)[0], extract_prior_features(right, candidate)[0])

    def test_immutable_store_rejects_conflicting_root_content(self) -> None:
        left = make_root(graph(), {"exact": True}, [{"source_language": "cpp"}], project_id="left")
        right = dict(left); right["project_id"] = "right"
        with tempfile.TemporaryDirectory() as directory:
            store = PriorExperienceStore(Path(directory)); store.append("roots", [left])
            with self.assertRaisesRegex(ValueError, "conflicts"):
                store.append("roots", [right])

    def test_candidate_level_leakage_is_rejected(self) -> None:
        root = make_root(graph(), {"exact": True}, [{"source_language": "c"}], project_id="project")
        dataset = {"roots": [root], "candidates": [], "observations": []}
        report = validate_dataset(dataset, {"train": [root["root_id"]], "calibration": [], "test": [root["root_id"]]})
        self.assertEqual(report["status"], "fail")
        self.assertIn("leaks", report["errors"][0])

    def test_project_split_has_no_project_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            generate_synthetic_prior_corpus(root_path / "corpus", root_count=36)
            dataset = PriorExperienceStore(root_path / "corpus/experience").load()
            split = build_splits(dataset, method="project", seed=3)
            owners = {}
            roots = {item["root_id"]: item for item in dataset["roots"]}
            for partition in ("train", "calibration", "test"):
                for root_id in split[partition]:
                    project = roots[root_id]["project_id"]
                    if project in owners:
                        self.assertEqual(owners[project], partition)
                    else:
                        owners[project] = partition

    def test_synthetic_grade_c_does_not_satisfy_production_measurement_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            generate_synthetic_prior_corpus(root_path / "corpus", root_count=30)
            dataset = PriorExperienceStore(root_path / "corpus/experience").load()
            statistics = dataset_statistics(dataset)
            self.assertGreater(statistics["physical_observation_count"], 0)
            self.assertEqual(statistics["production_physical_observation_count"], 0)
            self.assertEqual(statistics["production_acceptance"]["actual"]["physical_observations"], 0)

    def test_controlled_multilingual_clones_share_canonical_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = generate_synthetic_prior_corpus(Path(directory) / "corpus", root_count=12)
            canonicalization = report["multilingual_canonicalization"]
            self.assertEqual(canonicalization["status"], "pass")
            self.assertEqual(set(canonicalization["languages"]), {"c", "cpp", "rust", "zig", "julia"})
            self.assertTrue(all(item["equivalent_identity"] for item in canonicalization["rows"]))

    def test_unknown_future_grammar_fields_survive_identity_and_feature_extraction(self) -> None:
        future_graph = graph("FutureStatefulVariableOutput")
        future_graph["nodes"][1]["authority_epoch"] = {"scope": "transaction", "versioned": True}
        future_graph["edges"][0]["relation"] = "publishes-compacted-output"
        future_graph["edges"][0]["consistency_model"] = "atomic-generation"
        root = make_root(future_graph, {"semantic_family": "future.delta_compaction", "exact": True}, [{"source_language": "cpp"}], project_id="future-project")
        action = {
            "family": "future.delta_compaction", "family_version": 7,
            "primitives": ["compare", "prefix_sum", "publish"],
            "parameters": {"tile": 8, "publication": {"mode": "transactional"}},
            "extensions": {"org.example.delta": {"schema_version": 3, "rollback": True}},
        }
        candidate = make_candidate(root["root_id"], action, {"architecture": "future64", "isa": ["v2"]}, {"batch": 4})
        self.assertEqual(candidate["action"]["primitives"], ["compare", "prefix_sum", "publish"])
        inventory = root["canonical_graph"]["feature_inventory"]
        self.assertTrue(any("authority_epoch" in key for key in inventory))
        self.assertTrue(any("consistency_model" in key for key in inventory))
        features, _ = extract_prior_features(root, candidate)
        changed_graph = json.loads(json.dumps(future_graph))
        changed_graph["nodes"][1]["authority_epoch"]["versioned"] = False
        changed_root = make_root(changed_graph, root["contract"], [{"source_language": "zig"}], project_id="future-project")
        changed_candidate = make_candidate(changed_root["root_id"], action, candidate["hardware"], candidate["workload"])
        self.assertNotEqual(root["root_id"], changed_root["root_id"])
        self.assertNotEqual(features, extract_prior_features(changed_root, changed_candidate)[0])

    def test_reference_template_materializes_future_family_without_schema_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory); template = root_path / "template.yaml"
            initialized = initialize_prior_training_template(template)
            initialized["roots"][0]["graph"]["nodes"][1]["new_future_semantics"] = {"lanes": 17}
            initialized["candidates"][1]["action"]["primitives"].append("new.future.primitive")
            template.write_text(__import__("yaml").safe_dump(initialized, sort_keys=False))
            report = materialize_prior_dataset_template(template, root_path / "store")
            self.assertEqual(report["status"], "pass")
            dataset = PriorExperienceStore(root_path / "store").load()
            self.assertEqual(len(dataset["roots"]), 1)
            self.assertEqual(len(dataset["candidates"]), 2)
            future = next(item for item in dataset["candidates"] if not item["baseline"])
            self.assertIn("new.future.primitive", future["action"]["primitives"])

    def test_bundle_ingestion_preserves_immutable_lineage(self) -> None:
        root = make_root(graph(), {"exact": True}, [{"source_language": "c"}], project_id="project")
        candidate = make_candidate(root["root_id"], {"family": "baseline", "parameters": {}}, {"architecture": "x86_64"}, {"size": 8}, baseline=True)
        observation = make_observation(candidate["candidate_id"], "proof", "proof_passed", {"method": "fixture"}, quality_grade="C")
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            manifest = root_path / "bundle.json"
            manifest.write_text(json.dumps({"roots": [root], "candidates": [candidate], "observations": [observation]}))
            first = ingest_bundle(manifest, root_path / "store")
            second = ingest_bundle(manifest, root_path / "store")
            self.assertEqual(first["dataset_hash"], second["dataset_hash"])
            self.assertEqual(second["ingested"]["roots"]["added"], 0)

    def test_end_to_end_training_is_deterministic_and_baseline_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            generate_synthetic_prior_corpus(root_path / "corpus", root_count=36)
            store = PriorExperienceStore(root_path / "corpus" / "experience")
            dataset = store.load()
            split = build_splits(dataset, method="project", seed=7)
            first = train_prior_model(dataset, split, root_path / "model-a", ensemble_size=2, epochs=25, seed=9)
            second = train_prior_model(dataset, split, root_path / "model-b", ensemble_size=2, epochs=25, seed=9)
            self.assertEqual(first["model_hash"], second["model_hash"])
            model = load_prior_model(root_path / "model-a" / "prior-model.json")
            report = shadow_evaluate(model, dataset, split["test"])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["baseline_suppression_count"], 0)
            self.assertGreaterEqual(report["measurement_reduction_factor"], 5.0)
            self.assertEqual(first["production_model_status"], "insufficient_dataset")

            root_id = report["rows"][0]["root_id"]
            semantic_root = next(item for item in dataset["roots"] if item["root_id"] == root_id)
            candidates = [item for item in dataset["candidates"] if item["root_id"] == root_id]
            recommendation = recommend_candidates(model, semantic_root, candidates)
            decision = select_search_budget(recommendation, candidates, budget=4, seed=11)
            self.assertTrue(decision["baseline_retained"])
            self.assertIn("exploration_underrepresented_or_uncertain", set(decision["selection_reasons"].values()))

    def test_unseen_hardware_abstains_and_uses_exhaustive_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            generate_synthetic_prior_corpus(root_path / "corpus", root_count=30)
            store = PriorExperienceStore(root_path / "corpus" / "experience"); dataset = store.load()
            split = build_splits(dataset, method="root", seed=3)
            train_prior_model(dataset, split, root_path / "model", ensemble_size=2, epochs=20, seed=4)
            model = load_prior_model(root_path / "model" / "prior-model.json")
            base_root = dataset["roots"][0]
            foreign_hardware = {"architecture": "riscv64", "vendor": "unknown", "isa": ["v"], "device_class": "cpu"}
            workload = dataset["candidates"][0]["workload"]
            foreign = [
                make_candidate(base_root["root_id"], {"family": "baseline", "parameters": {}}, foreign_hardware, workload, baseline=True),
                make_candidate(base_root["root_id"], {"family": "stable_compaction", "parameters": {}}, foreign_hardware, workload),
            ]
            recommendation = recommend_candidates(model, base_root, foreign)
            self.assertTrue(recommendation["abstention"]["required"])
            decision = select_search_budget(recommendation, foreign, budget=1)
            self.assertEqual(set(decision["selected_candidate_ids"]), {item["candidate_id"] for item in foreign})
            self.assertEqual(decision["mode"], "model_abstained_exhaustive_fallback")

    def test_manifest_workflow_emits_decisive_nonproduction_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            manifest = root_path / "prior.yaml"
            raw = initialize_prior_manifest(manifest)
            raw["dataset"]["root_count"] = 24
            raw["model"]["ensemble_size"] = 2
            raw["model"]["epochs"] = 12
            manifest.write_text(__import__("yaml").safe_dump(raw, sort_keys=False))
            with patch.dict("os.environ", {"VLADDER_CONSENT_FILE": str(root_path / "consent.json")}):
                summary = run_prior_workflow(manifest, root_path / "out")
            self.assertTrue(summary["workflow_completed"])
            self.assertFalse(summary["live_search_pruned"])
            self.assertEqual(summary["production_model_status"], "insufficient_dataset")
            self.assertEqual(len(summary["decisive_artifacts"]), 5)
            contribution = summary["optional_canonical_training_contribution"]
            self.assertEqual(contribution["status"], "consent_required")
            self.assertFalse(contribution["network_action_performed"])
            self.assertTrue((root_path / "out/prior-summary.json").exists())

    def test_generalization_matrix_reports_independent_views(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            generate_synthetic_prior_corpus(root_path / "corpus", root_count=30)
            report = evaluate_prior_generalization(
                root_path / "corpus/experience", root_path / "matrix",
                methods=("root", "project", "language", "hardware", "temporal"),
                ensemble_size=1, epochs=3, seed=5,
            )
            self.assertEqual(set(report["views"]), {"root", "project", "language", "hardware", "temporal"})
            self.assertTrue(all(view["baseline_suppression_count"] == 0 for view in report["views"].values()))
            self.assertTrue((root_path / "matrix/generalization-summary.json").exists())


if __name__ == "__main__":
    unittest.main()
