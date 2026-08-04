import json
from pathlib import Path
import tempfile
import unittest

from vladder.pipeline_graph import load_pipeline_graph
from vladder.pipeline_search import load_pipeline_grammar, search_pipeline_graph
from vladder.pipeline_v4 import optimize_pipeline_v4
from vladder.pipeline_verification import infer_affected_fraction, verify_pipeline_plan


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "examples/pipelines/qwen3_block_v4.yaml"
GRAMMAR = ROOT / "vladder" / "grammars" / "pipeline-v4"


class PipelineGraphV4Tests(unittest.TestCase):
    def test_qwen_graph_is_deterministic_and_hierarchical(self):
        first = load_pipeline_graph(MANIFEST)
        second = load_pipeline_graph(MANIFEST)
        self.assertEqual(first.graph_hash, second.graph_hash)
        self.assertEqual(len(first.nodes), 12)
        self.assertEqual(len(first.edges), 13)
        self.assertGreater(first.annotations["max_live_logical_bytes"], 0)
        self.assertEqual(first.annotations["information_movement"]["measured_hardware_events"], None)
        self.assertFalse(first.annotations["profile_weights_measured"])

    def test_external_observer_cannot_stream(self):
        with self.assertRaisesRegex(ValueError, "externally observed"):
            load_pipeline_graph(ROOT / "examples/pipelines/invalid_external_observer_v4.yaml")

    def test_unresolved_shape_and_alias_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unbound_dimension"):
            load_pipeline_graph(ROOT / "examples/pipelines/invalid_shape_v4.yaml")
        with self.assertRaisesRegex(ValueError, "unresolved alias"):
            load_pipeline_graph(ROOT / "examples/pipelines/invalid_alias_v4.yaml")

    def test_seven_family_search_and_proof(self):
        graph = load_pipeline_graph(MANIFEST)
        rules, _ = load_pipeline_grammar(GRAMMAR)
        self.assertEqual({rule.family for rule in rules}, {"fusion", "materialization", "traversal", "layout", "state", "reduction", "scratch"})
        result = search_pipeline_graph(graph, GRAMMAR, beam_width=12, max_depth=4, child_budget=64)
        repeated = search_pipeline_graph(graph, GRAMMAR, beam_width=12, max_depth=4, child_budget=64)
        self.assertEqual(result, repeated)
        self.assertGreater(len(result.plans), 1)
        streamed = next(plan for plan in result.plans if plan.streamed_edges)
        self.assertEqual(verify_pipeline_plan(graph, streamed).status, "proved")
        self.assertLess(streamed.cost.scratch_bytes, result.plans[-1].cost.scratch_bytes + 1000000)
        self.assertTrue(any(item["action"] == "expand" and "child_budget" in item for item in result.audit))
        self.assertTrue(any(item["action"] == "reject" and "floating-point order" in item["reason"] for item in result.audit))
        constrained = search_pipeline_graph(graph, GRAMMAR, beam_width=4, max_depth=2, child_budget=4)
        self.assertTrue(any(plan.child_saturation == "best_found" for plan in constrained.plans))

    def test_inverse_amdahl_is_diagnostic(self):
        fraction = infer_affected_fraction(1.061919504643963, 1.0060345335564807)
        self.assertGreater(fraction, 0.09)
        self.assertLess(fraction, 0.12)

    def test_e2e_static_workflow_emits_auditable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            report = optimize_pipeline_v4(MANIFEST, out, beam_width=8, max_depth=3, child_budget=32)
            self.assertIsNotNone(report["winner"])
            self.assertEqual(report["physical_measurement"]["status"], "NOT_RUN")
            self.assertEqual(report["milestones"]["synthesized_measured_decode_coverage_25pct"], "OPEN")
            for relative in (
                "analysis/pipeline_graph.json", "analysis/pipeline_graph.dot", "pipeline_graph.before.json",
                "pipeline_graph.after.json", "pipeline_graph.before.dot", "pipeline_graph.after.dot",
                "pipeline_report.json", "search_audit.json", "pipeline_candidates.csv",
            ):
                self.assertTrue((out / relative).is_file(), relative)
            parsed = json.loads((out / "pipeline_report.json").read_text())
            self.assertIn("no physical speedup", parsed["claim"])


if __name__ == "__main__":
    unittest.main()
