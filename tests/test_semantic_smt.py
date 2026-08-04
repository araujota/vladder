from pathlib import Path
import tempfile
import unittest

from vladder.extractor import extract_function
from vladder.flow import build_flow_graph
from vladder.semantic_smt import emit_semantic_smt


class SemanticSMTTests(unittest.TestCase):
    def test_affine_array_model_is_emitted(self):
        source = "void transform(float *dst, const float *src, size_t n) { for (size_t i=0;i<n;++i) dst[i]=src[i]*2.0f+1.0f; }"
        graph = build_flow_graph(extract_function(source, "transform"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.smt2"
            result = emit_semantic_smt(graph, path, lanes=4)
            self.assertEqual(result.status, "encoded")
            text = path.read_text()
            self.assertIn("dst_after", text)
            self.assertIn("fp.mul", text)
            self.assertIn("unrolled lanes: 4", text)


if __name__ == "__main__":
    unittest.main()
