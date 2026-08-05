from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from vladder.api import AutomaticRegionRequest, BenchmarkPolicy, VelocityLadder
from vladder.automatic import inspect_automatic_region, loop_hint_candidate, ordered_unroll_candidate
from vladder.extractor import extract_function
from vladder.flow import analyze_ir, build_flow_graph, emit_target_ir
from vladder.toolchain import discover_toolchain


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "examples" / "automatic_regions"
SUPPORTED = {
    "supported_pointwise.c": ("pointwise_map", "pointwise_expr"),
    "supported_guarded.c": ("guarded_pointwise_map", "relu"),
    "supported_stencil.c": ("stencil", "neighborhood"),
    "supported_scan.c": ("scan", "prefix_sum"),
    "supported_recurrence.c": ("recurrence", "iir"),
    "supported_indirect.c": ("indirect_memory", "strided_indirect"),
}
ADAPTERS = {
    "adapter_external_call.c": "external-call-adapter",
    "adapter_multi_loop.c": "loop-shape-adapter",
    "adapter_wrong_abi.c": "grammar-adapter",
    "adapter_control_flow.c": "control-flow-adapter",
}


class AutomaticRegionTests(unittest.TestCase):
    def test_supported_region_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, shape in SUPPORTED.items():
                with self.subTest(source=name):
                    report = inspect_automatic_region(FIXTURES / name, "transform", root / name)
                    self.assertTrue(report.supported)
                    self.assertEqual((report.family, report.canonical), shape)
                    self.assertEqual(report.exactness, "E1-ordered")
                    self.assertIn("LLVM refinement identity or Alive2", report.proof_layers)
                    emitted = json.loads((root / name / "automatic-support.json").read_text())
                    self.assertEqual(emitted, json.loads(json.dumps(report.to_dict())))

    def test_adapter_taxonomy_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, expected in ADAPTERS.items():
                with self.subTest(source=name):
                    report = inspect_automatic_region(FIXTURES / name, "transform", root / name)
                    self.assertFalse(report.supported)
                    self.assertEqual(report.adapters[0].kind, expected)
                    self.assertIsNone(report.lowerer)
                    self.assertEqual(report.proof_layers, ())
                    self.assertTrue((root / name / "automatic-support.json").exists())

    def test_cpp_requires_explicit_language_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "region.cpp"
            source.write_text((FIXTURES / "supported_pointwise.c").read_text())
            report = inspect_automatic_region(source, "transform", Path(directory) / "out")
            self.assertFalse(report.supported)
            self.assertEqual(report.adapters[0].kind, "language-adapter")
            self.assertIn("compile_commands", report.adapters[0].required_boundary)
            self.assertIn("vladder cpp", report.adapters[0].next_workflow)

    def test_noncanonical_first_order_c_abi_is_closed_before_grammar_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_automatic_region(
                FIXTURES / "adapter_scalar_result.c", "checksum_bytes", Path(directory) / "out"
            )
            self.assertFalse(report.supported)
            self.assertEqual(report.adapters[0].kind, "grammar-adapter")
            self.assertEqual(report.region_closure["status"], "abi_closed_grammar_missing")
            self.assertTrue(report.region_closure["c_boundary"]["modeled"])
            self.assertEqual(report.region_closure["c_boundary"]["return_type"], "uint32_t")

    def test_generated_ordered_source_and_proof_source_compile(self):
        source = FIXTURES / "supported_recurrence.c"
        tc = discover_toolchain()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ir = emit_target_ir(tc, source, root / "analysis", "transform")
            function = extract_function(source.read_text(), "transform")
            graph = build_flow_graph(function, ir["stats"], analyze_ir(ir, "transform"))
            explicit = ordered_unroll_candidate(function, graph, 4)
            proof_source = loop_hint_candidate(function, graph, 4)
            self.assertIsNotNone(explicit)
            self.assertIsNotNone(proof_source)
            self.assertIn("n - i >= 4u", explicit.source)
            self.assertIn("for (; i < n; ++i)", explicit.source)
            self.assertGreaterEqual(explicit.source.count("y = y * 0.875f"), 5)
            self.assertIn("VLADDER_PROOF", proof_source.source)
            for name, candidate in (("explicit", explicit), ("proof", proof_source)):
                candidate_path = root / f"{name}.c"
                candidate_path.write_text("#include <stddef.h>\n" + candidate.source + "\n")
                result = subprocess.run(
                    [tc.compiler, "-std=c99", "-Werror", "-fsyntax-only", str(candidate_path)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_library_request_and_adapter_result(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            request = AutomaticRegionRequest(
                FIXTURES / "adapter_wrong_abi.c",
                "transform",
                output,
                benchmark=BenchmarkPolicy(element_count=32, repetitions=1, inner_calls=1),
            )
            self.assertEqual(request.argv()[:2], ["region", "optimize"])
            result = VelocityLadder().optimize_region(request)
            self.assertEqual(result.return_code, 2)
            self.assertEqual(result.report["status"], "adapter_required")
            self.assertEqual(result.report["adapters"][0]["kind"], "grammar-adapter")


if __name__ == "__main__":
    unittest.main()
