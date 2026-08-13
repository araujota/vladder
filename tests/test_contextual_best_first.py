from __future__ import annotations

from dataclasses import replace

from vladder.frontier_training import decision_bundle
from vladder.lazy_search import (
    FiniteParameterGrammar,
    FrontierScore,
    LazySearchEngine,
    LazyState,
)
from vladder.schema_registry import validate_payload


class PreferLargeFactor:
    def score(self, parent, frontier, *, depth, history, root_context):
        return tuple(
            FrontierScore(float(item.semantic_state.get("parameters", {}).get("factor", 0)))
            for item in frontier
        )


def test_contextual_priority_changes_order_without_changing_completeness() -> None:
    grammar = FiniteParameterGrammar("schedule", {"factor": (1, 2, 4)})
    result = LazySearchEngine().run(
        grammar,
        {"semantic_hash": "root"},
        frontier_policy=PreferLargeFactor(),
        mode="exhaustive",
    )
    assert result.complete is True
    assert [item.semantic_state["parameters"]["factor"] for item in result.terminals] == [4, 2, 1]
    assert result.policy_pruned == 0
    assert result.frontier_decisions
    assert result.frontier_decisions[-1].chosen_state_hash == result.terminals[0].identity


def test_fast_mode_stops_by_budget_but_never_reports_policy_pruning() -> None:
    result = LazySearchEngine().run(
        FiniteParameterGrammar("schedule", {"factor": (1, 2, 4), "banks": (1, 2, 4)}),
        {"semantic_hash": "root"},
        frontier_policy=PreferLargeFactor(),
        mode="fast",
        work_budget=3,
    )
    assert result.complete is False
    assert result.policy_pruned == 0
    assert len(result.nodes) == 3


def test_fast_mode_accepts_a_strict_time_budget_without_deletion() -> None:
    result = LazySearchEngine().run(
        FiniteParameterGrammar("schedule", {"factor": tuple(range(100))}),
        {"semantic_hash": "root"},
        mode="fast",
        time_budget_seconds=1e-12,
    )
    assert result.complete is False
    assert result.policy_pruned == 0


class DuplicateGrammar:
    def initial_states(self, root_context):
        return (
            LazyState(
                "test", "candidate", {"value": 1}, {"family": "test", "op": "left"},
                terminal=True, identity="a" * 64,
            ),
            LazyState(
                "test", "candidate", {"value": 1}, {"family": "test", "op": "right"},
                terminal=True, identity="a" * 64,
            ),
        )

    def expand(self, state, root_context):
        return ()


def test_exact_transposition_precedes_frontier_scoring() -> None:
    seen = []

    class Recorder:
        def score(self, parent, frontier, *, depth, history, root_context):
            seen.append(len(frontier))
            return tuple(FrontierScore(0.0) for _ in frontier)

    result = LazySearchEngine().run(
        DuplicateGrammar(),
        {"semantic_hash": "root"},
        frontier_policy=Recorder(),
        mode="exhaustive",
    )
    assert seen == [1]
    assert result.canonicalized == 1
    assert len(result.terminals) == 1


def test_learned_equivalence_proposal_requires_verifier_acceptance() -> None:
    class Proposer:
        def propose(self, parent, frontier, *, history, root_context):
            return ((0, 1),)

    grammar = FiniteParameterGrammar("schedule", {"factor": (1, 2)})
    rejected = LazySearchEngine().run(
        grammar,
        {"semantic_hash": "root"},
        mode="exhaustive",
        equivalence_proposer=Proposer(),
        equivalence_verifier=lambda left, right, context: False,
    )
    accepted = LazySearchEngine().run(
        grammar,
        {"semantic_hash": "root"},
        mode="exhaustive",
        equivalence_proposer=Proposer(),
        equivalence_verifier=lambda left, right, context: True,
    )
    assert len(rejected.terminals) == 2
    assert rejected.verified_equivalences == 0
    assert len(accepted.terminals) == 1
    assert accepted.verified_equivalences == 1


class CommutativeGrammar:
    def initial_states(self, root_context):
        return tuple(self._state((name,), name) for name in ("a", "b"))

    def expand(self, state, root_context):
        selected = tuple(state.semantic_state["selected"])
        if len(selected) == 2:
            return ()
        remaining = "b" if selected == ("a",) else "a"
        return (self._state(tuple(sorted((*selected, remaining))), remaining, terminal=True),)

    @staticmethod
    def _state(selected, action, terminal=False):
        return LazyState("composition", "composition", {"selected": selected}, {"op": action}, terminal=terminal)


def test_commutative_action_order_is_collapsed_by_exact_state_identity() -> None:
    result = LazySearchEngine().run(CommutativeGrammar(), {"semantic_hash": "root"}, mode="exhaustive")
    assert result.complete is True
    assert result.canonicalized == 1
    assert len(result.terminals) == 1


def test_decision_bundle_schema_and_outcome_isolation() -> None:
    from vladder.frontier_training import FrontierActionRecord, FrontierOutcome, SearchDecision

    outcome = FrontierOutcome(1, True, False, 1, {"node_expansions": 2}, "unique")
    action = FrontierActionRecord(
        "branch-a",
        {"family": "test"},
        {},
        (),
        1,
        1,
        (),
        None,
        None,
        None,
        outcome,
    )
    decision = SearchDecision(
        "decision-a",
        "project",
        "root-a",
        "search-a",
        "parent-a",
        {"graph": {}},
        (),
        {},
        1,
        None,
        (action, replace(action, branch_id="branch-b")),
        "branch-a",
        ("historical_limit",),
    )
    changed = replace(
        decision,
        frontier=(replace(action, outcome=replace(outcome, contains_useful_descendant=False)), decision.frontier[1]),
    )
    assert decision.inference_view() == changed.inference_view()
    report = validate_payload(
        "search-decision-bundle",
        decision_bundle((decision,), source_schema="vladder-model-training-bundle-v3"),
    )
    assert report["status"] == "pass"
