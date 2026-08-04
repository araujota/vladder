from pathlib import Path
import unittest

from vladder.extractor import extract_function
from vladder.flow import build_flow_graph
from vladder.grammar_search import search_candidates
from vladder.memory_proofs import prove_memory_safety


CLAMP = """
void transform(float *dst, const float *src, size_t n) {
  for (size_t i = 0; i < n; ++i) {
    float x = src[i];
    if (x < -1.0f) dst[i] = -1.0f;
    else if (x > 1.0f) dst[i] = 1.0f;
    else dst[i] = x;
  }
}
"""


class GrammarAndMemoryTests(unittest.TestCase):
    def test_clamp_search_saturates_and_lifts(self):
        fn = extract_function(CLAMP, "transform")
        graph = build_flow_graph(fn)
        grammar_dir = Path(__file__).resolve().parent.parent / "vladder" / "grammars"
        result = search_candidates(fn, graph, {"avx2"}, True, grammar_dir)
        self.assertEqual(result.status, "saturated_optimal")
        names = {candidate.name for candidate in result.candidates}
        self.assertIn("grammar_select_saturating_projection", names)
        self.assertIn("grammar_avx2_saturating_projection", names)
        self.assertTrue(any("dst[i]" in c.source for c in result.candidates))

    def test_search_budget_is_reported(self):
        fn = extract_function(CLAMP, "transform")
        graph = build_flow_graph(fn)
        grammar_dir = Path(__file__).resolve().parent.parent / "vladder" / "grammars"
        result = search_candidates(fn, graph, {"avx2"}, True, grammar_dir, node_budget=1)
        self.assertEqual(result.status, "best_found")

    def test_pointer_footprint_proof(self):
        fn = extract_function(CLAMP, "transform")
        graph = build_flow_graph(fn)
        grammar_dir = Path(__file__).resolve().parent.parent / "vladder" / "grammars"
        result = search_candidates(fn, graph, {"avx2"}, True, grammar_dir)
        vector = next(c for c in result.candidates if c.name.startswith("grammar_avx2"))
        proof = prove_memory_safety(graph, vector, True)
        self.assertEqual(proof.status, "proved")
        self.assertIn("src[0:n] and dst[0:n] are disjoint", proof.preconditions)


if __name__ == "__main__":
    unittest.main()
