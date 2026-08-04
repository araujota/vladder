from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from vladder.projection_graph import load_projection_graph
from vladder.projection_layout import interleave_sibling_blocks, inverse_sibling_interleave, verify_layout_round_trip
from vladder.projection_profile import parse_projection_profile
from vladder.projection_search import FAMILIES, search_projection_graph
from vladder.projection_v5 import synthesize_projection_v5, transform_projection_layout_v5
from vladder.projection_verification import verify_projection_plan


ROOT = Path(__file__).resolve().parent.parent


class ProjectionV5Tests(unittest.TestCase):
    def test_ffn_and_qkv_graphs_are_deterministic(self) -> None:
        for name, count in (("qwen3_ffn_gate_up_v5.yaml", 2), ("qwen3_qkv_v5.yaml", 3)):
            path = ROOT / "examples" / "projections" / name
            first = load_projection_graph(path)
            second = load_projection_graph(path)
            self.assertEqual(first.graph_hash, second.graph_hash)
            self.assertEqual(first.annotations["projection_count"], count)
            self.assertGreaterEqual(first.annotations["shared_activation_fanout"], 2)
            self.assertGreater(first.annotations["cost"]["weight_bytes_read"], 0)

    def test_invalid_projection_fixtures_are_rejected(self) -> None:
        for name in ("invalid_shape_v5.yaml", "invalid_quantization_v5.yaml", "invalid_tile_v5.yaml"):
            with self.assertRaises(ValueError, msg=name):
                load_projection_graph(ROOT / "examples" / "projections" / name)

    def test_exact_sibling_layout_round_trip(self) -> None:
        payloads = [bytes(range(32)), bytes(reversed(range(32))), b"x" * 32]
        transformed, manifest = interleave_sibling_blocks(payloads, 8)
        self.assertEqual(inverse_sibling_interleave(transformed, manifest), payloads)
        proof = verify_layout_round_trip(payloads, transformed, manifest)
        self.assertEqual(proof["status"], "proved")
        self.assertEqual(proof["block_identity_count"], 12)
        self.assertEqual(proof["padding_bytes"], 0)
        tampered = {**manifest, "forward_map": [dict(entry) for entry in manifest["forward_map"]]}
        tampered["forward_map"][1]["destination_block"] = tampered["forward_map"][0]["destination_block"]
        with self.assertRaises(ValueError):
            inverse_sibling_interleave(transformed, tampered)

    def test_search_has_seven_families_guards_and_proof(self) -> None:
        graph = load_projection_graph(ROOT / "examples" / "projections" / "qwen3_ffn_gate_up_v5.yaml")
        search = search_projection_graph(graph, ROOT / "vladder" / "grammars" / "projection-v5", beam_width=16, max_depth=7)
        self.assertEqual(FAMILIES, {family for plan in search.plans for family in plan.families})
        tiled = next(plan for plan in search.plans if plan.token_tile > 1)
        self.assertTrue(any("token_count" in guard for guard in tiled.guards))
        self.assertEqual(verify_projection_plan(graph, tiled).status, "proved")
        self.assertEqual(search.status, "best_verified_found")

    def test_profile_parser_preserves_fused_boundary(self) -> None:
        line = "VLADDER_PROJECTION|name=ffn_gate-0|backend=native_repack|weight_type=q4_K|activation_type=f32|input=2560|outputs=9728|tokens=1|prep_cycles=20|prep_us=3|sync_cycles=4|sync_us=1|fused_cycles=800|fused_us=100"
        report = parse_projection_profile(line)
        result = report["token_count_regimes"]["1"]["projection_categories"]["ffn_gate_up"]
        self.assertAlmostEqual(result["fraction"]["activation_prepare"], 3 / 104)
        self.assertIn("fused_weight_decode_dot_accumulate_us", result)
        self.assertEqual(report["backends"], ["native_repack"])
        self.assertTrue(any("remain one fused region" in item for item in report["limitations"]))

    def test_static_e2e_emits_nonclaiming_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = synthesize_projection_v5(
                ROOT / "examples" / "projections" / "qwen3_qkv_v5.yaml", Path(directory), beam_width=12, max_depth=5,
            )
            self.assertEqual(report["physical_measurement"]["status"], "NOT_RUN")
            self.assertEqual(report["winner"]["proof"]["status"], "proved")
            self.assertTrue((Path(directory) / "projection_candidates.csv").is_file())
            persisted = json.loads((Path(directory) / "projection_report.json").read_text())
            self.assertIn("no physical performance claim", persisted["claim"])

    def test_layout_workflow_emits_verified_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [root / "gate.bin", root / "up.bin"]
            inputs[0].write_bytes(bytes(range(32)))
            inputs[1].write_bytes(bytes(reversed(range(32))))
            report = transform_projection_layout_v5(inputs, 8, root / "out")
            self.assertEqual(report["proof"]["status"], "proved")
            self.assertTrue((root / "out" / "transformed-layout.bin").is_file())
            self.assertTrue((root / "out" / "layout-manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
