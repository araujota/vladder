from pathlib import Path
import tempfile
import unittest

from vladder.extractor import extract_function
from vladder.flow import analyze_ir, build_flow_graph, emit_target_ir
from vladder.toolchain import discover_toolchain


EXPECTED = {
    "01_affine_scale_bias": ("pointwise_map", "affine"),
    "02_affine_add": ("pointwise_map", "affine"),
    "03_divide_by_two": ("pointwise_map", "div_const"),
    "04_divide_by_four": ("pointwise_map", "div_const"),
    "05_clamp_unit": ("guarded_pointwise_map", "saturating_projection"),
    "06_clamp_positive": ("guarded_pointwise_map", "saturating_projection"),
    "07_abs_branch": ("guarded_pointwise_map", "abs_preserve_negzero"),
    "08_relu": ("guarded_pointwise_map", "relu"),
    "09_leaky_relu": ("guarded_pointwise_map", "leaky_relu"),
    "10_threshold": ("guarded_pointwise_map", "threshold01"),
    "11_square": ("pointwise_map", "pointwise_expr"),
    "12_cubic": ("pointwise_map", "pointwise_expr"),
    "13_poly3": ("pointwise_map", "pointwise_expr"),
    "14_reciprocal_shift": ("pointwise_map", "pointwise_expr"),
    "15_stencil3": ("stencil", "neighborhood"),
    "16_moving_average5": ("stencil", "neighborhood"),
    "17_prefix_sum": ("scan", "prefix_sum"),
    "18_running_max": ("scan", "running_max"),
    "19_sign": ("guarded_pointwise_map", "signum"),
    "20_softsign": ("guarded_pointwise_map", "conditional_pointwise"),
    "21_blend_constants": ("guarded_pointwise_map", "conditional_pointwise"),
    "22_deadzone": ("guarded_pointwise_map", "conditional_pointwise"),
    "23_gain_gate": ("guarded_pointwise_map", "conditional_pointwise"),
    "24_iir_like": ("recurrence", "iir"),
    "25_stride_mix": ("indirect_memory", "strided_indirect"),
}


class CorpusShapeTests(unittest.TestCase):
    def test_all_corpus_shapes_from_ir(self):
        root = Path(__file__).resolve().parent.parent
        tc = discover_toolchain()
        with tempfile.TemporaryDirectory() as tmp:
            for source in sorted((root / "examples" / "corpus").glob("*.c")):
                with self.subTest(kernel=source.stem):
                    info = emit_target_ir(tc, source, Path(tmp) / source.stem, "transform")
                    slice_ = analyze_ir(info, "transform")
                    fn = extract_function(source.read_text(), "transform")
                    graph = build_flow_graph(fn, info["stats"], slice_)
                    self.assertEqual((graph.family, graph.canonical), EXPECTED[source.stem])
                    self.assertGreaterEqual(len(slice_.roots), 1)


if __name__ == "__main__":
    unittest.main()
