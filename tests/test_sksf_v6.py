from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from vladder.kernel_graph import kernel_graph_from_projection
from vladder.kernel_search import search_kernel_graph
from vladder.portfolio_v6 import rank_portfolio
from vladder.projection_graph import load_projection_graph
from vladder.sksf_attribution import evaluate_grammar_admission, load_attribution_study
from vladder.sksf_workflow import synthesize_kernel_v6


ROOT = Path(__file__).resolve().parent.parent
STUDY_PATH = ROOT / "examples" / "sksf" / "attribution" / "qwen3_q4km_projection_v6.json"


class SksfV6Tests(unittest.TestCase):
    def test_attribution_hash_and_admission_gate(self) -> None:
        study = load_attribution_study(STUDY_PATH)
        self.assertEqual(len(study.study_hash), 64)
        studies = {study.id: study}
        admitted = evaluate_grammar_admission("decode", {
            "study_id": study.id,
            "bottleneck_ids": ["all-fused-projection-token1"],
            "target_metric": "fused_projection_time_us",
            "expected_direction": "decrease",
            "allow_instrumented_attribution": True,
        }, studies)
        self.assertEqual(admitted.state, "admitted")
        exploratory = evaluate_grammar_admission("activation", {
            "study_id": study.id,
            "bottleneck_ids": ["activation-prepare-token1"],
            "target_metric": "activation_prepare_time_us",
            "expected_direction": "decrease",
            "allow_instrumented_attribution": True,
        }, studies)
        self.assertEqual(exploratory.state, "exploratory")
        rejected = evaluate_grammar_admission("materialization", {
            "study_id": study.id,
            "bottleneck_ids": ["all-fused-projection-token1"],
            "target_metric": "temporary_bytes",
            "expected_direction": "decrease",
        }, studies)
        self.assertEqual(rejected.state, "rejected")

    def test_kernel_graph_and_gated_search_are_deterministic(self) -> None:
        projection = load_projection_graph(ROOT / "examples" / "projections" / "qwen3_ffn_gate_up_v5.yaml")
        graph = kernel_graph_from_projection(projection)
        self.assertEqual(graph.schema_version, "vladder-kernel-graph-v6.0")
        self.assertIn("DotProduct", {node.kind for node in graph.nodes})
        study = load_attribution_study(STUDY_PATH)
        first = search_kernel_graph(graph, ROOT / "vladder" / "grammars" / "kernel-v6", {study.id: study}, beam_width=12, max_depth=5)
        second = search_kernel_graph(graph, ROOT / "vladder" / "grammars" / "kernel-v6", {study.id: study}, beam_width=12, max_depth=5)
        self.assertEqual(first.grammar_hash, second.grammar_hash)
        self.assertEqual(first.candidates, second.candidates)
        states = {item.family: item.state for item in first.admissions}
        self.assertEqual(states["activation_preparation"], "exploratory")
        self.assertEqual(states["materialization"], "rejected")
        self.assertEqual(states["kv_pressure"], "rejected")
        self.assertNotIn("activation_preparation", {family for item in first.candidates for family in item.families})
        tiled = [item for item in first.candidates if "token_reuse" in item.families]
        self.assertTrue(tiled)
        self.assertTrue(all(any("token_count" in guard for guard in item.guards) for item in tiled))

    def test_workflow_emits_non_claiming_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = synthesize_kernel_v6(
                ROOT / "examples" / "projections" / "qwen3_qkv_v5.yaml",
                [STUDY_PATH], ROOT / "vladder" / "grammars" / "kernel-v6", Path(directory), beam_width=8, max_depth=4,
            )
            self.assertIn("No kernel or portfolio performance claim", report["claim"])
            self.assertTrue((Path(directory) / "grammar-admissions.json").is_file())
            self.assertTrue((Path(directory) / "search-audit.json").is_file())
            self.assertTrue(all(item["measurement_status"] == "NOT_RUN" for item in report["candidates"]))

    def test_portfolio_rejects_hidden_regression(self) -> None:
        manifest = {
            "minimum_portfolio_improvement_percent": 5,
            "workloads": {
                "interactive_decode": {"weight": 0.3, "minimum_relative_performance": 0.99},
                "prompt_processing": {"weight": 0.2, "minimum_relative_performance": 1.0},
                "concurrent_serving": {"weight": 0.35, "minimum_relative_performance": 1.02},
                "kv_pressure": {"weight": 0.15, "minimum_relative_performance": 0.98},
            },
        }
        measurements = {
            "interactive_decode": {"baseline": [10, 10.1, 9.9], "candidate": [11, 11.1, 10.9]},
            "prompt_processing": {"baseline": [20, 20.1, 19.9], "candidate": [22, 22.1, 21.9]},
            "concurrent_serving": {"baseline": [30, 30.1, 29.9], "candidate": [34, 34.1, 33.9]},
            "kv_pressure": {"baseline": [8, 8.1, 7.9], "candidate": [7, 7.1, 6.9]},
        }
        report = rank_portfolio(manifest, measurements, bootstrap_rounds=500)
        self.assertFalse(report["accepted"])
        self.assertGreater(report["portfolio_improvement_percent"], 5)
        kv = next(item for item in report["workloads"] if item["name"] == "kv_pressure")
        self.assertFalse(kv["accepted"])


if __name__ == "__main__":
    unittest.main()
