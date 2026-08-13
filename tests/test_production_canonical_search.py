from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import tempfile

import pytest

from vladder.canonical_search import (
    CanonicalSearchEngine,
    Canonicalizer,
    TranspositionTable,
    compare_terminal_sets,
)
from vladder.executable_search import ExecutableSearchEngine, ExecutableSearchRequest
from vladder.lazy_search import LazyState
from vladder.production_search import (
    AdaptiveReductionPolicy,
    ProductionCanonicalSearchEngine,
    ProductionSearchConfig,
    RollingSearchCostModel,
)
from vladder.schema_registry import validate_payload
from vladder.selected_build_search import SelectedBuildCppGrammar


def _grammar(regions: int = 4) -> SelectedBuildCppGrammar:
    return SelectedBuildCppGrammar({
        "closure": {
            "candidates": [
                {
                    "id": f"region-{index}-unroll-2",
                    "region_id": f"region-{index}",
                    "schedule_choice": "unroll-2",
                    "source_sha256": f"candidate-{index}",
                }
                for index in range(regions)
            ]
        }
    })


def test_concurrent_transposition_intern_has_one_deterministic_owner() -> None:
    table = TranspositionTable()
    state = LazyState("fixture", "candidate", {"value": 7}, {"op": "same"})

    def register(index: int):
        return table.intern(state, depth=index % 3, path=({"op": "same"},), edge_id=f"edge-{index}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(register, range(64)))
    assert sum(created for _, created, _ in outcomes) == 1
    assert len(table.records) == 1
    record = next(iter(table.records.values()))
    assert record.state_id.startswith("canonical-semantic-state-v2:")
    assert len(record.parent_edges) == 64


def test_adaptive_policy_declines_cheap_frontier_and_accepts_expensive_one() -> None:
    grammar = _grammar(3)
    root = next(iter(grammar.initial_states({})))
    actions = grammar.enabled_actions(root, {})
    cheap = AdaptiveReductionPolicy(RollingSearchCostModel())
    assert cheap.allow_por(root, actions, 0, {}) is False

    costs = RollingSearchCostModel()
    costs.seed(root.family, {
        "candidate_construction_ms": 2.0,
        "proof_ms": 50.0,
        "compile_ms": 75.0,
        "canonicalization_ms": 0.02,
        "commutativity_ms": 0.05,
        "descendant_fanout": 4.0,
        "transposition_rate": 0.5,
    })
    expensive = AdaptiveReductionPolicy(costs)
    assert expensive.allow_por(root, actions, 0, {}) is True


def test_production_result_validates_and_exhaustive_alias_uses_canonical_dag() -> None:
    engine = ProductionCanonicalSearchEngine()
    result = engine.run(
        _grammar(3),
        {"semantic_hash": "production", "grammar_version": "fixture-v1"},
        config=ProductionSearchConfig(mode="exhaustive", por_policy="force"),
    )
    assert result.effective_mode == "exhaustive_reduced"
    assert result.canonical_result.complete
    assert result.canonical_result.metrics.por_avoided_transitions > 0
    assert validate_payload("production-canonical-search", result.to_dict())["status"] == "pass"
    families = result.footprint_audit["families"]
    assert families and all(row["complete_ratio"] == 1.0 for row in families)


def test_checkpoint_resume_preserves_terminal_set_and_rejects_identity_change() -> None:
    grammar = _grammar(4)
    context = {"semantic_hash": "checkpoint", "grammar_version": "fixture-v1"}
    with tempfile.TemporaryDirectory() as directory:
        checkpoint = Path(directory) / "search.json"
        engine = ProductionCanonicalSearchEngine()
        partial = engine.run(
            grammar,
            context,
            config=ProductionSearchConfig(
                mode="fast", work_budget=2, por_policy="off", checkpoint_path=checkpoint,
            ),
        )
        assert not partial.canonical_result.complete
        assert checkpoint.is_file()
        assert validate_payload(
            "production-search-checkpoint",
            __import__("json").loads(checkpoint.read_text()),
        )["status"] == "pass"
        resumed = engine.run(
            grammar,
            context,
            config=ProductionSearchConfig(
                mode="exhaustive_canonical", work_budget=100_000,
                resume_path=checkpoint, checkpoint_path=checkpoint,
            ),
        )
        full = CanonicalSearchEngine().run(grammar, context, mode="exhaustive_canonical")
        assert resumed.canonical_result.complete
        assert compare_terminal_sets(full, resumed.canonical_result)["status"] == "PASS"
        with pytest.raises(ValueError, match="incompatible"):
            engine.run(
                grammar,
                {**context, "semantic_hash": "changed"},
                config=ProductionSearchConfig(
                    mode="exhaustive_canonical", resume_path=checkpoint,
                ),
            )


def test_memory_ceiling_stops_without_losing_identity() -> None:
    result = ProductionCanonicalSearchEngine().run(
        _grammar(5),
        {"semantic_hash": "memory", "grammar_version": "fixture-v1"},
        config=ProductionSearchConfig(
            mode="exhaustive", memory_ceiling_bytes=1, por_policy="off",
        ),
    )
    assert not result.canonical_result.complete
    assert result.canonical_result.metrics.memory_ceiling_stops == 1
    assert result.resource_policy["identity_preserved_on_resource_stop"] is True


def test_source_search_exhaustive_default_emits_production_artifact() -> None:
    if not shutil.which("rustc"):
        pytest.skip("rustc unavailable")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "count.rs"
        source.write_text(
            "fn binary_count_ones(opt: Option<&[u8]>) -> Option<i64> { "
            "opt.map(|value| value.iter().map(|b| b.count_ones() as i64).sum()) }\n"
        )
        request = ExecutableSearchRequest(
            "production-default", root / "out", source=source, function="binary_count_ones",
            language="rust", family="bit-popcount-reduction", project_id="fixture",
            search_mode="exhaustive",
        )
        result = ExecutableSearchEngine(root / "cache").search(request)
        assert result["production_canonical_search"] is not None
        assert result["production_canonical_search"]["effective_mode"] == "exhaustive_reduced"
        assert (root / "out" / "production-canonical-search.json").is_file()
