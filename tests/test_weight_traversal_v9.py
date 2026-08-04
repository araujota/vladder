from __future__ import annotations

from pathlib import Path
import unittest

from vladder.weight_traversal_graph import NODE_KINDS, load_weight_traversal_graph
from vladder.weight_traversal_search import (
    WeightTraversalPlan, _legal, search_weight_traversal_graph, simulate_requests, synthesize_dispatch,
)
from vladder.weight_traversal_v9 import _identity_adjusted_ranking, _verify_simulations, _weight_accounting


ROOT = Path(__file__).resolve().parents[1]


class WeightTraversalV9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_weight_traversal_graph(ROOT / "examples/workloads/qwen3_weight_reuse_v9.yaml")
        cls.calibration = {
            "regional_weight_bytes": 14_008_320, "input_dimension": 2560,
            "output_dimension": 9728, "model_weight_bytes": 2_491_323_904,
            "model_macs_per_token": 4_022_468_096, "decode_tokens_per_second": 23.5,
            "prompt_tokens_per_second": 177.2,
            "decode_iteration_us": {"1": 42000.0, "2": 76000.0, "4": 120000.0, "8": 180000.0},
            "lane_efficiency": {"1": 1.0, "2": 1.1, "4": 1.4, "8": 1.8},
        }

    def test_graph_instantiates_complete_v9_vocabulary(self) -> None:
        self.assertEqual({node.kind for node in self.graph.nodes}, NODE_KINDS)
        self.assertTrue(all(edge.exactness == "E1" for edge in self.graph.edges))
        self.assertEqual(len(self.graph.graph_hash), 64)

    def test_autoregressive_and_projection_legality_fail_closed(self) -> None:
        legal, reason = _legal(self.graph, 4, 1, "independent", "weight_major", "decode", False)
        self.assertFalse(legal)
        self.assertIn("autoregressive", reason)
        legal, reason = _legal(self.graph, 1, 4, "gate_up", "weight_major", "continuous_batch", False)
        self.assertFalse(legal)
        self.assertIn("V8 admitted no", reason)

    def test_search_exhausts_bounded_product_and_has_fallback(self) -> None:
        search = search_weight_traversal_graph(self.graph, self.calibration)
        self.assertEqual(search["coverage"]["raw_cross_product"], 3840)
        self.assertEqual(search["coverage"]["enumeration"], "exhaustive bounded grammar")
        self.assertGreater(search["coverage"]["legal"], 0)
        dispatch = synthesize_dispatch(self.graph, search)
        self.assertTrue(dispatch.rules[-1].fallback)
        self.assertEqual(dispatch.rules[-1].guard, "true")

    def test_simulator_preserves_sequence_state(self) -> None:
        baseline = WeightTraversalPlan(
            "test", 1, 4, "independent", "mixed", "continuous_batch", False,
            0, 32, ("true",), "test", 1.0, 1.0, 1.0, 0.0, "eligible",
        )
        requests = [
            {"id": index, "arrival_us": index * 10, "prompt_tokens": 4 + index, "generated_tokens": 3}
            for index in range(4)
        ]
        report = simulate_requests(baseline, requests, self.calibration)
        self.assertEqual(report["semantic_status"], "PASS")
        self.assertEqual([item["decode"] for item in report["state_final"]], [3, 3, 3, 3])
        self.assertGreater(report["useful_macs_per_streamed_weight_byte"], 0)

    def test_state_verifier_ignores_schedule_but_not_results(self) -> None:
        state = [{"id": 0, "prompt": 4, "decode": 2, "complete": 10.0}]
        good = {"x": {"baseline": {"state_final": state}, "selected": {"state_final": [{**state[0], "complete": 5.0}]}}}
        self.assertEqual(_verify_simulations(good)["status"], "PASS")
        bad = {"x": {"baseline": {"state_final": state}, "selected": {"state_final": [{**state[0], "decode": 1}]}}}
        self.assertEqual(_verify_simulations(bad)["status"], "FAIL")

    def test_identical_implementations_are_not_ranked_from_noise(self) -> None:
        raw = {"classification": "measured_regression", "accepted": False}
        adjusted = _identity_adjusted_ranking(raw, {"deduplicated": True})
        self.assertEqual(adjusted["classification"], "implementation_identity_tie")
        self.assertEqual(adjusted["effective_portfolio_improvement_percent"], 0.0)
        self.assertFalse(adjusted["accepted"])

    def test_weight_accounting_labels_logical_proxy(self) -> None:
        physical = {
            "causal_batching_ablation": {
                "concurrent": {
                    "batched": {"pl": 4, "speed_tg": 40.0},
                    "sequential": {"speed_tg": 10.0},
                }
            }
        }
        report = _weight_accounting(self.graph, physical)
        row = report["workloads"]["concurrent"]
        self.assertEqual(row["intensity_multiplier"], 4)
        self.assertIn("logical_useful_macs_per_sequential_model_byte_proxy", row)
        self.assertIn("external DRAM bytes were not isolated", report["byte_scope"])


if __name__ == "__main__":
    unittest.main()
