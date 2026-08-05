from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest

from vladder.language_adapter import SEMANTIC_NODE_KINDS
from vladder.rust_adapter import (
    RustRegionRequest,
    audit_rust_regions,
    inspect_rust_region,
    synthesize_rust_region,
)
from vladder.rust_semantics import extract_rust_function
from vladder.rust_verification import extract_candidate_schedule, generate_rust_candidates


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "rust_regions" / "byte_count"


class RustAdapterTests(unittest.TestCase):
    def request(self, output: Path, function: str = "count_equal") -> RustRegionRequest:
        return RustRegionRequest(
            manifest_path=FIXTURE / "Cargo.toml",
            source=FIXTURE / "src" / "lib.rs",
            function=function,
            output_directory=output,
            proof_bound=8,
            benchmark_processes=2,
            benchmark_repetitions=1,
        )

    @unittest.skipUnless(shutil.which("cargo") and shutil.which("rustc"), "Rust toolchain unavailable")
    def test_supported_region_uses_common_semantic_vocabulary_and_pinned_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_rust_region(self.request(Path(directory)))
            self.assertEqual(report["status"], "supported")
            graph = report["semantic_graph"]
            self.assertTrue(graph["graph_hash"])
            self.assertTrue(all(node["kind"] in SEMANTIC_NODE_KINDS for node in graph["nodes"]))
            self.assertEqual(graph["source_language"], "rust")
            self.assertIn("rustc_identity", report["build_identity"])
            self.assertTrue(Path(report["artifacts"]["mir"]).exists())
            repeated = inspect_rust_region(self.request(Path(directory)))
            self.assertEqual(graph["graph_hash"], repeated["semantic_graph"]["graph_hash"])

    @unittest.skipUnless(shutil.which("cargo") and shutil.which("rustc"), "Rust toolchain unavailable")
    def test_owning_and_unsafe_regions_fail_closed_with_specific_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            owning = inspect_rust_region(self.request(Path(directory) / "owning", "owning_copy"))
            unsafe = inspect_rust_region(self.request(Path(directory) / "unsafe", "unsafe_count"))
            self.assertIn("allocation-ownership", {item["kind"] for item in owning["blockers"]})
            self.assertIn("unsafe-contract", {item["kind"] for item in unsafe["blockers"]})
            self.assertNotEqual(owning["status"], "supported")
            self.assertNotEqual(unsafe["status"], "supported")

    @unittest.skipUnless(
        shutil.which("cargo") and shutil.which("rustc") and shutil.which("alive-tv"),
        "strict Rust proof toolchain unavailable",
    )
    def test_native_candidates_pass_mir_z3_and_alive2_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            report = synthesize_rust_region(self.request(Path(directory)))
            self.assertEqual(report["status"], "pass")
            self.assertGreater(report["candidate_count"], 0)
            self.assertEqual(report["candidate_count"], report["proved_candidate_count"])
            for item in report["candidates"]:
                self.assertEqual(item["mir_validation"]["status"], "PASS")
                self.assertEqual(item["mir_proof"]["status"], "PASS")
                self.assertEqual(item["llvm_refinement"]["status"], "PASS")
                self.assertEqual(
                    item["llvm_refinement"]["normalization"]["kind"],
                    "assumption-erasing-rustc-llvm-compatibility",
                )

    def test_schedule_is_derived_from_source_not_trusted_metadata(self):
        source = (FIXTURE / "src" / "lib.rs").read_text()
        function = extract_rust_function(source, "count_equal")
        # A minimal model is sufficient to exercise deterministic regeneration.
        from vladder.rust_semantics import RustKernelModel
        model = RustKernelModel(
            "ordered_reduction", "count_equal_u8", "bytes", "needle", "usize", "usize",
            "E1", "no panic", "wrapping-machine-usize", "iterator_fold", ("Eq", "Add"), True, 8,
        )
        candidate = generate_rust_candidates(function, model)[2]
        schedule = extract_candidate_schedule(candidate, model)
        self.assertEqual(schedule.lane_offsets, (0, 1, 2, 3))
        broken_source = candidate.source.replace("bytes[i + 3]", "bytes[i + 2]")
        broken = replace(candidate, source=broken_source)
        with self.assertRaisesRegex(ValueError, "every lane exactly once"):
            extract_candidate_schedule(broken, model)

    @unittest.skipUnless(shutil.which("cargo") and shutil.which("rustc"), "Rust toolchain unavailable")
    def test_audit_resolves_relative_paths_and_preserves_partial_local_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            report = audit_rust_regions(
                ROOT / "examples" / "rust_regions" / "audit.yaml",
                Path(directory),
            )
            self.assertEqual(report["supported_count"], 1)
            statuses = {item["id"]: item["status"] for item in report["regions"]}
            self.assertEqual(statuses["supported-count"], "supported")
            self.assertEqual(statuses["owning-boundary"], "local_graph_only")


if __name__ == "__main__":
    unittest.main()
