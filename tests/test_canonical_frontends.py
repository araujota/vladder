from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from vladder.canonical_regions import (
    CANONICAL_FAMILIES,
    CanonicalRegionError,
    classify_canonical_region,
    corroborate_compiler_shape,
)
from vladder.julia_adapter import JuliaRegionRequest, _extract_julia_function, inspect_julia_region, synthesize_julia_region
from vladder.language_adapter import SEMANTIC_NODE_KINDS
from vladder.rust_adapter import RustRegionRequest, inspect_rust_region, synthesize_rust_region
from vladder.rust_semantics import extract_rust_function
from vladder.zig_adapter import (
    ZigRegionRequest,
    _extract_zig_function,
    _specialize_zig_signature,
    inspect_zig_region,
    synthesize_zig_region,
)


ROOT = Path(__file__).resolve().parents[1]
RUST = ROOT / "examples" / "rust_regions" / "byte_count"
ZIG = ROOT / "examples" / "zig_regions" / "byte_count"
JULIA = ROOT / "examples" / "julia_regions" / "byte_count"
FAMILIES = {
    "pointwise": "pointwise_map",
    "guarded": "guarded_pointwise_map",
    "stencil": "stencil",
    "scan": "scan",
    "recurrence": "recurrence",
    "indirect": "indirect_memory",
}
NAMES = {
    "rust": {
        "pointwise": "pointwise", "guarded": "guarded", "stencil": "stencil",
        "scan": "prefix_scan", "recurrence": "recurrence", "indirect": "indirect",
    },
    "zig": {
        "pointwise": "pointwise", "guarded": "guarded", "stencil": "stencil",
        "scan": "prefixScan", "recurrence": "recurrence", "indirect": "indirect",
    },
    "julia": {
        "pointwise": "pointwise!", "guarded": "guarded!", "stencil": "stencil!",
        "scan": "prefix_scan!", "recurrence": "recurrence!", "indirect": "indirect!",
    },
}


class CanonicalClassifierTests(unittest.TestCase):
    def test_all_native_spellings_collapse_to_identical_canonical_regions(self):
        texts = {
            "rust": (RUST / "src" / "lib.rs").read_text(),
            "zig": (ZIG / "src" / "root.zig").read_text(),
            "julia": (JULIA / "src" / "VLadderJuliaFixture.jl").read_text(),
        }
        hashes: dict[str, set[str]] = {family: set() for family in FAMILIES}
        for language, names in NAMES.items():
            for key, name in names.items():
                if language == "rust":
                    function = extract_rust_function(texts[language], name)
                    source, signature = function.source, function.signature
                elif language == "zig":
                    source = _extract_zig_function(texts[language], name)
                    signature = source[:source.find("{")]
                else:
                    source = _extract_julia_function(texts[language], name)
                    signature = "Vector{Float32},Vector{Float32}"
                region = classify_canonical_region(language, source, signature)
                self.assertEqual(region.family, FAMILIES[key])
                self.assertIn(region.family, CANONICAL_FAMILIES)
                hashes[key].add(region.region_hash)
        self.assertTrue(all(len(values) == 1 for values in hashes.values()), hashes)

        rust_count = extract_rust_function(texts["rust"], "count_equal")
        zig_count = _extract_zig_function(texts["zig"], "countEqual")
        julia_count = _extract_julia_function(texts["julia"], "count_equal")
        count_hashes = {
            classify_canonical_region("rust", rust_count.source, rust_count.signature).region_hash,
            classify_canonical_region("zig", zig_count, zig_count[:zig_count.find("{")]).region_hash,
            classify_canonical_region("julia", julia_count, "Vector{UInt8},UInt8").region_hash,
        }
        self.assertEqual(len(count_hashes), 1, count_hashes)

    def test_multiple_loops_and_missing_compiler_shape_fail_closed(self):
        source = "pub fn f(dst: &mut [f32], src: &[f32]) { for i in 0..src.len() { dst[i]=src[i]; } for i in 0..src.len() { dst[i]=src[i]; } }"
        with self.assertRaises(CanonicalRegionError) as raised:
            classify_canonical_region("rust", source, "pub fn f(dst: &mut [f32], src: &[f32])")
        self.assertEqual(raised.exception.kind, "loop-shape")
        single = source.replace(" for i in 0..src.len() { dst[i]=src[i]; } }", " }")
        region = classify_canonical_region("rust", single, "pub fn f(dst: &mut [f32], src: &[f32])")
        evidence = corroborate_compiler_shape(region, ("define void @f() { ret void }",))
        self.assertEqual(evidence["status"], "fail")
        self.assertIn("memory", evidence["missing_signals"])

    def test_family_match_does_not_erase_expression_semantics(self):
        square = "pub fn f(dst: &mut [f32], src: &[f32]) { for i in 0..src.len() { dst[i] = src[i] * src[i] + 0.25; } }"
        affine = "pub fn f(dst: &mut [f32], src: &[f32]) { for i in 0..src.len() { dst[i] = src[i] * 2.0 + 0.25; } }"
        signature = "pub fn f(dst: &mut [f32], src: &[f32])"
        first = classify_canonical_region("rust", square, signature)
        second = classify_canonical_region("rust", affine, signature)
        self.assertEqual(first.family, second.family)
        self.assertNotEqual(first.region_hash, second.region_hash)
        self.assertNotEqual(first.semantic_parameters, second.semantic_parameters)

    def test_zig_comptime_specialization_closes_shared_byte_reduction(self):
        source = """pub fn countScalar(comptime T: type, list: []const T, element: T) usize {
            var found: usize = 0;
            for (list) |item| found += @intFromBool(item == element);
            return found;
        }"""
        generic = source[:source.find("{")]
        projected = _specialize_zig_signature(generic, "u8")
        self.assertNotIn("comptime T", projected)
        region = classify_canonical_region("zig", source, projected)
        self.assertEqual(region.operation, "count_equal_u8")


class CanonicalNativeCaptureTests(unittest.TestCase):
    def assert_supported(self, report: dict, family: str) -> None:
        self.assertEqual(report["status"], "supported", report["blockers"])
        graph = report["semantic_graph"]
        self.assertEqual(graph["contracts"]["canonical_region"]["family"], family)
        self.assertEqual(graph["contracts"]["compiler_corroboration"]["status"], "pass")
        self.assertTrue(all(node["kind"] in SEMANTIC_NODE_KINDS for node in graph["nodes"]))
        self.assertTrue(report["capabilities"]["semantic_capture"]["actual"])
        self.assertTrue(report["capabilities"]["information_flow"]["actual"] if "information_flow" in report["capabilities"] else report["capabilities"]["closure"]["actual"])
        self.assertFalse(report["capabilities"]["candidate_generation"]["actual"])

    @unittest.skipUnless(shutil.which("cargo") and shutil.which("rustc"), "Rust toolchain unavailable")
    def test_rust_compiler_corroborates_six_canonical_families(self):
        with tempfile.TemporaryDirectory() as directory:
            for key, family in FAMILIES.items():
                with self.subTest(family=family):
                    report = inspect_rust_region(RustRegionRequest(
                        RUST / "Cargo.toml", RUST / "src" / "lib.rs", NAMES["rust"][key],
                        Path(directory) / key,
                    ))
                    self.assert_supported(report, family)

    @unittest.skipUnless(shutil.which("zig"), "Zig toolchain unavailable")
    def test_zig_compiler_corroborates_six_canonical_families(self):
        with tempfile.TemporaryDirectory() as directory:
            for key, family in FAMILIES.items():
                with self.subTest(family=family):
                    report = inspect_zig_region(ZigRegionRequest(
                        ZIG / "src" / "root.zig", NAMES["zig"][key], Path(directory) / key,
                        build_root=ZIG,
                    ))
                    self.assert_supported(report, family)

    @unittest.skipUnless(shutil.which("julia"), "Julia toolchain unavailable")
    def test_julia_compiler_corroborates_six_canonical_families(self):
        with tempfile.TemporaryDirectory() as directory:
            for key, family in FAMILIES.items():
                with self.subTest(family=family):
                    report = inspect_julia_region(JuliaRegionRequest(
                        JULIA, JULIA / "src" / "VLadderJuliaFixture.jl", "VLadderJuliaFixture",
                        NAMES["julia"][key], "Vector{Float32},Vector{Float32}", Path(directory) / key,
                    ))
                    self.assert_supported(report, family)

    @unittest.skipUnless(
        shutil.which("cargo") and shutil.which("rustc") and shutil.which("zig") and shutil.which("julia"),
        "native language toolchains unavailable",
    )
    def test_semantic_capture_does_not_invoke_reduction_only_lowerers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust = synthesize_rust_region(RustRegionRequest(
                RUST / "Cargo.toml", RUST / "src" / "lib.rs", "pointwise", root / "rust",
            ))
            zig = synthesize_zig_region(ZigRegionRequest(
                ZIG / "src" / "root.zig", "pointwise", root / "zig", build_root=ZIG,
            ))
            julia = synthesize_julia_region(JuliaRegionRequest(
                JULIA, JULIA / "src" / "VLadderJuliaFixture.jl", "VLadderJuliaFixture",
                "pointwise!", "Vector{Float32},Vector{Float32}", root / "julia",
            ))
            for report in (rust, zig, julia):
                self.assertEqual(report["status"], "lowerer_required")
                self.assertEqual(report["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
