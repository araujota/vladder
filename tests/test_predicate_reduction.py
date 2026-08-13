from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from vladder.executable_search import ExecutableSearchEngine, ExecutableSearchRequest
from vladder.bit_reduction import (
    bit_reduction_realizations,
    detect_bit_reduction,
    enumerate_bit_reduction_candidates,
    prove_bit_reduction_candidate,
)
from vladder.deep_audit import extract_named_source_region
from vladder.predicate_reduction import (
    PREDICATE_REDUCTION_STYLES,
    PREDICATE_REDUCTION_UNROLLS,
    detect_predicate_reduction,
    enumerate_predicate_reduction_candidates,
    prove_predicate_reduction_candidate,
)


def test_detects_projected_bool_and_arrow_adjacent_change_reductions() -> None:
    bool_contract = detect_predicate_reduction(
        "fn count(&self) -> i64 { self.seen.iter().filter(|&&b| b).count() as i64 }"
    )
    assert bool_contract is not None
    assert bool_contract.operation == "count_true"
    assert bool_contract.source_binding == "projected-bool-field-view"

    adjacent_contract = detect_predicate_reduction("""
        fn count_distinct_sorted_indices(indices: &UInt32Array) -> usize {
            if indices.is_empty() { return 0; }
            let values = indices.values();
            let mut count = 1usize;
            let mut last = values[0];
            for &value in values.iter().skip(1) {
                if value != last { last = value; count += 1; }
            }
            count
        }
    """)
    assert adjacent_contract is not None
    assert adjacent_contract.operation == "count_adjacent_changes"
    assert adjacent_contract.element_type == "u32"
    assert adjacent_contract.source_binding == "arrow-primitive-values-view"


def test_every_predicate_parameter_combination_has_a_bound_proof() -> None:
    contract = detect_predicate_reduction(
        "fn count(data: &[u32]) -> usize { data.iter().filter(|&&value| value != 0).count() }"
    )
    assert contract is not None
    with tempfile.TemporaryDirectory() as directory:
        candidates = enumerate_predicate_reduction_candidates(contract, language="rust")
        assert {(item.style, item.unroll) for item in candidates} == {
            (style, unroll)
            for style in PREDICATE_REDUCTION_STYLES
            for unroll in PREDICATE_REDUCTION_UNROLLS
        }
        for candidate in candidates:
            proof = prove_predicate_reduction_candidate(
                candidate, Path(directory) / candidate.realization,
            )
            assert proof["status"] == "PASS"


def test_rust_wrapper_root_enumerates_compiles_and_deduplicates_in_parallel() -> None:
    if not shutil.which("rustc"):
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "stream.rs"
        source.write_text("""
        struct UInt32Array { values: Vec<u32> }
        impl UInt32Array {
            fn is_empty(&self) -> bool { self.values.is_empty() }
            fn values(&self) -> &[u32] { &self.values }
        }
        fn count_distinct_sorted_indices(indices: &UInt32Array) -> usize {
            if indices.is_empty() { return 0; }
            let values = indices.values();
            let mut count = 1usize;
            let mut last = values[0];
            for &value in values.iter().skip(1) {
                if value != last { last = value; count += 1; }
            }
            count
        }
        """)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "rust-adjacent", root / "out", source=source,
            function="count_distinct_sorted_indices", language="rust", family="auto",
            project_id="fixture", terminal_workers=8,
        ))
        assert result["status"] == "pass"
        evidence = result["family_evidence"]["predicate-reduction"]
        assert evidence["terminal_count"] == 8
        assert evidence["resolved_count"] == 8
        assert evidence["proof_status_counts"] == {"PASS": 8}
        assert evidence["compile_status_counts"] == {"PASS": 8}
        assert evidence["distinct_assembly_count"] >= 2
        assert result["closure"]["external_boundaries"] == ["owning wrapper projection"]


def test_qualified_rust_method_binds_retained_u64_bitmap_to_shared_popcount_grammar() -> None:
    source = """
    struct Bitmap65536DistinctCountAccumulator { bitmap: Box<[u64; 1024]> }
    impl Bitmap65536DistinctCountAccumulator {
        fn count(&self) -> i64 {
            self.bitmap.iter().map(|w| w.count_ones() as i64).sum()
        }
    }
    struct Other { values: [bool; 4] }
    impl Other { fn count(&self) -> usize { self.values.iter().filter(|&&b| b).count() } }
    """
    selected = extract_named_source_region(
        source, "Bitmap65536DistinctCountAccumulator::count", "rust",
    )
    contract = detect_bit_reduction(
        selected,
        source_context=source,
        function="Bitmap65536DistinctCountAccumulator::count",
    )
    assert contract is not None
    assert contract.element_bits == 64
    assert contract.source_binding == "projected-word-field-view"
    assert bit_reduction_realizations(contract) == (
        "scalar-element", "element-unroll2", "element-unroll4", "element-unroll8",
    )
    try:
        extract_named_source_region(source, "count", "rust")
    except ValueError as error:
        assert "multiple Rust definitions" in str(error)
    else:
        raise AssertionError("unqualified overloaded Rust method selection must fail closed")


def test_fallback_cpp_extraction_ignores_comments_and_literals_with_braces() -> None:
    source = r'''
    #include <cstddef>
    std::size_t target(const unsigned char* data, std::size_t n) noexcept {
        // An unmatched { in a comment is not C++ structure.
        const char* text = "} unrelated() {";
        const char* raw = R"tag({ still not structure })tag";
        std::size_t result = 0;
        for (std::size_t i = 0; i < n; ++i) result += data[i] != 0;
        return result;
    }
    std::size_t unrelated() noexcept { return 17; }
    '''
    selected = extract_named_source_region(source, "target", "cpp")
    assert "for (std::size_t i" in selected
    assert "unrelated() noexcept" not in selected


def test_zig_and_julia_bind_and_execute_the_shared_bit_reduction_grammar() -> None:
    fixtures = {
        "zig": """
            fn count(data: []const u64) usize {
                var total: usize = 0;
                for (data) |value| total += @popCount(value);
                return total;
            }
        """,
        "julia": """
            function count(data::Vector{UInt64})::Int
                total = 0
                for value in data
                    total += count_ones(value)
                end
                return total
            end
        """,
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for language, source_text in fixtures.items():
            if not shutil.which(language):
                continue
            contract = detect_bit_reduction(source_text)
            assert contract is not None
            assert contract.element_bits == 64
            candidates = enumerate_bit_reduction_candidates(contract, language=language)
            assert len(candidates) == 4
            for candidate in candidates:
                assert prove_bit_reduction_candidate(
                    candidate, root / language / candidate.realization,
                )["status"] == "PASS"
            source = root / ("count.zig" if language == "zig" else "count.jl")
            source.write_text(source_text)
            result = ExecutableSearchEngine(root / f"cache-{language}").search(
                ExecutableSearchRequest(
                    f"bit-{language}", root / f"out-{language}", source=source,
                    function="count", language=language, family="bit-popcount-reduction",
                    project_id="fixture", terminal_workers=4,
                )
            )
            assert result["status"] == "pass"
            assert len(result["terminals"]) == 4
            assert all(item["proof_status"] == "PASS" for item in result["terminals"])
            assert all(item["compile_status"] == "PASS" for item in result["terminals"])
