from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import tempfile

import pytest

from vladder.lazy_search import (
    ConservativePolicy,
    ExpansionDecision,
    FiniteParameterGrammar,
    JsonLineExpansionPolicy,
    LazySearchEngine,
    PolicyDecision,
)
from vladder.deep_grammar import load_deep_grammar
from vladder.bit_reduction import (
    BitReductionContract,
    detect_bit_reduction,
    enumerate_bit_reduction_candidates,
    prove_bit_reduction_candidate,
)
from vladder.dataflow_inference import infer_bounded_dataflow_contracts
from vladder.executable_search import (
    DeepLazyGrammar,
    ExecutableSearchEngine,
    ExecutableSearchRequest,
    load_executable_search_manifest,
    run_executable_search_manifest,
)
from vladder.toolchain import discover_toolchain
from vladder.search_training import build_search_training_bundle
from vladder.selected_build_search import (
    SelectedBuildCppGrammar,
    _compose_candidate_source,
    _selected_identity_symbol,
    prepare_selected_build_candidates,
)
from vladder.training_workflow import create_training_bundle_from_search_trace
from vladder.frontier_training import reconstruct_search_decisions
from vladder.model_training_data import graph_learning_examples
from vladder.ordered_prefix import (
    OrderedReductionContract,
    detect_ordered_reduction,
    enumerate_ordered_candidates,
    prove_ordered_candidate,
)


def test_lazy_parameter_search_does_not_materialize_before_policy() -> None:
    grammar = FiniteParameterGrammar("schedule", {"factor": (1, 2, 4), "banks": (1, 2, 4)})
    calls = []

    def callback(state, depth, context):
        calls.append((depth, dict(state.semantic_state.get("parameters", {}))))
        if state.semantic_state.get("parameters", {}).get("factor") == 4:
            return PolicyDecision(ExpansionDecision.PRUNE, 1.0, "test prune", True)
        return PolicyDecision(ExpansionDecision.EXPAND, 1.0, "test expand", True)

    policy = ConservativePolicy(callback, exploration_slots=0)
    result = LazySearchEngine().run(
        grammar,
        {"semantic_hash": "root"},
        policy=policy,
        mode="live",
    )
    assert result.complete is False
    assert result.policy_pruned == 1
    assert len(result.terminals) == 6
    assert all(item.semantic_state["parameters"]["factor"] != 4 for item in result.terminals)
    assert len(calls) < 1 + 3 + 9


def test_selected_build_prewarm_failure_is_diagnostic_not_authoritative(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    report = {
        "source": str(tmp_path / "source.cpp"),
        "closure": {
            "candidates": [{
                "id": "region-000-unroll-2",
                "region_id": "region-000",
                "schedule_choice": "unroll-2",
                "schedule_family": "loop-unroll",
                "source_sha256": "candidate",
            }],
        },
    }
    (tmp_path / "source.cpp").write_text("void transform() {}\n")
    calls = 0

    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise ValueError("capsule is not independently compilable")

    monkeypatch.setattr("vladder.selected_build_search.materialize_cpp_schedule_candidate", fail)
    result = prepare_selected_build_candidates(report, tmp_path)
    assert result["status"] == "partial"
    assert result["prepared"] == []
    assert result["failures"] == [{
        "region": "region-000",
        "choice": "unroll-2",
        "error": "capsule is not independently compilable",
    }]
    repeated = prepare_selected_build_candidates(report, tmp_path)
    assert repeated["failures"] == result["failures"]
    assert calls == 1


def test_lazy_policy_observes_partial_state_graph_without_terminal_evidence() -> None:
    grammar = FiniteParameterGrammar("schedule", {"factor": (1, 2), "banks": (1, 2)})
    contexts = []

    def callback(state, depth, context):
        decision = context["decision_context"]
        contexts.append(decision)
        assert decision["context_version"] == "pre-decision-state-v2"
        if state.action.get("parameter") == "factor":
            assert decision["semantic_delta"].get("factor") == state.action.get("value")
        assert "proof_status" not in json.dumps(decision)
        assert "assembly_identity" not in json.dumps(decision)
        return PolicyDecision(ExpansionDecision.EXPAND, 1.0, "capture", True)

    root_graph = {
        "nodes": [{"id": "input", "kind": "Input", "operation": "input", "output_type": "i32"}],
        "edges": [], "obligations": [], "effects": [], "protocols": [], "claims": [],
    }
    result = LazySearchEngine().run(
        grammar,
        {"semantic_hash": "root", "semantic_graph": root_graph},
        policy=ConservativePolicy(callback, exploration_slots=0),
        mode="live",
    )
    assert result.complete is True
    assert contexts
    assert all(context["graph"]["nodes"][-1]["source_provenance"]["language"] == "language-neutral" for context in contexts)


def test_exhaustive_lazy_search_is_deterministic_and_complete() -> None:
    grammar = FiniteParameterGrammar("schedule", {"factor": (1, 2, 4), "banks": (1, 2)})
    first = LazySearchEngine().run(grammar, {"semantic_hash": "root"})
    second = LazySearchEngine().run(grammar, {"semantic_hash": "root"})
    assert first.complete is True
    assert len(first.terminals) == 6
    assert first.to_dict() == second.to_dict()


def test_node_budget_reconciles_parent_child_counts_to_emitted_lineage() -> None:
    grammar = FiniteParameterGrammar(
        "schedule",
        {"first": tuple(range(8)), "second": tuple(range(8)), "third": tuple(range(8))},
    )
    result = LazySearchEngine().run(grammar, {"semantic_hash": "root"}, node_budget=25)
    assert result.complete is False
    actual_children: dict[str, int] = {}
    for node in result.nodes:
        if node.parent_id is not None:
            actual_children[node.parent_id] = actual_children.get(node.parent_id, 0) + 1
    assert all(
        node.child_count == actual_children.get(node.node_id, 0)
        for node in result.nodes
        if node.disposition == "expanded"
    )


def test_conservative_policy_fails_open_for_ood_and_low_confidence_prunes() -> None:
    grammar = FiniteParameterGrammar("schedule", {"factor": (1, 2), "banks": (1, 2)})

    def callback(state, depth, context):
        return PolicyDecision(ExpansionDecision.PRUNE, 0.5, "uncertain", False)

    result = LazySearchEngine().run(
        grammar,
        {"semantic_hash": "root"},
        policy=ConservativePolicy(callback, exploration_slots=0),
        mode="live",
    )
    assert result.complete is True
    assert result.policy_pruned == 0
    assert len(result.terminals) == 4
    assert any("fail-open" in item.decision_reason for item in result.nodes)


def test_policy_can_prune_a_terminal_before_candidate_evaluation() -> None:
    grammar = FiniteParameterGrammar("schedule", {"factor": (1, 2, 4)})

    def callback(state, depth, context):
        factor = state.semantic_state.get("parameters", {}).get("factor")
        if state.terminal and factor == 4:
            return PolicyDecision(ExpansionDecision.PRUNE, 1.0, "terminal rejected", True)
        return PolicyDecision(ExpansionDecision.EXPAND, 1.0, "keep", True)

    result = LazySearchEngine().run(
        grammar,
        {"semantic_hash": "root"},
        policy=ConservativePolicy(callback, exploration_slots=0),
        mode="live",
    )
    assert result.complete is False
    assert result.policy_pruned == 1
    assert [item.semantic_state["parameters"]["factor"] for item in result.terminals] == [1, 2]
    rejected = [item for item in result.nodes if item.disposition == "policy_pruned"]
    assert len(rejected) == 1
    assert rejected[0].terminal is True


def test_policy_receives_complete_ancestor_action_path() -> None:
    seen: list[list[dict[str, object]]] = []

    class RecordingPolicy:
        def decide(self, state, *, depth, root_context):
            seen.append(list(root_context["ancestor_action_path"]))
            return PolicyDecision(ExpansionDecision.EXPAND, 1.0, "record", True)

    result = LazySearchEngine().run(
        FiniteParameterGrammar("schedule", {"unroll": (1, 2), "width": (1, 4)}),
        {"semantic_hash": "root"},
        policy=RecordingPolicy(),
    )

    assert result.complete
    assert [len(path) for path in seen] == [1, 2, 2, 3, 3, 3, 3]
    assert all(path[-1]["family"] == "schedule" for path in seen)


def test_persistent_json_line_oracle_prunes_before_terminal_materialization() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        server = root / "oracle.py"
        server.write_text("""
import json
import sys
for line in sys.stdin:
    request = json.loads(line)
    if request["kind"] == "register_root":
        print(json.dumps({"status": "ready"}), flush=True)
        continue
    parameters = request["state"]["semantic_state"].get("parameters", {})
    if parameters.get("factor") == 4:
        response = {"decision": "PRUNE_HIGH_CONFIDENCE", "confidence": 1.0, "in_distribution": True}
    else:
        response = {"decision": "KEEP", "confidence": 1.0, "in_distribution": True}
    print(json.dumps(response), flush=True)
""")
        oracle = JsonLineExpansionPolicy(("python3", str(server)), timeout_seconds=5)
        try:
            policy = ConservativePolicy(
                lambda state, depth, context: oracle.decide(
                    state, depth=depth, root_context=context,
                ),
                exploration_slots=0,
            )
            result = LazySearchEngine().run(
                FiniteParameterGrammar(
                    "schedule", {"factor": (1, 2, 4), "banks": (1, 2, 4)},
                ),
                {"semantic_hash": "root", "semantic_graph": {"nodes": [], "edges": []}},
                policy=policy,
                mode="live",
            )
        finally:
            oracle.close()
        assert result.complete is False
        assert result.policy_pruned == 1
        assert len(result.terminals) == 6
        assert all(item.semantic_state["parameters"]["factor"] != 4 for item in result.terminals)


def test_deep_lazy_search_emits_candidates_without_stopping_descendant_expansion() -> None:
    grammar = load_deep_grammar()
    result = LazySearchEngine().run(
        DeepLazyGrammar(grammar, "scalar"),
        {"semantic_hash": "deep-root"},
    )
    assert result.complete is True
    assert {item.semantic_state["realization"] for item in result.terminals} == set(grammar.terminals)
    assert any(item.action.get("op") == "emit" for item in result.terminals)
    lazy_grammar = DeepLazyGrammar(grammar, "scalar")
    first = lazy_grammar._grammar_state("word-lanes", ("a",), {"rule": "a"})
    second = lazy_grammar._grammar_state("word-lanes", ("b",), {"rule": "b"})
    assert first.identity == second.identity


def test_ordered_prefix_detection_enumeration_and_proof() -> None:
    source = """
    size_t prefix(const uint8_t *data, size_t n, uint8_t needle) {
        size_t i = 0;
        while (i < n && data[i] == needle) ++i;
        return i;
    }
    """
    contract = detect_ordered_reduction(source)
    assert contract == OrderedReductionContract("prefix", "equal-u8", source_binding="raw-borrowed")
    candidates = enumerate_ordered_candidates(contract, language="cpp")
    assert [item.factor for item in candidates] == [1, 2, 4, 8]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for candidate in candidates:
            proof = prove_ordered_candidate(candidate, root / str(candidate.factor))
            assert proof["status"] == "PASS"


def test_ordered_pair_prefix_and_suffix_detection() -> None:
    prefix = """
    static size_t common_prefix_len(const std::string &left, const std::string &right) {
        size_t prefix_len = 0;
        size_t min_len = std::min(left.length(), right.length());
        while (prefix_len < min_len && left[prefix_len] == right[prefix_len]) {
            prefix_len++;
        }
        return prefix_len;
    }
    """
    suffix = """
    static size_t common_suffix_len(const std::string &left, const std::string &right) {
        size_t suffix_len = 0;
        size_t min_len = std::min(left.length(), right.length());
        while (suffix_len < min_len &&
               left[left.length() - 1 - suffix_len] == right[right.length() - 1 - suffix_len]) {
            suffix_len++;
        }
        return suffix_len;
    }
    """
    assert detect_ordered_reduction(prefix) == OrderedReductionContract(
        "prefix", "equal-elements", operand_mode="pair",
    )
    assert detect_ordered_reduction(suffix) == OrderedReductionContract(
        "suffix", "equal-elements", operand_mode="pair",
    )


def test_ordered_pair_candidates_compile_across_available_languages() -> None:
    contract = OrderedReductionContract("prefix", "equal-elements", operand_mode="pair")
    tools = {
        "cpp": shutil.which("clang++-20") or shutil.which("clang++"),
        "rust": shutil.which("rustc"),
        "zig": shutil.which("zig"),
        "julia": shutil.which("julia"),
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        engine = ExecutableSearchEngine(root / "cache")
        extensions = {"cpp": "cpp", "rust": "rs", "zig": "zig", "julia": "jl"}
        snippets = {
            "cpp": """size_t pair(const uint8_t *left, size_t left_n, const uint8_t *right, size_t right_n) { size_t i = 0; size_t n = left_n < right_n ? left_n : right_n; while (i < n && left[i] == right[i]) ++i; return i; }""",
            "rust": """fn pair(left: &[u8], right: &[u8]) -> usize { left.iter().zip(right.iter()).take_while(|(a, b)| a == b).count() }""",
            "zig": """fn pair(left: []const u8, right: []const u8) usize { var i: usize = 0; const n = @min(left.len, right.len); while (i < n and left[i] == right[i]) : (i += 1) {} return i; }""",
            "julia": """function pair(left::Vector{UInt8}, right::Vector{UInt8})::Int; i = 0; n = min(length(left), length(right)); while i < n && left[i + 1] == right[i + 1]; i += 1; end; return i; end""",
        }
        for language, available in tools.items():
            if not available:
                continue
            source = root / f"pair.{extensions[language]}"
            source.write_text(snippets[language])
            result = engine.search(ExecutableSearchRequest(
                f"pair-{language}", root / f"out-{language}", source=source,
                function="pair", language=language, family="ordered-prefix-suffix",
                project_id="fixture",
            ))
            assert result["status"] == "pass", result
            assert len(result["terminals"]) == 4
            assert all(item["proof_status"] == "PASS" for item in result["terminals"])
            assert all(item["compile_status"] == "PASS" for item in result["terminals"])


def test_cpp_compiler_source_range_prevents_cross_function_grammar_leakage() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "selection.cpp"
        source.write_text("""
        #include <cstddef>
        #include <cstdint>
        std::size_t common_prefix(const std::uint8_t* left, std::size_t left_n,
                                  const std::uint8_t* right, std::size_t right_n) noexcept {
            // An unmatched lexical brace { must not extend Clang's function range.
            std::size_t i = 0;
            const std::size_t n = left_n < right_n ? left_n : right_n;
            while (i < n && left[i] == right[i]) ++i;
            return i;
        }
        std::uint64_t serialize_unrelated(std::uint16_t a, std::uint16_t b, std::uint32_t c) noexcept {
            return std::uint64_t(a) | (std::uint64_t(b) << 16) | (std::uint64_t(c) << 32);
        }
        """)
        database = _write_cpp_compile_database(root, source)
        request = ExecutableSearchRequest(
            "compiler-range", root / "out", source=source, function="common_prefix",
            language="cpp", family="auto", project_id="fixture",
            compile_commands=database,
        )
        captured = ExecutableSearchEngine(root / "cache").capture(request)
        by_family = {item.family: item for item in captured.family_alternatives}
        ordered = by_family["ordered-prefix-suffix"]
        assert ordered.contract["operand_mode"] == "pair"
        codec = next(
            item for item in captured.family_alternatives
            if item.family == "bounded-variable-output-dataflow"
            and "fixed-width-codec source archetype absent" in item.unresolved_contracts
        )
        assert codec.blocked_authority == "sound_contract"


def test_ordered_candidates_compile_when_clang_is_available() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    contract = OrderedReductionContract("suffix", "nonzero-u8")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for candidate in enumerate_ordered_candidates(contract, language="cpp"):
            source = root / f"candidate-{candidate.factor}.cpp"
            assembly = root / f"candidate-{candidate.factor}.s"
            source.write_text(candidate.source)
            result = subprocess.run(
                [compiler, "-std=c++20", "-O3", "-march=native", "-S", str(source), "-o", str(assembly)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert result.returncode == 0, result.stderr
            assert assembly.exists()


def test_rust_bit_popcount_reduction_is_detected_enumerated_proved_and_compiled() -> None:
    if not shutil.which("rustc"):
        return
    source_text = """
fn binary_count_ones(opt: Option<&[u8]>) -> Option<i64> {
    opt.map(|value| value.iter().map(|b| b.count_ones() as i64).sum())
}
"""
    contract = detect_bit_reduction(source_text)
    assert contract == BitReductionContract()
    candidates = enumerate_bit_reduction_candidates(contract, language="rust")
    assert [item.realization for item in candidates] == [
        "scalar-byte", "word-u64", "word-u64-unroll2",
    ]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "bitmap.rs"
        source.write_text(source_text)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "bit-popcount", root / "out", source=source,
            function="binary_count_ones", language="rust", project_id="fixture",
        ))
        assert result["status"] == "pass"
        assert result["root"]["family"] == "source-family-dispatch"
        assert any(
            item["family"] == "bit-popcount-reduction" and item["stage"] == "grammar_family"
            for item in result["lazy_search"]["nodes"]
        )
        assert len(result["terminals"]) == 3
        assert all(item["proof_status"] == "PASS" for item in result["terminals"])
        assert all(item["compile_status"] == "PASS" for item in result["terminals"])
        for candidate in candidates:
            assert prove_bit_reduction_candidate(candidate, root / candidate.realization)["status"] == "PASS"


def test_live_policy_prunes_source_family_before_candidate_realization() -> None:
    source_text = """
fn binary_count_ones(opt: Option<&[u8]>) -> Option<i64> {
    opt.map(|value| value.iter().map(|b| b.count_ones() as i64).sum())
}
"""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "bitmap.rs"
        source.write_text(source_text)
        seen = []

        def callback(state, depth, context):
            seen.append((state.family, state.stage, depth, tuple(context["ancestor_action_path"])))
            return PolicyDecision(
                ExpansionDecision.PRUNE if state.family == "bit-popcount-reduction" else ExpansionDecision.EXPAND,
                1.0,
                "fixture family decision",
                True,
            )

        result = ExecutableSearchEngine(root / "cache").search(
            ExecutableSearchRequest(
                "bit-popcount-live", root / "out", source=source,
                function="binary_count_ones", language="rust", project_id="fixture",
            ),
            policy=ConservativePolicy(callback, exploration_slots=0),
            shadow_exhaustive=False,
        )
        assert any(
            family == "bit-popcount-reduction" and stage == "grammar_family" and depth == 0
            for family, stage, depth, _ in seen
        )
        assert result["lazy_search"]["policy_pruned"] == 1
        assert result["terminals"] == []
        assert not (root / "out" / "terminals").exists()


def test_selected_build_capture_does_not_materialize_schedule_candidates_before_policy() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "loop.cpp"
        source.write_text("""
        #include <cstddef>
        void transform(float* dst, const float* src, std::size_t n) noexcept {
            for (std::size_t i = 0; i < n; ++i) dst[i] = src[i] + 1.0f;
        }
        """)
        database = _write_cpp_compile_database(root, source)

        def callback(state, depth, context):
            return PolicyDecision(ExpansionDecision.PRUNE, 1.0, "fixture family prune", True)

        result = ExecutableSearchEngine(root / "cache").search(
            ExecutableSearchRequest(
                "selected-build-live", root / "out", source=source, function="transform",
                language="cpp", family="auto", project_id="fixture", compile_commands=database,
            ),
            policy=ConservativePolicy(callback, exploration_slots=0),
            shadow_exhaustive=False,
        )
        selected = next(
            item for item in result["lazy_search"]["nodes"]
            if item["family"] == "selected-build-cpp"
        )
        assert selected["disposition"] == "policy_pruned"
        capture = json.loads((root / "out" / "selected-build-capture" / "cpp-support.json").read_text())
        assert capture["closure"].get("candidates", []) == []
        assert not (root / "out" / "selected-build-capture" / "closure").exists()
        assert not (root / "out" / "regional-candidates").exists()
        assert result["terminals"] == []


def test_selected_build_identity_uses_the_concrete_llvm_alias_target() -> None:
    report = {
        "selection": {"symbol": "_ZN4ItemC1Ei"},
        "production_ir": {
            "resolved_symbols": {"production": "_ZN4ItemC2Ei"},
            "alias_chains": {"production": ["_ZN4ItemC1Ei", "_ZN4ItemC2Ei"]},
        },
    }
    assert _selected_identity_symbol(report) == "_ZN4ItemC2Ei"


def test_unified_search_emits_complete_v3_lineage_for_ordered_prefix() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "prefix.cpp"
        source.write_text("""
        #include <cstddef>
        #include <cstdint>
        std::size_t prefix(const std::uint8_t* data, std::size_t n, std::uint8_t needle) noexcept {
            std::size_t i = 0;
            while (i < n && data[i] == needle) ++i;
            return i;
        }
        """)
        request = ExecutableSearchRequest(
            "prefix-fixture", root / "out", source=source, function="prefix", language="cpp",
            family="ordered-prefix-suffix", project_id="fixture",
        )
        result = ExecutableSearchEngine(root / "cache").search(request)
        assert result["status"] == "pass"
        assert result["closure"]["source_executable"] is True
        assert result["closure"]["proof_unit_executable"] is True
        assert result["closure"]["replacement_ready"] is False
        assert result["closure"]["closure_scope"] == "proof_unit_only"
        assert result["closure"]["exhaustive_within_domain"] is True
        assert len(result["terminals"]) == 4
        assert {item["physical_outcome"] for item in result["terminals"]} >= {"compiler_identical", "distinct_realization"}
        trace = result["trace"]
        assert trace["frontier_decisions"]
        assert trace["transposition_evidence"]["canonical_state_hashes_available"] is True
        assert trace["best_first_evidence"]["authority"] == "priority-only in fast/guided/exhaustive modes"
        bundle = build_search_training_bundle(
            trace["roots"], trace["searches"], trace["branches"], trace["observations"],
            project_identity="fixture", producer_agent="test", producer_model="test",
            producer_provider=None, submission_consent=False,
            identity_path=root / "identity.json", grammar_version=trace["grammar_version"],
        )
        labels = {item["survival"]["class"] for item in bundle["branches"] if not item["baseline"]}
        assert "KEEP" in labels
        assert "PRUNE_HIGH_CONFIDENCE" in labels
        validated = create_training_bundle_from_search_trace(
            trace,
            root / "training-bundle.json",
            project_id="fixture",
            producer_agent="test",
            producer_model="test",
            identity_path=root / "workflow-identity.json",
        )
        assert validated["schema_version"] == "vladder-model-training-bundle-v3"
        decisions = reconstruct_search_decisions(graph_learning_examples(root / "training-bundle.json"))
        assert decisions
        assert all(item.canonical_state_hash is not None for item in decisions)
        assert all("rc24_missing_canonical_state_hash" not in item.evidence_limitations for item in decisions)


def test_unified_search_executes_deep_byte_reduction_from_source() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    if not shutil.which("alive-tv"):
        pytest.skip("strict LLVM refinement requires Alive2")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "count.cpp"
        source.write_text("""
        #include <cstddef>
        #include <cstdint>
        std::size_t count_equal(const std::uint8_t* data, std::size_t n, std::uint8_t needle) noexcept {
            std::size_t count = 0;
            for (std::size_t i = 0; i < n; ++i) count += data[i] == needle;
            return count;
        }
        """)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "deep-count", root / "out", source=source, function="count_equal", language="cpp",
            family="deep-information-realization", project_id="fixture",
        ))
        assert result["status"] == "pass"
        assert result["closure"]["source_executable"] is True
        assert result["closure"]["exhaustive_within_domain"] is True
        assert len(result["terminals"]) >= 4
        assert all(item["proof_status"] == "PASS" for item in result["terminals"])


def test_unified_search_executes_rust_ordered_suffix_from_source() -> None:
    if not shutil.which("rustc"):
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "ordered.rs"
        source.write_text("""
        fn trailing_bytes(bytes: &[u8], byte: u8) -> usize {
            bytes.iter().rev().take_while(|&&b| b == byte).count()
        }
        """)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "rust-suffix", root / "out", source=source, function="trailing_bytes", language="rust",
            family="ordered-prefix-suffix", project_id="fixture",
        ))
        assert result["status"] == "pass"
        assert result["closure"]["source_executable"] is True
        assert len(result["terminals"]) == 4
        assert all(item["compile_status"] == "PASS" for item in result["terminals"])


def test_manifest_runner_is_deterministic_and_emits_stage_coverage() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "prefix.cpp"
        source.write_text("""
        #include <cstddef>
        #include <cstdint>
        std::size_t prefix(const std::uint8_t* data, std::size_t n, std::uint8_t needle) noexcept {
            std::size_t i = 0;
            while (i < n && data[i] == needle) ++i;
            return i;
        }
        """)
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": "vladder-executable-search-manifest-v1",
            "mode": "shadow_exhaustive",
            "root_workers": 2,
            "terminal_workers": 3,
            "cache_directory": "cache",
            "roots": [{
                "id": "prefix",
                "source": "prefix.cpp",
                "function": "prefix",
                "language": "cpp",
                "family": "ordered-prefix-suffix",
                "project_id": "fixture",
            }],
        }))
        _, loaded_requests = load_executable_search_manifest(manifest, root / "out")
        assert loaded_requests[0].terminal_workers == 3
        report = run_executable_search_manifest(manifest, root / "out")
        assert report["root_count"] == 1
        assert report["terminal_workers"] == [3]
        assert report["complete_count"] == 1
        assert report["closure_coverage"]["source_executable_count"] == 1
        assert report["closure_coverage"]["proof_unit_executable_count"] == 1
        assert report["closure_coverage"]["replacement_ready_count"] == 0
        assert report["training_v3"]["status"] == "pass"
        assert report["training_v3"]["record_count"] == 1
        assert report["training_v3"]["status_counts"] == {"pass": 1}
        assert report["training_v3"]["records"][0]["request_fingerprint"]
        assert report["training_v3"]["records"][0]["search_decision_count"] > 0
        assert all(
            Path(path).is_file()
            for path in report["training_v3"]["records"][0]["search_decision_bundles"]
        )
        assert sum(report["training_v3"]["label_counts"].values()) > 0
        assert report["training_v3"]["label_counts"]["PRUNE_HIGH_CONFIDENCE"] >= 1
        bundle_path = Path(report["training_v3"]["records"][0]["bundle"])
        assert bundle_path.is_file()
        bundle = json.loads(bundle_path.read_text())
        factors = {
            parameter["value"]
            for branch in bundle["branches"]
            for parameter in branch["action"]["numeric_parameters"]
            if parameter["name"] == "factor"
        }
        assert factors == {1.0, 2.0, 4.0, 8.0}
        progress = json.loads((root / "out/training-v3/training-v3-progress.json").read_text())
        assert progress == report["training_v3"]
        trace = json.loads((root / "out/roots/prefix/executable-search-trace.json").read_text())
        assert trace["searches"][0]["grammar_version"] == "executable-grammar-registry-v2"
        grammar_actions = [
            branch["action"] for branch in trace["branches"] if branch["stage"] == "grammar_family"
        ]
        assert grammar_actions
        assert {tuple(action["primitives"]) for action in grammar_actions} == {("family_opportunity",)}
        assert (root / "out/executable-search-campaign.json").is_file()

        search_artifact = root / "out/roots/prefix/executable-search.json"
        first_search = json.loads(search_artifact.read_text())
        first_mtime = search_artifact.stat().st_mtime_ns
        resumed = run_executable_search_manifest(manifest, root / "out")
        assert resumed["training_v3"]["record_count"] == 1
        assert search_artifact.stat().st_mtime_ns == first_mtime
        assert json.loads(search_artifact.read_text())["request_fingerprint"] == first_search["request_fingerprint"]

        source.write_text(source.read_text() + "\n// source-fingerprint refresh\n")
        refreshed = run_executable_search_manifest(manifest, root / "out")
        assert refreshed["complete_count"] == 1
        assert search_artifact.stat().st_mtime_ns > first_mtime
        assert json.loads(search_artifact.read_text())["request_fingerprint"] != first_search["request_fingerprint"]


def test_manifest_decisive_retention_preserves_root_evidence_and_training_lineage() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "prefix.cpp"
        source.write_text("""
        #include <cstddef>
        #include <cstdint>
        std::size_t prefix(const std::uint8_t* data, std::size_t n) noexcept {
            std::size_t i = 0;
            while (i < n && data[i] != 0) ++i;
            return i;
        }
        """)
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": "vladder-executable-search-manifest-v1",
            "mode": "shadow_exhaustive",
            "artifact_retention": "decisive",
            "roots": [{
                "id": "prefix", "source": "prefix.cpp", "function": "prefix",
                "language": "cpp", "family": "ordered-prefix-suffix",
                "project_id": "fixture",
            }],
        }))

        report = run_executable_search_manifest(manifest, root / "out")

        assert report["artifact_retention"] == "decisive"
        root_output = root / "out/roots/prefix"
        assert not (root_output / "executable-search.json").exists()
        assert (root_output / "executable-search.json.gz").is_file()
        assert (root_output / "executable-search-trace.json.gz").is_file()
        assert (root_output / "executable-search-summary.json").is_file()
        assert (root_output / "executable-closure.json").is_file()
        assert not (root_output / "terminals").exists()
        record = report["training_v3"]["records"][0]
        assert record["artifact_compaction"]["policy"] == "decisive"
        assert Path(record["bundle"]).is_file()
        compressed_mtime = (root_output / "executable-search.json.gz").stat().st_mtime_ns
        resumed = run_executable_search_manifest(manifest, root / "out")
        assert resumed["complete_count"] == 1
        assert (root_output / "executable-search.json.gz").stat().st_mtime_ns == compressed_mtime


def test_ephemeral_terminal_artifacts_preserve_decisions_without_build_products() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "prefix.cpp"
        source.write_text("""
        #include <cstddef>
        #include <cstdint>
        std::size_t prefix(const std::uint8_t* data, std::size_t n) noexcept {
            std::size_t i = 0;
            while (i < n && data[i] != 0) ++i;
            return i;
        }
        """)
        result = ExecutableSearchEngine(root / "cache").search(
            ExecutableSearchRequest(
                "prefix", root / "out", source=source, function="prefix",
                language="cpp", family="ordered-prefix-suffix", project_id="fixture",
            ),
            ephemeral_terminal_artifacts=True,
        )

        assert result["status"] == "pass"
        assert result["terminals"]
        assert not (root / "out/terminals").exists() or not any(
            (root / "out/terminals").iterdir()
        )
        assert (root / "out/composition-native-search-trace.json").is_file()
        assert all("search_cost" in terminal for terminal in result["terminals"])


def test_budget_truncated_source_search_emits_schema_valid_uncertain_lineage() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "prefix.cpp"
        source.write_text("""
        #include <cstddef>
        #include <cstdint>
        std::size_t prefix(const std::uint8_t* data, std::size_t n, std::uint8_t needle) noexcept {
            std::size_t i = 0;
            while (i < n && data[i] == needle) ++i;
            return i;
        }
        """)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "budget-prefix", root / "out", source=source, function="prefix",
            language="cpp", family="ordered-prefix-suffix", project_id="fixture",
            node_budget=2,
        ))
        assert result["status"] == "incomplete"
        bundle = create_training_bundle_from_search_trace(
            result["trace"], root / "training.json", project_id="fixture",
            producer_agent="test", producer_model="test",
            identity_path=root / "identity.json",
        )
        assert bundle["branches"]
        assert any(
            branch["survival"]["class"] == "KEEP_UNCERTAIN"
            for branch in bundle["branches"] if not branch["baseline"]
        )


def _write_cpp_compile_database(root: Path, source: Path, *, duplicate: bool = False) -> Path:
    compiler = discover_toolchain().compiler
    entry = {
        "directory": str(root),
        "file": str(source),
        "arguments": [
            compiler, "-std=c++20", "-O3", "-c", str(source),
            "-o", str(root / "fixture.o"),
        ],
    }
    entries = [entry]
    if duplicate:
        entries.append({
            **entry,
            "arguments": [
                compiler, "-std=c++20", "-O2", "-DNDEBUG", "-c", str(source),
                "-o", str(root / "fixture-release.o"),
            ],
        })
    database = root / "compile_commands.json"
    database.write_text(json.dumps(entries, indent=2) + "\n")
    return database


def test_selected_build_cpp_lazily_composes_multiple_proved_regions() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "two_loops.cpp"
        source.write_text("""
        #include <cstddef>
        #include <span>
        void two_loops(std::span<float> dst, std::span<const float> src) noexcept {
            for (std::size_t i = 0; i < src.size(); ++i) {
                dst[i] = src[i] + 1.0f;
            }
            for (std::size_t i = 0; i < src.size(); ++i) {
                dst[i] *= 2.0f;
            }
        }
        """)
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "selected-build", root / "out", source=source, function="two_loops",
            language="cpp", family="auto", project_id="fixture",
            compile_commands=database, terminal_workers=4,
        ))
        assert result["status"] == "pass"
        assert result["root"]["family"] == "source-family-dispatch"
        # Aggregate dispatch closure stays conservative when a sibling family
        # (for example an LLVM candidate containing unsupported proof IR) is
        # unresolved.  The selected-build subtree itself is fully terminal.
        selected_terminals = [
            item for item in result["terminals"]
            if item["dispatch_family"] == "selected-build-cpp"
        ]
        assert result["closure"]["parameter_domains"]["selected-build-cpp.region-000"] == [
            "baseline", "interleave-2", "interleave-4", "unroll-2", "unroll-4",
            "vector-width-2", "vector-width-4", "vector-width-8",
        ]
        assert result["closure"]["parameter_domains"]["selected-build-cpp.region-001"] == [
            "baseline", "interleave-2", "interleave-4", "unroll-2", "unroll-4",
            "vector-width-2", "vector-width-4", "vector-width-8",
        ]
        assert len(selected_terminals) == 64
        assert result["family_evidence"]["selected-build-cpp"]["terminal_count"] == 64
        assert result["family_evidence"]["selected-build-cpp"]["resolved_count"] == 64
        assert all(item["proof_status"] == "PASS" for item in selected_terminals)
        assert all(item["compile_status"] == "PASS" for item in selected_terminals)
        assert all(item["replacement_ready"] for item in selected_terminals)
        assert all(item["source_reconstruction"]["scope"] == "complete_translation_unit" for item in selected_terminals)
        assert all(Path(item["artifacts"]["source"]).is_file() for item in selected_terminals)
        assert len(tuple((root / "out/terminals").glob("*/terminal-result.json"))) == 64
        assert any(
            branch["stage"] == "composition"
            for branch in result["trace"]["branches"]
        )
        assert {
            branch["action"].get("family") for branch in result["trace"]["branches"]
        } >= {"loop-unroll-schedule", "loop-vector-width", "loop-interleave-schedule"}
        bundle = create_training_bundle_from_search_trace(
            result["trace"], root / "training.json", project_id="fixture",
            producer_agent="test", producer_model="test",
            identity_path=root / "identity.json",
        )
        labels = {
            item["survival"]["class"]
            for item in bundle["branches"]
            if not item["baseline"]
        }
        assert "KEEP" in labels
        assert "PRUNE_HIGH_CONFIDENCE" in labels
        regional = [
            item for item in bundle["branches"]
            if item["decision_context"]["quality"] == "region_projected"
        ]
        assert regional
        assert all(item["decision_context"]["focus_node_indices"] for item in regional)
        assert any(
            node["kind"] == "Loop"
            for item in regional
            for node in item["decision_context"]["graph"]["nodes"]
        )


def test_selected_build_cartesian_domain_can_be_bounded_without_claiming_omitted_regions() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "two_loops.cpp"
        source.write_text("""
        #include <cstddef>
        void two_loops(float* dst, const float* src, std::size_t n) noexcept {
            for (std::size_t i = 0; i < n; ++i) dst[i] = src[i] + 1.0f;
            for (std::size_t i = 0; i < n; ++i) dst[i] *= 2.0f;
        }
        """)
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "bounded-selected-build", root / "out", source=source, function="two_loops",
            language="cpp", family="auto", project_id="fixture",
            compile_commands=database, contract={"max_selected_build_regions": 1},
            terminal_workers=2,
        ))
        assert result["status"] == "pass"
        selected_contract = next(
            item["contract"] for item in result["root"]["contract"]["family_contracts"]
            if item["dispatch_family"] == "selected-build-cpp"
        )
        assert selected_contract["selected_regions"] == ["region-000"]
        assert selected_contract["omitted_regions"] == ["region-001"]
        selected_terminals = [
            item for item in result["terminals"]
            if item["dispatch_family"] == "selected-build-cpp"
        ]
        assert len(selected_terminals) == 8
        assert all(item["replacement_ready"] for item in selected_terminals)


def test_selected_build_source_composition_uses_exact_insertion_spans() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        original = "void transform() {\n  first();\n  second();\n}\n"
        first_offset = original.index("first")
        second_offset = original.index("second")
        first_text = "#pragma clang loop unroll_count(2)\n"
        second_text = "#pragma clang loop vectorize_width(4)\n"
        first_source = root / "first.cpp"
        second_source = root / "second.cpp"
        first_source.write_text(original[:first_offset] + first_text + original[first_offset:])
        second_source.write_text(original[:second_offset] + second_text + original[second_offset:])

        composed = _compose_candidate_source(original, [
            {
                "id": "first",
                "repository_candidate_source": str(first_source),
                "placement": {"insert_before": first_offset},
            },
            {
                "id": "second",
                "repository_candidate_source": str(second_source),
                "placement": {"insert_before": second_offset},
            },
        ])

        assert composed == (
            original[:first_offset]
            + first_text
            + original[first_offset:second_offset]
            + second_text
            + original[second_offset:]
        )


def test_selected_build_cpp_inapplicability_is_a_sound_negative() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "identity.cpp"
        source.write_text("int identity(int value) noexcept { return value; }\n")
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "selected-build-negative", root / "out", source=source, function="identity",
            language="cpp", family="auto", project_id="fixture",
            compile_commands=database, terminal_workers=2,
        ))
        assert result["status"] == "pass"
        assert result["root"]["family"] == "source-family-dispatch"
        bundle = create_training_bundle_from_search_trace(
            result["trace"], root / "training.json", project_id="fixture",
            producer_agent="test", producer_model="test",
            identity_path=root / "identity.json",
        )
        family = next(
            item for item in bundle["branches"]
            if item["action"]["family"] == "selected-build-cpp"
        )
        assert family["survival"]["class"] == "BLOCKED_BY_CONTRACT"
        assert {tuple((item["name"], item["value"])) for item in family["action"]["categorical_parameters"]} >= {
            ("decision_surface", "deterministic")
        }


def test_selected_build_cpp_keeps_internal_symbol_identity_out_of_inlining() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "internal.cpp"
        source.write_text("""
        #include <cstddef>
        static std::size_t count_nonzero(const unsigned char* data, std::size_t n) noexcept {
            std::size_t count = 0;
            for (std::size_t i = 0; i < n; ++i) {
                count += data[i] != 0;
            }
            return count;
        }
        std::size_t use_count(const unsigned char* data, std::size_t n) noexcept {
            return count_nonzero(data, n);
        }
        """)
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "selected-build-internal", root / "out", source=source,
            function="count_nonzero", language="cpp", family="auto",
            project_id="fixture", compile_commands=database, terminal_workers=4,
        ))
        assert result["status"] == "pass"
        selected = [
            item for item in result["terminals"]
            if item["dispatch_family"] == "selected-build-cpp"
        ]
        assert len(selected) == 8
        assert all(
            item["compile"]["identity_mode"] == "no-inline-internal-symbol-identity"
            for item in selected
        )
        assert all(item["assembly_identity"] for item in selected)


def test_selected_build_compile_rejection_is_a_resolved_negative() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "nonvectorizable.cpp"
        source.write_text("""
        #include <cstddef>
        void transform(float* dst, const float* src, std::size_t n) noexcept {
            for (std::size_t i = 0; i < n; ++i) {
                if (src[i] < 0.0f) break;
                dst[i] = src[i] + 1.0f;
            }
        }
        """)
        database = _write_cpp_compile_database(root, source)
        entries = json.loads(database.read_text())
        entries[0]["arguments"].insert(3, "-Werror")
        database.write_text(json.dumps(entries, indent=2) + "\n")
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "compile-negative", root / "out", source=source,
            function="transform", language="cpp", family="auto",
            project_id="fixture", compile_commands=database,
        ))
        assert result["status"] == "pass"
        rejected = [item for item in result["terminals"] if item["compile_status"] == "FAIL"]
        assert rejected
        assert all(item["physical_outcome"] == "illegal" for item in rejected)
        assert all(item["resolved"] for item in rejected)
        assert result["closure"]["stages"]["compilation"]["status"] == "complete"


def test_selected_build_cpp_canonicalizes_duplicate_ast_regions() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        candidate_2 = root / "factor-2.cpp"
        candidate_4 = root / "factor-4.cpp"
        candidate_2.write_text("#pragma clang loop unroll_count(2)\nfor (;;) {}\n")
        candidate_4.write_text("#pragma clang loop unroll_count(4)\nfor (;;) {}\n")
        report = {"closure": {"candidates": []}}
        for region in ("region-000", "region-001"):
            report["closure"]["candidates"].extend((
                {
                    "id": f"{region}-unroll-2", "factor": 2,
                    "repository_candidate_source": str(candidate_2),
                },
                {
                    "id": f"{region}-unroll-4", "factor": 4,
                    "repository_candidate_source": str(candidate_4),
                },
            ))
        grammar = SelectedBuildCppGrammar(report)
        assert grammar.regions == ("region-000",)
        selected = SelectedBuildCppGrammar(report, ("region-001",))
        assert selected.regions == ("region-001",)
        with pytest.raises(ValueError, match="absent from compiler capture"):
            SelectedBuildCppGrammar(report, ("region-999",))


def test_manifest_can_expand_every_matching_cpp_build_configuration() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "identity.cpp"
        source.write_text("int identity(int value) noexcept { return value; }\n")
        database = _write_cpp_compile_database(root, source, duplicate=True)
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": "vladder-executable-search-manifest-v1",
            "oracle": {
                "command": ["python3", "oracle.py"],
                "timeout_seconds": 7,
                "prune_confidence": 0.9999,
                "exploration_modulus": 20,
                "exploration_slots": 2,
            },
            "roots": [{
                "id": "identity",
                "source": source.name,
                "function": "identity",
                "source_line": 1,
                "language": "cpp",
                "compile_commands": database.name,
                "compile_command_mode": "all",
            }],
        }))
        _, requests = load_executable_search_manifest(manifest, root / "out")
        assert [item.identifier for item in requests] == ["identity@cc-0", "identity@cc-1"]
        assert [item.command_index for item in requests] == [0, 1]
        assert [item.source_line for item in requests] == [1, 1]
        assert all(item.oracle_command == ("python3", "oracle.py") for item in requests)
        assert all(item.oracle_timeout_seconds == 7 for item in requests)
        assert all(item.oracle_prune_confidence == 0.9999 for item in requests)
        assert all(item.oracle_exploration_modulus == 20 for item in requests)
        assert all(item.oracle_exploration_slots == 2 for item in requests)


def test_contract_blocked_root_emits_blocked_v3_supervision() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "blocked", root / "out", language="cpp",
            family="bounded-variable-output-dataflow", project_id="fixture",
        ))
        assert result["status"] == "contract_blocked"
        bundle = build_search_training_bundle(
            result["trace"]["roots"], result["trace"]["searches"],
            result["trace"]["branches"], result["trace"]["observations"],
            project_identity="fixture", producer_agent="test", producer_model="test",
            producer_provider=None, submission_consent=False,
            identity_path=root / "identity.json", grammar_version=result["trace"]["grammar_version"],
        )
        family = next(item for item in bundle["branches"] if not item["baseline"])
        assert family["survival"]["class"] == "BLOCKED_BY_CONTRACT"


def test_recognition_incomplete_root_emits_schema_valid_uncertain_v3() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "unsupported.cpp"
        source.write_text("""
        #include <cstddef>
        void unsupported(unsigned long* out, const unsigned long* current,
                         const unsigned long* baseline, std::size_t n) {
            for (std::size_t i = 0; i < n; ++i) {
                if (current[i] != baseline[i]) out[i] = current[i];
            }
        }
        """)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "unrecognized", root / "out", source=source, function="unsupported",
            language="cpp", project_id="fixture",
        ))
        assert result["status"] == "pass"
        assert result["trace"]["searches"][0]["selection_policy"] == "bounded_exhaustive"
        bundle = create_training_bundle_from_search_trace(
            result["trace"], root / "training-bundle.json", project_id="fixture",
            producer_agent="test", producer_model="test", identity_path=root / "identity.json",
        )
        family = next(
            item for item in bundle["branches"]
            if item["action"]["family"] == "predicate-stable-compaction"
            and item["survival"]["class"] == "KEEP_UNCERTAIN"
        )
        assert family["survival"]["class"] == "KEEP_UNCERTAIN"
        siblings = [
            item for item in bundle["branches"]
            if item["stage"] == "grammar_family" and item["branch_id"] != family["branch_id"]
        ]
        assert siblings
        assert {item["survival"]["class"] for item in siblings} <= {
            "BLOCKED_BY_CONTRACT", "KEEP_UNCERTAIN",
        }
        assert "BLOCKED_BY_CONTRACT" in {item["survival"]["class"] for item in siblings}
        assert bundle["searches"][0]["grammar_version"] == "executable-grammar-registry-v2"


def test_source_infers_and_executes_bounded_compaction_contract() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    source_text = """
    #include <cstddef>
    #include <cstdint>
    std::size_t compact(
        std::uint32_t* __restrict out_indices,
        std::uint64_t* __restrict out_values,
        std::size_t out_capacity,
        const std::uint64_t* __restrict current,
        const std::uint64_t* __restrict baseline,
        std::size_t n) noexcept {
        if (n > 64 || out_capacity < n) return SIZE_MAX;
        std::size_t output_count = 0;
        for (std::size_t i = 0; i < n; ++i) {
            if (current[i] != baseline[i]) {
                out_indices[output_count] = static_cast<std::uint32_t>(i);
                out_values[output_count] = current[i];
                ++output_count;
            }
        }
        return output_count;
    }
    """
    inferred = infer_bounded_dataflow_contracts(source_text, "compact")
    assert len(inferred) == 1
    assert inferred[0].family == "predicate-stable-compaction"
    assert inferred[0].status == "complete"
    assert inferred[0].contract() is not None
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "compact.cpp"
        source.write_text(source_text)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "compact", root / "out", source=source, function="compact", language="cpp",
            family="auto", project_id="fixture",
        ))
        assert result["status"] == "pass"
        assert result["root"]["family"] == "source-family-dispatch"
        dataflow = [
            item for item in result["terminals"]
            if item["dispatch_family"] == "predicate-stable-compaction"
        ]
        assert len(dataflow) == 5
        assert all(item["proof_status"] == "PASS" for item in dataflow)
        assert all(item["compile_status"] == "PASS" for item in dataflow)


def test_compiler_closed_no_growth_vector_enters_runtime_sized_compaction_grammar() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "collect.cpp"
        source.write_text(
            (Path(__file__).resolve().parents[1] / "examples/cpp_regions/accepted_no_growth_vector.cpp").read_text()
        )
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "no-growth-vector",
            root / "out",
            source=source,
            function="collect_changed",
            language="cpp",
            family="predicate-stable-compaction",
            project_id="fixture",
            compile_commands=database,
            terminal_workers=4,
        ))
        assert result["status"] == "pass"
        assert result["root"]["contract"]["bounded_dataflow"]["max_elements"] is None
        assert result["root"]["contract"]["bounded_dataflow"]["element_bits"] == 32
        assert result["root"]["contract"]["bounded_dataflow"]["capacity_policy"] == "fail-input-extent-unchanged"
        assert result["root"]["contract"]["bounded_dataflow"]["aliasing"] == "runtime-guarded-disjoint"
        assert len(result["terminals"]) == 5
        assert all(item["compile_status"] == "PASS" for item in result["terminals"])
        assert all(item["proof_status"] == "PASS" for item in result["terminals"])
        assert result["closure"]["proof_unit_executable"] is True
        assert result["closure"]["replacement_ready"] is False


def test_exact_cpp_compaction_abi_reconstructs_complete_selected_definition() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "compact.cpp"
        source.write_text("""
        #include <cstddef>
        #include <cstdint>
        #include <limits>
        std::size_t compact(
            std::uint32_t* out_indices,
            std::uint32_t* out_values,
            std::size_t capacity,
            const std::uint32_t* current,
            const std::uint32_t* baseline,
            std::size_t n) noexcept {
            std::size_t selected = 0;
            for (std::size_t i = 0; i < n; ++i) selected += current[i] != baseline[i];
            if (selected > capacity) return std::numeric_limits<std::size_t>::max();
            std::size_t output = 0;
            for (std::size_t i = 0; i < n; ++i) {
                if (current[i] == baseline[i]) continue;
                out_indices[output] = static_cast<std::uint32_t>(i);
                out_values[output] = current[i];
                ++output;
            }
            return output;
        }
        """)
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "exact-cpp-compaction",
            root / "out",
            source=source,
            function="compact",
            language="cpp",
            family="predicate-stable-compaction",
            project_id="fixture",
            compile_commands=database,
            terminal_workers=4,
        ))
        assert result["status"] == "pass"
        assert len(result["terminals"]) == 5
        assert all(item["replacement_ready"] for item in result["terminals"])
        assert all(Path(item["artifacts"]["source_reconstruction"]).is_file() for item in result["terminals"])
        assert result["closure"]["proof_unit_executable"] is True
        assert result["closure"]["replacement_ready"] is True
        assert result["closure"]["closure_scope"] == "replacement_ready"
        bundle = create_training_bundle_from_search_trace(
            result["trace"],
            root / "training.json",
            project_id="fixture",
            producer_agent="test",
            producer_model="test",
            identity_path=root / "identity.json",
        )
        mask = next(
            item for item in bundle["branches"]
            if "root-to-mask-and-scatter" in item["action"]["primitives"]
        )
        mask_children = [
            item for item in bundle["branches"]
            if item["parent_branch_id"] == mask["branch_id"]
        ]
        assert len(mask_children) == 3
        assert mask["coverage"]["children_status"] == "exhaustive"
        assert mask["survival"]["class"] in {"KEEP", "PRUNE_HIGH_CONFIDENCE"}
        assert mask["descendant_utility"]["useful"] is not None


def test_exact_cpp_codec_abi_reconstructs_and_proves_complete_source() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "codec.cpp"
        source.write_text("""
        #include <cstdint>
        // vladder: field_widths=8,16,32
        // little endian fixed-width codec
        std::uint64_t encode(std::uint16_t field0, std::uint16_t field1,
                             std::uint32_t field2) noexcept {
            return (static_cast<std::uint64_t>(field0) & 0xffU)
                | ((static_cast<std::uint64_t>(field1) & 0xffffU) << 8U)
                | (static_cast<std::uint64_t>(field2) << 24U);
        }
        """)
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "exact-cpp-codec",
            root / "out",
            source=source,
            function="encode",
            language="cpp",
            family="fixed-width-codec",
            project_id="fixture",
            compile_commands=database,
            terminal_workers=3,
        ))
        assert result["status"] == "pass"
        assert len(result["terminals"]) == 3
        assert all(item["proof_status"] == "PASS" for item in result["terminals"])
        assert all(item["replacement_ready"] for item in result["terminals"])
        assert result["closure"]["replacement_ready"] is True


def test_selected_build_schedules_external_callback_without_claiming_local_capsule() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "callback.cpp"
        source.write_text("""
        #include <span>
        void visit_values(std::span<const int> values, void (*callback)(int)) {
            for (const int value : values) callback(value);
        }
        """)
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "callback", root / "out", source=source, function="visit_values",
            language="cpp", family="selected-build-cpp", project_id="fixture",
            compile_commands=database, terminal_workers=2,
        ))
        assert result["status"] == "pass"
        assert len(result["terminals"]) == 8
        assert all(item["proof_status"] == "PASS" for item in result["terminals"])
        assert all(item["compile_status"] == "PASS" for item in result["terminals"])
        report = json.loads((root / "out/selected-build-capture/cpp-support.json").read_text())
        assert report["status"] == "adapter_required"
        region = report["closure"]["regions"][0]
        assert region["eligible"] is False
        assert region["schedule_eligible"] is True
        assert region["disposition"] == "effect_preserving_schedule"


def test_llvm_function_family_enumerates_and_proves_complete_module_candidates() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    if not shutil.which("alive-tv"):
        pytest.skip("strict LLVM refinement requires Alive2")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "aggregate.cpp"
        source.write_text("""
        struct Pair { unsigned first; unsigned second; };
        Pair make_pair(unsigned value) noexcept {
            return Pair{value, value + 1U};
        }
        """)
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "aggregate", root / "out", source=source, function="make_pair",
            language="cpp", family="llvm-function-pipeline", project_id="fixture",
            compile_commands=database, terminal_workers=2,
        ))
        assert result["status"] == "pass"
        assert len(result["terminals"]) == 7
        assert all(item["compile_status"] == "PASS" for item in result["terminals"])
        assert all(item["proof_status"] == "PASS" for item in result["terminals"])
        assert all(Path(item["artifacts"]["llvm_ir"]).is_file() for item in result["terminals"])
        assert result["closure"]["stages"]["source_reconstruction"]["status"] == "partial"
        bundle = create_training_bundle_from_search_trace(
            result["trace"], root / "training.json", project_id="fixture",
            producer_agent="test", producer_model="test", identity_path=root / "identity.json",
        )
        assert bundle["schema_version"] == "vladder-model-training-bundle-v3"
        assert bundle["searches"][0]["coverage"] in {"complete", "partial"}


def test_explicit_family_with_unresolved_neighbor_does_not_claim_complete_training_utility() -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    if not shutil.which("alive-tv"):
        pytest.skip("strict LLVM refinement requires Alive2")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "owner.cpp"
        source.write_text("""
        #include <cstddef>
        #include <vector>
        struct Owner {
            std::vector<unsigned> values;
            std::size_t index(unsigned value) const noexcept;
        };
        std::size_t Owner::index(unsigned value) const noexcept {
            return values.empty() ? 0 : value % values.size();
        }
        """)
        database = _write_cpp_compile_database(root, source)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "owner-index", root / "out", source=source, function="Owner::index",
            language="cpp", family="llvm-function-pipeline", project_id="fixture",
            compile_commands=database, terminal_workers=2,
        ))
        assert result["status"] == "pass"
        assert all(item["proof_status"] in {"PASS", "FAIL"} for item in result["terminals"])
        bundle = create_training_bundle_from_search_trace(
            result["trace"], root / "training.json", project_id="fixture",
            producer_agent="test", producer_model="test", identity_path=root / "identity.json",
        )
        unresolved_neighbors = [
            item for item in bundle["branches"]
            if item["stage"] == "grammar_family"
            and item["action"]["family"] != "llvm-function-pipeline"
            and item["survival"]["class"] == "KEEP_UNCERTAIN"
        ]
        if unresolved_neighbors:
            assert bundle["searches"][0]["coverage"] == "partial"


def test_compiler_corroborated_canonical_source_enumerates_full_rule_tree() -> None:
    compiler = shutil.which("clang-20") or shutil.which("clang")
    if not compiler:
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "pointwise.c"
        source.write_text(
            "#include <stddef.h>\n"
            "void pointwise(float *dst,const float *src,size_t n){"
            "for(size_t i=0;i<n;++i)dst[i]=src[i]*src[i]+0.25f;}\n"
        )
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "pointwise", root / "out", source=source, function="pointwise",
            language="c", family="auto", project_id="fixture",
        ))
        terminals = [
            item for item in result["terminals"]
            if item["dispatch_family"] == "canonical-bounded-region"
        ]
        assert result["status"] == "pass"
        assert result["closure"]["source_executable"] is True
        assert {item["realization"] for item in terminals} == {
            "scalar", "unroll4", "unroll8", "avx2", "avx512",
        }
        assert all(item["proof_status"] == "PASS" for item in terminals)
        assert all(item["compile_status"] == "PASS" for item in terminals)
        assert any(item["physical_outcome"] == "compiler_identical" for item in terminals)
        assert any(item["physical_outcome"] == "duplicate" for item in terminals)
        bundle = create_training_bundle_from_search_trace(
            result["trace"], root / "training.json", project_id="fixture",
            producer_agent="test", producer_model="test", identity_path=root / "identity.json",
        )
        labels = {item["survival"]["class"] for item in bundle["branches"]}
        assert "KEEP" in labels
        assert "PRUNE_HIGH_CONFIDENCE" in labels


def test_bounded_dataflow_inference_covers_remaining_executable_families() -> None:
    fixtures = {
        "fixed-width-codec": """
            // vladder: aliasing=disjoint
            // little endian serialize append_u16 append_u16 append_u32
            void encode(std::uint8_t* out, const std::uint32_t* fields) noexcept {}
        """,
        "stateful-delta-transducer": """
            // vladder: max_elements=64
            // vladder: aliasing=disjoint
            void delta(std::vector<std::uint64_t>& changed, std::uint64_t* cache,
                       const std::uint64_t* current, const std::uint64_t* baseline,
                       std::size_t n) noexcept {
                if (n > 64 || changed.capacity() < changed.size() + n) return;
                for (std::size_t i=0;i<n;++i) if (current[i] != baseline[i]) {
                    changed.push_back(current[i]); cache[i] = current[i];
                }
            }
        """,
        "aos-fused-multi-reduction": """
            // vladder: aliasing=disjoint
            Stats classify(const Packet* packets, std::size_t n) noexcept {
                if (n > 64) return {};
                Stats result{};
                for (std::size_t i=0;i<n;++i) if (packets[i].record_kind == 2) {
                    ++result.count; result.bytes += packets[i].bytes; ++result.flagged;
                }
                return result;
            }
        """,
        "quantized-block-4x4": """
            // vladder: aliasing=disjoint
            std::uint64_t hpc_comp_encode_block(const std::uint8_t* rgba) noexcept {
                // fixed 4x4 rgb565 palette_index block
                return 0;
            }
        """,
    }
    for family, source in fixtures.items():
        inferred = infer_bounded_dataflow_contracts(source, source.split("(")[0].split()[-1], overrides={"family": family})
        selected = next(item for item in inferred if item.family == family)
        assert selected.status == "complete", (family, selected.unresolved)
        assert selected.contract() is not None


def test_lifetime_plans_are_lazy_and_proved_without_claiming_source_closure() -> None:
    repository = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "lifetime",
            root / "out",
            family="lifetime-realization",
            language="language-neutral",
            project_id="fixture",
            lifetime_manifest=repository / "examples/lifetime/lifetime_corpus.yaml",
            lifetime_trace=repository / "examples/lifetime/lifetime_trace.json",
        ))
        assert result["status"] == "pass"
        assert result["closure"]["exhaustive_within_domain"] is True
        assert result["closure"]["source_executable"] is False
        assert result["closure"]["first_incomplete_stage"] == "compilation"
        assert len(result["terminals"]) >= 4
        proof_statuses = {item["proof_status"] for item in result["terminals"]}
        assert proof_statuses == {"PASS", "FAIL"}
        assert all(item["physical_outcome"] == "proof_unknown" for item in result["terminals"])
        bundle = create_training_bundle_from_search_trace(
            result["trace"],
            root / "lifetime-training.json",
            project_id="fixture",
            producer_agent="test",
            producer_model="test",
            identity_path=root / "identity.json",
        )
        labels = {
            item["survival"]["class"]
            for item in bundle["branches"]
            if not item["baseline"]
        }
        assert labels <= {"KEEP_UNCERTAIN", "PRUNE_HIGH_CONFIDENCE", "BLOCKED_BY_CONTRACT"}
        assert "KEEP_UNCERTAIN" in labels


def test_state_and_device_protocols_are_explicit_proved_non_source_branches() -> None:
    repository = Path(__file__).resolve().parents[1]
    manifests = (
        repository / "examples/protocols/versioned_cache.yaml",
        repository / "examples/gpu/protocols/queue-valid.yaml",
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index, manifest in enumerate(manifests):
            result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
                f"protocol-{index}",
                root / f"out-{index}",
                family="bounded-protocol",
                language="language-neutral",
                project_id="fixture",
                protocol_manifest=manifest,
            ))
            assert result["status"] == "pass"
            assert result["closure"]["exhaustive_within_domain"] is True
            assert result["closure"]["source_executable"] is False
            assert result["closure"]["first_incomplete_stage"] == "compilation"
            assert result["terminals"]
            assert all(item["proof_status"] == "PASS" for item in result["terminals"])
            assert all(item["physical_outcome"] == "proof_unknown" for item in result["terminals"])
