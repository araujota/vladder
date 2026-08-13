from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import tempfile

import pytest

from vladder.canonical_search import (
    ActionFootprint,
    CanonicalSearchEngine,
    CanonicalizationPolicy,
    Canonicalizer,
    GrammarDependencyGraph,
    IndependenceVerifier,
    LayeredStateHash,
    OptimizationSignature,
    TranspositionTable,
    canonical_result_to_lazy,
    compare_terminal_sets,
    optimization_equivalence_proposals,
    reduction_waterfall,
    typed_wl_labels,
)
from vladder.lazy_search import LazyState
from vladder.executable_search import ExecutableSearchEngine, ExecutableSearchRequest
from vladder.schema_registry import validate_payload
from vladder.search_reductions import (
    LocalEGraph,
    commutative_rewrite,
    qualify_dominance,
    qualify_macro,
)
from vladder.selected_build_search import SelectedBuildCppGrammar


def _selected_build_grammar(regions: int = 3) -> SelectedBuildCppGrammar:
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


def test_canonical_dag_collapses_paths_and_retains_every_parent_edge() -> None:
    result = CanonicalSearchEngine().run(
        _selected_build_grammar(2), {"semantic_hash": "root"}, mode="exhaustive_canonical",
    )
    assert result.complete
    assert len(result.terminal_state_ids) == 4
    assert result.metrics.exact_transpositions == 4
    terminal_records = [item for item in result.states if item.state.terminal]
    assert any(len(item.parent_edges) == 2 for item in terminal_records)
    assert validate_payload("canonical-state-dag", result.to_dict())["status"] == "pass"


def test_reduced_search_avoids_construction_and_preserves_all_terminals() -> None:
    engine = CanonicalSearchEngine()
    grammar = _selected_build_grammar(4)
    full = engine.run(grammar, {"semantic_hash": "root"}, mode="exhaustive_canonical")
    reduced = engine.run(grammar, {"semantic_hash": "root"}, mode="exhaustive_reduced")
    parity = compare_terminal_sets(full, reduced)
    assert parity["status"] == "PASS"
    assert parity["preservation_ratio"] == 1.0
    assert len(reduced.terminal_state_ids) == 16
    assert reduced.metrics.por_avoided_transitions > 0
    assert reduced.metrics.candidate_constructions < full.metrics.candidate_constructions
    assert reduction_waterfall(reduced)["steps"][-1]["remaining"] == reduced.metrics.unique_canonical_states
    compatibility = canonical_result_to_lazy(reduced)
    assert len(compatibility.terminals) == 16
    assert compatibility.canonicalized == (
        reduced.metrics.exact_transpositions
        + reduced.metrics.alpha_equivalent_collapses
        + reduced.metrics.symmetry_collapses
    )
    sleep = engine.run(
        grammar,
        {"semantic_hash": "root"},
        mode="exhaustive_reduced",
        por_strategy="sleep_set",
    )
    assert sleep.por_strategy == "sleep_set"
    assert compare_terminal_sets(full, sleep)["status"] == "PASS"


def test_unknown_footprints_fail_open_as_dependent() -> None:
    left = ActionFootprint.from_action({"op": "left"})
    right = ActionFootprint.from_action({"op": "right"})
    assert IndependenceVerifier.static_screen(left, right) == (
        False, "unknown footprint is dependent",
    )


def test_static_independence_rejects_shared_alias_and_contract_state() -> None:
    left = ActionFootprint.from_action({
        "action_key": "left",
        "footprint": {"complete": True, "aliases": ["buffer"], "contracts_write": ["valid"]},
    })
    alias = ActionFootprint.from_action({
        "action_key": "alias",
        "footprint": {"complete": True, "aliases": ["buffer"]},
    })
    contract = ActionFootprint.from_action({
        "action_key": "contract",
        "footprint": {"complete": True, "contracts_read": ["valid"]},
    })
    assert IndependenceVerifier.static_screen(left, alias)[0] is False
    assert IndependenceVerifier.static_screen(left, contract)[0] is False


def test_hash_collision_does_not_merge_distinct_canonical_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    table = TranspositionTable()
    monkeypatch.setattr(table.canonicalizer, "envelope", lambda state: replace(
        Canonicalizer().envelope(state), digest="forced-collision",
    ))
    first, created_first, _ = table.intern(
        LazyState("x", "candidate", {"value": 1}, {"op": "one"}),
        depth=0, path=(), edge_id="e1",
    )
    second, created_second, _ = table.intern(
        LazyState("x", "candidate", {"value": 2}, {"op": "two"}),
        depth=0, path=(), edge_id="e2",
    )
    assert created_first and created_second
    assert first.state_id != second.state_id
    assert table.hash_collisions == 1


def test_alpha_equivalence_is_explicit_and_preserves_atomic_distinctions() -> None:
    canonicalizer = Canonicalizer(CanonicalizationPolicy(enable_alpha=True))
    left = LazyState(
        "x", "candidate",
        {"_nonobservable_ids": ["tmp_4"], "temporary": "tmp_4", "atomic": True},
        {"op": "x"},
    )
    right = LazyState(
        "x", "candidate",
        {"_nonobservable_ids": ["tmp_19"], "temporary": "tmp_19", "atomic": True},
        {"op": "x"},
    )
    nonatomic = LazyState(
        "x", "candidate",
        {"_nonobservable_ids": ["tmp_9"], "temporary": "tmp_9", "atomic": False},
        {"op": "x"},
    )
    assert canonicalizer.envelope(left).canonical_bytes == canonicalizer.envelope(right).canonical_bytes
    assert canonicalizer.envelope(left).digest != canonicalizer.envelope(nonatomic).digest


def test_explicit_symmetry_collapses_interchangeable_nodes_only() -> None:
    def state(first: str, second: str, *, observable: bool = False) -> LazyState:
        return LazyState("x", "candidate", {
            "graph": {
                "nodes": [
                    {"id": first, "kind": "lane", "symmetry_class": "lane", "identity_observable": observable},
                    {"id": second, "kind": "lane", "symmetry_class": "lane", "identity_observable": observable},
                ],
                "edges": [{"source": first, "target": second, "kind": "peer"}],
            }
        }, {"op": "x"})

    canonicalizer = Canonicalizer()
    left = state("lane-a", "lane-b")
    right = state("lane-y", "lane-z")
    visible = state("lane-y", "lane-z", observable=True)
    assert canonicalizer.envelope(left).digest == canonicalizer.envelope(right).digest
    assert canonicalizer.envelope(left).digest != canonicalizer.envelope(visible).digest


def test_typed_wl_refinement_retains_node_and_edge_colors() -> None:
    labels = typed_wl_labels({
        "nodes": [{"id": "a", "kind": "load"}, {"id": "b", "kind": "store"}],
        "edges": [{"source": "a", "target": "b", "kind": "data"}],
    })
    assert labels["a"] != labels["b"]


def test_incremental_hash_must_equal_clean_rematerialization() -> None:
    baseline = {"a": 1, "b": {"value": 2}}
    layered = LayeredStateHash.build(baseline)
    changed = {"a": 3, "b": {"value": 2}}
    assert layered.update(changed, changed={"a": 3}) == LayeredStateHash.build(changed)
    with pytest.raises(ValueError, match="clean rematerialization"):
        layered.update(changed, changed={"a": 4})


def test_dependency_graph_topological_order_and_cycle_detection() -> None:
    actions = (
        {"action_key": "a", "footprint": {"complete": True}},
        {"action_key": "b", "footprint": {"complete": True, "requires": ["a"]}},
    )
    assert GrammarDependencyGraph.build(actions).topological_order() == ("a", "b")
    cyclic = (
        {"action_key": "a", "footprint": {"complete": True, "requires": ["b"]}},
        {"action_key": "b", "footprint": {"complete": True, "requires": ["a"]}},
    )
    graph = GrammarDependencyGraph.build(cyclic)
    assert graph.topological_order() is None


def test_dominance_and_macro_require_descendant_relations() -> None:
    engine = CanonicalSearchEngine()
    two = engine.run(_selected_build_grammar(2), {"semantic_hash": "root"})
    one = engine.run(_selected_build_grammar(1), {"semantic_hash": "root"})
    assert qualify_dominance(one, two).status == "REJECTED"
    assert qualify_macro(two, two).status == "PASS"
    assert qualify_macro(two, one).status == "REJECTED"


def test_bounded_local_egraph_records_exact_commutative_class() -> None:
    expression = {"op": "add", "args": ["x", "y"]}
    result = LocalEGraph().saturate((expression,), (commutative_rewrite(("add",)),))
    assert result.status == "PASS"
    assert result.e_nodes == 2
    assert result.e_classes == 1
    assert result.unions == 1


def test_optimization_signature_only_proposes_coarse_pairs() -> None:
    result = CanonicalSearchEngine().run(
        _selected_build_grammar(1), {"semantic_hash": "root"}, mode="exhaustive_canonical",
    )
    assert all(OptimizationSignature.from_record(record).digest for record in result.states)
    assert all(len(item) == 3 for item in optimization_equivalence_proposals(result.states))


def test_canonical_source_search_projects_parents_before_children() -> None:
    if not shutil.which("rustc"):
        pytest.skip("rustc unavailable")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "count.rs"
        source.write_text(
            "fn binary_count_ones(opt: Option<&[u8]>) -> Option<i64> { "
            "opt.map(|value| value.iter().map(|b| b.count_ones() as i64).sum()) }\n"
        )
        result = ExecutableSearchEngine(root / "cache").search(ExecutableSearchRequest(
            "canonical-smoke", root / "out", source=source, function="binary_count_ones",
            language="rust", family="bit-popcount-reduction", project_id="fixture",
            search_mode="exhaustive_canonical",
        ))
        assert result["status"] == "pass"
        assert len(result["terminals"]) == 3
        assert validate_payload("canonical-state-dag", result["canonical_state_dag"])["status"] == "pass"
        assert (root / "out" / "canonical-state-dag.json").is_file()
