import unittest

from vladder.extractor import extract_function
from vladder.flow import build_flow_graph


def graph_for(expr: str):
    source = f"""
    #include <stddef.h>
    void transform(float *dst, const float *src, size_t n) {{
        {expr}
    }}
    """
    return build_flow_graph(extract_function(source, "transform"))


class FlowTests(unittest.TestCase):
    def test_affine_shape(self):
        graph = graph_for("for (size_t i = 0; i < n; ++i) { dst[i] = src[i] * 2.0f + 1.0f; }")
        self.assertEqual(graph.family, "pointwise_map")
        self.assertEqual(graph.canonical, "affine")
        self.assertTrue(graph.invariants["pointwise_independent"])

    def test_clamp_shape(self):
        graph = graph_for(
            """
            for (size_t i = 0; i < n; ++i) {
                float x = src[i];
                if (x < -1.0f) { dst[i] = -1.0f; }
                else if (x > 1.0f) { dst[i] = 1.0f; }
                else { dst[i] = x; }
            }
            """
        )
        self.assertEqual(graph.family, "guarded_pointwise_map")
        self.assertEqual(graph.canonical, "saturating_projection")

    def test_scan_shape(self):
        graph = graph_for("float sum = 0.0f; for (size_t i = 0; i < n; ++i) { sum += src[i]; dst[i] = sum; }")
        self.assertEqual(graph.family, "scan")
        self.assertEqual(graph.invariants["loop_carried_dependence"], "sum")

    def test_stencil_shape(self):
        graph = graph_for(
            """
            for (size_t i = 0; i < n; ++i) {
                if (i < 2 || i + 2 >= n) { dst[i] = src[i]; }
                else { dst[i] = src[i - 2] + src[i - 1] + src[i] + src[i + 1] + src[i + 2]; }
            }
            """
        )
        self.assertEqual(graph.family, "stencil")
        self.assertEqual(graph.source_pattern["neighbor_offsets"], [-2, -1, 0, 1, 2])


if __name__ == "__main__":
    unittest.main()
