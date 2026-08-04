import unittest

from vladder.ggml_profile import parse_ggml_profile


class GGMLProfileV4Tests(unittest.TestCase):
    def test_profile_classifies_fused_and_projection_regions(self):
        graph = {"nodes": [
            {"kind": "compute", "index": 0, "shape": [2560, 1]},
            {"kind": "compute", "index": 3, "shape": [4096, 1]},
            {"kind": "compute", "index": 31, "shape": [9728, 1]},
        ]}
        one = "\n".join([
            "VLADDER_PROFILE|graph_begin|nodes=3",
            "VLADDER_PROFILE|node=0|op=ADD|fused=2|cycles=10|us=10|name=ffn_inp-0",
            "VLADDER_PROFILE|node=3|op=MUL_MAT|fused=0|cycles=20|us=20|name=Qcur-0",
            "VLADDER_PROFILE|node=31|op=MUL_MAT|fused=0|cycles=50|us=50|name=ffn_gate-0",
            "VLADDER_PROFILE|graph_end",
        ])
        report = parse_ggml_profile(one + "\n" + one, graph)
        self.assertEqual(report["graph_samples"], 1)
        self.assertEqual(report["categories"]["residual_norm_fused"]["median_us"], 10)
        self.assertEqual(report["categories"]["qkv_projection"]["median_us"], 20)
        self.assertEqual(report["categories"]["ffn_projection"]["median_us"], 50)
        self.assertTrue(report["stage1_to_stage3_addressable"]["addressable_coverage_25pct"])
        self.assertFalse(report["stage1_to_stage3_addressable"]["research_milestone_25pct"])


if __name__ == "__main__":
    unittest.main()
