from pathlib import Path
import tempfile
import unittest

from vladder.c_lift import graph_ast, parse_c_expr
from vladder.extractor import extract_function
from vladder.flow import build_flow_graph
from vladder.llm_lifter import _decode_response, _validate_source
from vladder.toolchain import discover_toolchain


class CLiftTests(unittest.TestCase):
    def test_expression_ast_round_trip(self):
        expression = parse_c_expr("x > 0.0f ? x : x * 0.125f")
        self.assertEqual(expression.render(), "x > 0.0f ? x : x * 0.125f")

    def test_unbound_local_is_not_lifted(self):
        source = "void transform(float *dst,const float *src,size_t n){for(size_t i=0;i<n;++i){float x=src[i];float ax=x<0?-x:x;dst[i]=x/(1.0f+ax);}}"
        graph = build_flow_graph(extract_function(source, "transform"))
        self.assertIsNone(graph_ast(graph))

    def test_llm_response_is_strict_json(self):
        source, error = _decode_response('{"c_source":"void transform_candidate(float *dst, const float *src, size_t n) {}"}')
        self.assertIsNone(error)
        self.assertIn("transform_candidate", source)
        _, error = _decode_response('{"c_source":"x", "explanation":"trust me"}')
        self.assertIsNotNone(error)

    def test_llm_proposal_must_match_graph_constants(self):
        original = "void transform(float *dst,const float *src,size_t n){for(size_t i=0;i<n;++i)dst[i]=src[i]*2.0f+1.0f;}"
        graph = build_flow_graph(extract_function(original, "transform"))
        proposal = "void transform_candidate(float *dst, const float *src, size_t n) { for (size_t i=0;i<n;++i) dst[i]=src[i]*3.0f+1.0f; }"
        with tempfile.TemporaryDirectory() as tmp:
            errors = _validate_source(proposal, graph, discover_toolchain(), Path(tmp))
        self.assertTrue(any("constants" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
