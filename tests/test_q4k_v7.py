from __future__ import annotations

import random
import unittest

from vladder.q4k_capture import parse_q4k_path_records
from vladder.q4k_semantics import (
    Q4KBlock, Q4K_NODE_KINDS, build_q4k_kernel_graph, decode_scale_min,
    pack_scale_min, verify_repack_bijection,
)
from vladder.q4k_sibling import _attribution_report, _enumerate_grammar


class Q4KProductionV7Tests(unittest.TestCase):
    def test_capture_parser_preserves_dispatch_contract(self) -> None:
        line = (
            "VLADDER_Q4K_PATH|tensor=ffn_gate-0|kernel=ggml_gemv_q4_K_8x8_q8_K|"
            "weight_type=q4_K|activation_source_type=f32|activation_block_type=q8_K|"
            "repack_type=block_q4_Kx8|interleave=8|output_row_group=8|input=2560|"
            "outputs=9728|tokens=1|threads=8|gemm_threshold=4|tail=gemv|avx2=1"
        )
        record = parse_q4k_path_records(line)[0]
        self.assertEqual(record["category"], "ffn_gate_up")
        self.assertEqual(record["kernel"], "ggml_gemv_q4_K_8x8_q8_K")
        self.assertEqual((record["input"], record["outputs"], record["tokens"]), (2560, 9728, 1))

    def test_scale_min_codec_and_native_repack_are_bijective(self) -> None:
        rng = random.Random(7)
        blocks = []
        for row in range(8):
            scales = [(row*7 + index*3) % 64 for index in range(8)]
            minima = [(row*11 + index*5) % 64 for index in range(8)]
            packed = pack_scale_min(scales, minima)
            self.assertEqual([decode_scale_min(packed, index)[0] for index in range(8)], scales)
            self.assertEqual([decode_scale_min(packed, index)[1] for index in range(8)], minima)
            blocks.append(Q4KBlock(0x3800, 0x3400, packed, bytes(rng.randrange(256) for _ in range(128))))
        proof = verify_repack_bijection(tuple(blocks), 8)
        self.assertEqual(proof["status"], "proved")
        self.assertTrue(proof["deterministic"])
        self.assertEqual(proof["padding_bytes"], 0)

    def test_graph_has_complete_typed_provenance(self) -> None:
        graph = build_q4k_kernel_graph({"status": "PASS", "runtime_contract": {"interleave": 8}})
        self.assertEqual({node.kind for node in graph.nodes}, Q4K_NODE_KINDS)
        self.assertTrue(all(node.provenance for node in graph.nodes))
        self.assertTrue(all(edge.exactness_obligation for edge in graph.edges))
        self.assertEqual(len(graph.graph_hash), 64)

    def test_narrow_grammar_has_sound_local_coverage(self) -> None:
        audit = _enumerate_grammar()
        self.assertEqual(audit["enumerated"], 36)
        self.assertEqual(audit["legal"], 6)
        self.assertEqual(audit["classification"], "best_verified_found")
        self.assertEqual(audit["control_product_coverage"], "exhaustive_legality")
        self.assertTrue(all(item["row_group"] == 8 for item in audit["legal_plans"]))

    def test_attribution_rejects_unprofitable_load_family(self) -> None:
        rankings = [{"candidate": "fused_shared_q8_loads", "speedup_percent": -2.0, "speedup_95": [-4.0, 1.0]}]
        report = _attribution_report(rankings, {"fused": {}}, {}, n=2560, nc=9728)
        self.assertEqual(report["promotion_decision"]["state"], "rejected_for_expansion")
        self.assertGreater(report["byte_model"]["sibling_weight_bytes"], report["byte_model"]["activation_bytes_removed"])


if __name__ == "__main__":
    unittest.main()
