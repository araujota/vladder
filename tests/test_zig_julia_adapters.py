from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from vladder.language_adapter import SEMANTIC_NODE_KINDS
from vladder.zig_adapter import ZigRegionRequest, audit_zig_regions, inspect_zig_region, optimize_zig_region, synthesize_zig_region
from vladder.julia_adapter import JuliaRegionRequest, audit_julia_regions, inspect_julia_region, optimize_julia_region, synthesize_julia_region


ROOT = Path(__file__).resolve().parents[1]
ZIG = ROOT / "examples" / "zig_regions" / "byte_count"
JULIA = ROOT / "examples" / "julia_regions" / "byte_count"


class ZigAdapterTests(unittest.TestCase):
    def request(self, output: Path, function: str = "countEqual") -> ZigRegionRequest:
        return ZigRegionRequest(ZIG / "src" / "root.zig", function, output, build_root=ZIG, proof_bound=4, benchmark_elements=4096, benchmark_inner=8, benchmark_processes=2, benchmark_repetitions=1)

    @unittest.skipUnless(shutil.which("zig"), "Zig toolchain unavailable")
    def test_capture_uses_shared_vocabulary_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_zig_region(self.request(Path(directory) / "good"))
            self.assertEqual(report["status"], "supported")
            self.assertEqual(report["semantic_graph"]["source_language"], "zig")
            self.assertTrue(all(node["kind"] in SEMANTIC_NODE_KINDS for node in report["semantic_graph"]["nodes"]))
            again = inspect_zig_region(self.request(Path(directory) / "good"))
            self.assertEqual(report["semantic_graph"]["graph_hash"], again["semantic_graph"]["graph_hash"])
            blocked = inspect_zig_region(self.request(Path(directory) / "blocked", "owningCopy"))
            self.assertIn("allocation-ownership", {item["kind"] for item in blocked["blockers"]})
            self.assertNotEqual(blocked["status"], "supported")

    @unittest.skipUnless(shutil.which("zig") and shutil.which("alive-tv"), "strict Zig proof toolchain unavailable")
    def test_native_zig_synthesis_and_physical_harness(self):
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(Path(directory))
            synthesis = synthesize_zig_region(request)
            self.assertEqual(synthesis["candidate_count"], synthesis["proved_candidate_count"])
            result = optimize_zig_region(request)
            self.assertEqual(result["differential"]["status"], "PASS")
            self.assertEqual(len(result["measurements"]), synthesis["candidate_count"])

    @unittest.skipUnless(shutil.which("zig"), "Zig toolchain unavailable")
    def test_zig_audit_preserves_partial_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            report = audit_zig_regions(ROOT / "examples" / "zig_regions" / "audit.yaml", Path(directory))
            self.assertEqual(report["supported_count"], 1)


class JuliaAdapterTests(unittest.TestCase):
    def request(self, output: Path, function: str = "count_equal") -> JuliaRegionRequest:
        return JuliaRegionRequest(JULIA, JULIA / "src" / "VLadderJuliaFixture.jl", "VLadderJuliaFixture", function, "Vector{UInt8},UInt8", output, proof_bound=4, benchmark_elements=4096, benchmark_inner=8, benchmark_processes=2, benchmark_repetitions=1)

    @unittest.skipUnless(shutil.which("julia"), "Julia toolchain unavailable")
    def test_concrete_specialization_uses_shared_vocabulary_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_julia_region(self.request(Path(directory) / "good"))
            self.assertEqual(report["status"], "supported")
            self.assertEqual(report["semantic_graph"]["source_language"], "julia")
            self.assertTrue(all(node["kind"] in SEMANTIC_NODE_KINDS for node in report["semantic_graph"]["nodes"]))
            self.assertEqual(report["build_identity"]["allocated_bytes"], "0")
            blocked = inspect_julia_region(self.request(Path(directory) / "blocked", "allocating_copy"))
            self.assertIn("gc-allocation", {item["kind"] for item in blocked["blockers"]})
            unstable = inspect_julia_region(self.request(Path(directory) / "unstable", "unstable_count"))
            self.assertIn("nondeterministic-effect", {item["kind"] for item in unstable["blockers"]})

    @unittest.skipUnless(shutil.which("julia") and shutil.which("alive-tv"), "strict Julia proof toolchain unavailable")
    def test_native_julia_synthesis_and_physical_harness(self):
        with tempfile.TemporaryDirectory() as directory:
            request = self.request(Path(directory))
            synthesis = synthesize_julia_region(request)
            self.assertEqual(synthesis["candidate_count"], synthesis["proved_candidate_count"])
            result = optimize_julia_region(request)
            self.assertEqual(result["differential"]["status"], "PASS")
            self.assertEqual(len(result["measurements"]), synthesis["candidate_count"])

    @unittest.skipUnless(shutil.which("julia"), "Julia toolchain unavailable")
    def test_julia_audit_preserves_partial_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            report = audit_julia_regions(ROOT / "examples" / "julia_regions" / "audit.yaml", Path(directory))
            self.assertEqual(report["supported_count"], 1)


if __name__ == "__main__":
    unittest.main()
