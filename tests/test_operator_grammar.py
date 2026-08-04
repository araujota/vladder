from pathlib import Path
import subprocess
import tempfile
import unittest

from vladder.operator_analysis import analyze_operator
from vladder.operator_grammar import load_operator_grammar, search_operator_graph, transformed_graph_dict
from vladder.operator_lift import lift_operator_candidates
from vladder.toolchain import discover_toolchain


class OperatorGrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent
        cls.source = cls.root / "examples/operators/residual_rmsnorm_quant.c"
        cls.contract_path = cls.root / "examples/operators/contracts/residual_rmsnorm_quant.yaml"
        cls.grammar_dir = cls.root / "vladder" / "grammars" / "operator-v3"

    def test_six_grammar_families_and_minimum_rules(self):
        rules, digest = load_operator_grammar(self.grammar_dir)
        families = {rule.family for rule in rules}
        self.assertEqual(families, {"fusion", "layout", "reduction", "control", "schedule", "specialization"})
        self.assertGreaterEqual(sum(rule.family == "fusion" for rule in rules), 3)
        self.assertGreaterEqual(sum(rule.family == "layout" for rule in rules), 2)
        self.assertGreaterEqual(sum(rule.family == "reduction" for rule in rules), 3)
        self.assertEqual(len(digest), 64)

    def test_search_and_graph_ast_lifting(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract, graph, _ = analyze_operator(self.source, self.contract_path, Path(tmp))
            result = search_operator_graph(contract, graph, self.grammar_dir, beam_width=32)
            candidates = lift_operator_candidates(contract, self.source.read_text(), result.plans)
            names = {candidate.name for candidate in candidates}
            self.assertIn("synth_fused_linear", names)
            self.assertIn("synth_fused_multi4", names)
            self.assertIn("synth_fused_pairwise", names)
            fused_plan = next(candidate.plan for candidate in candidates if candidate.name == "synth_fused_linear")
            after = transformed_graph_dict(graph, fused_plan)
            self.assertLess(after["annotations"]["estimated_materialized_bytes"], graph.annotations["estimated_materialized_bytes"])
            self.assertTrue(result.audit)

    def test_layout_adapter_is_guarded_and_compiles(self):
        source = self.root / "examples/operators/token_operator_suite.c"
        contract_path = self.root / "examples/operators/contracts/rope_qk.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            contract, graph, _ = analyze_operator(source, contract_path, Path(tmp))
            result = search_operator_graph(contract, graph, self.grammar_dir, beam_width=32)
            candidates = lift_operator_candidates(contract, source.read_text(), result.plans)
            adapter = next(candidate for candidate in candidates if candidate.name == "split_plane_adapter_128")
            path = Path(tmp) / "adapter.c"
            path.write_text("#include <stddef.h>\n" + adapter.source + "\n")
            compiler = discover_toolchain().compiler
            subprocess.run([compiler, "-std=c17", "-Werror", "-fsyntax-only", str(path)], check=True)
            self.assertIn("pairs <= 128", adapter.preconditions[0])


if __name__ == "__main__":
    unittest.main()
