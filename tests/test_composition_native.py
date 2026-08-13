from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile

from vladder.composition_native import (
    build_composition_trace,
    build_interaction_graph,
    composition_trace_integrity_errors,
    exact_state_delta,
    inference_view,
    normalize_terminal_ownership,
)
from vladder.lazy_search import FiniteParameterGrammar, LazySearchEngine
from vladder.schema_registry import validate_payload
from vladder.selected_build_search import SelectedBuildCppGrammar


def _semantic_graph() -> dict:
    return {
        "nodes": [
            {
                "id": "buffer",
                "kind": "MaterializedBuffer",
                "operation": "materialize",
                "output_type": "bytes",
                "attributes": {"lifetime": "function", "ownership": "ephemeral", "placement": "cpu"},
            }
        ],
        "edges": [],
        "obligations": [{"id": "exact", "proof_method": "z3"}],
        "effects": [],
        "protocols": [],
        "claims": [],
    }


def test_exact_delta_and_interaction_graph_are_deterministic() -> None:
    parent = {"graph": _semantic_graph(), "focus_node_ids": ["buffer"]}
    child = deepcopy(parent)
    child["graph"]["nodes"][0]["attributes"]["lifetime"] = "generation"
    delta = exact_state_delta(parent, child, {"scope": "function"}, {"scope": "generation"})
    assert delta["lifetime_changes"]
    assert delta == exact_state_delta(parent, child, {"scope": "function"}, {"scope": "generation"})
    interaction = build_interaction_graph(
        parent,
        ({"family": "lifetime", "op": "retain"}, {"family": "schedule", "op": "defer"}),
        ({
            "state_hash": "a" * 64,
            "action": {"family": "composition", "op": "fuse", "requires_actions": ["0", "1"]},
            "decision_context": child,
            "state_delta": delta,
        },),
    )
    kinds = {item["kind"] for item in interaction["nodes"]}
    relations = {item["relation"] for item in interaction["edges"]}
    assert "interaction_factor" in kinds
    assert "EXTENDS_LIFETIME" in relations
    assert interaction == build_interaction_graph(
        parent,
        ({"family": "lifetime", "op": "retain"}, {"family": "schedule", "op": "defer"}),
        ({
            "state_hash": "a" * 64,
            "action": {"family": "composition", "op": "fuse", "requires_actions": ["0", "1"]},
            "decision_context": child,
            "state_delta": delta,
        },),
    )


def test_native_trace_labels_descendant_utility_and_isolates_outcomes() -> None:
    result = LazySearchEngine().run(
        FiniteParameterGrammar("schedule", {"factor": (1, 2), "banks": (1, 2)}),
        {"semantic_hash": "f" * 64, "semantic_graph": _semantic_graph()},
        mode="exhaustive",
    )
    terminal_rows = []
    for index, terminal in enumerate(result.terminals):
        terminal_rows.append({
            "state_id": terminal.identity,
            "candidate_id": f"candidate-{index}",
            "proof_status": "PASS",
            "physical_outcome": "distinct_realization" if index == 0 else "compiler_identical",
            "compile_status": "PASS",
            "benchmark_status": "not_run",
            "search_cost": {"proof_calls": 1, "compiler_invocation_count": 1, "evaluation_wall_ms": 2.0},
        })
    trace = build_composition_trace(
        root={
            "root_id": "root",
            "canonical_root_hash": "f" * 64,
            "semantic_graph": _semantic_graph(),
            "contracts": {},
            "cross_tu_scope": {},
        },
        project_id="project",
        source_frontend="cpp",
        compiler_target="clang-test",
        hardware_context={"cpu": "test"},
        lazy_result=result,
        terminal_results=terminal_rows,
    )
    assert trace["summary"]["frontier_count"] >= 3
    assert any(
        outcome["best_descendant_tier"] == "U2"
        for label in trace["labels"] for outcome in label["action_outcomes"]
    )
    assert any(
        outcome["redundancy_class"] == "compiler-identical"
        for label in trace["labels"] for outcome in label["action_outcomes"]
    )
    report = validate_payload("composition-native-search-trace", trace)
    assert report["status"] == "pass"
    assert composition_trace_integrity_errors(trace) == []
    assert trace["training_contract"]["future_policy_training_eligible"] is True

    relabeled = deepcopy(trace)
    relabeled["terminals"][0]["utility_tier"] = "U4"
    relabeled["labels"][0]["action_outcomes"][0]["best_descendant_tier"] = "U4"
    assert inference_view(trace) == inference_view(relabeled)
    inference = inference_view(trace)
    assert "states" not in inference
    assert "transpositions" not in inference
    assert all("selected_action" not in item for item in inference["frontiers"])

    missing_sibling = deepcopy(trace)
    missing_sibling["frontiers"][0]["available_actions"].pop()
    assert any("size does not match" in item for item in composition_trace_integrity_errors(missing_sibling))

    truncated = deepcopy(trace)
    truncated["complete"] = False
    unrealized_hash = "0" * 64
    truncated["frontiers"][0]["available_actions"][0]["child_state_hash"] = unrealized_hash
    truncated["frontiers"][0]["selected_action"] = unrealized_hash
    truncated["training_contract"].update({
        "frontier_context": "partial",
        "future_policy_training_eligible": False,
        "limitations": ["search_not_exhaustive", "frontier_context_incomplete"],
    })
    truncated_payload = {key: value for key, value in truncated.items() if key != "trace_hash"}
    from vladder.language_adapter import canonical_hash
    truncated["trace_hash"] = canonical_hash(truncated_payload)
    assert composition_trace_integrity_errors(truncated) == []


def test_exact_transpositions_are_reported_separately() -> None:
    from tests.test_contextual_best_first import CommutativeGrammar

    result = LazySearchEngine().run(
        CommutativeGrammar(),
        {"semantic_hash": "e" * 64, "semantic_graph": _semantic_graph()},
        mode="exhaustive",
    )
    trace = build_composition_trace(
        root={
            "root_id": "root",
            "canonical_root_hash": "e" * 64,
            "semantic_graph": _semantic_graph(),
            "contracts": {},
            "cross_tu_scope": {},
        },
        project_id="project",
        source_frontend="cpp",
        compiler_target="clang-test",
        hardware_context={},
        lazy_result=result,
        terminal_results=({
            "state_id": result.terminals[0].identity,
            "candidate_id": "candidate",
            "proof_status": "PASS",
            "physical_outcome": "distinct_realization",
            "search_cost": {},
        },),
    )
    assert trace["summary"]["transposition_count"] == 1
    assert trace["transpositions"][0]["authority"] == "exact_canonical_hash"
    state_by_id = {item["state_id"]: item for item in trace["states"]}
    assert not state_by_id[trace["terminals"][0]["state_id"]]["canonical_of"]
    assert any(
        outcome["best_descendant_tier"] == "U2"
        for label in trace["labels"]
        for outcome in label["action_outcomes"]
    )

    corrupted = deepcopy(trace)
    corrupted["terminals"][0]["state_id"] = trace["transpositions"][0]["state_id"]
    repaired, changes = normalize_terminal_ownership(corrupted)
    assert changes == 1
    assert repaired["terminals"][0]["state_id"] == trace["terminals"][0]["state_id"]
    assert repaired["trace_hash"] == trace["trace_hash"]


def test_selected_build_exposes_orderings_and_canonicalizes_partial_states() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources = {}
        for region in ("region-a", "region-b"):
            path = root / f"{region}.cpp"
            path.write_text(f"// {region}\n#pragma clang loop unroll_count(2)\n")
            sources[region] = path
        report = {
            "closure": {
                "candidates": [
                    {
                        "id": f"{region}-unroll-2",
                        "region_id": region,
                        "schedule_choice": "unroll-2",
                        "repository_candidate_source": str(path),
                    }
                    for region, path in sources.items()
                ]
            }
        }
        result = LazySearchEngine().run(
            SelectedBuildCppGrammar(report),
            {"semantic_hash": "d" * 64, "semantic_graph": _semantic_graph()},
            mode="exhaustive",
        )
    assert len(result.terminals) == 4
    assert result.canonicalized == 4
    assert any(
        len(frontier.frontier) == 4
        for frontier in result.frontier_decisions
    )
