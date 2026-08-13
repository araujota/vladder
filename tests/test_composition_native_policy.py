from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from vladder.composition_native import build_composition_trace
from vladder.lazy_search import FiniteParameterGrammar, LazySearchEngine


pytest.importorskip("torch")

SPEC = importlib.util.spec_from_file_location(
    "composition_native_policy_test", Path(__file__).parents[1] / "scripts" / "composition_native_policy.py"
)
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)


def _trace(project: str):
    graph = {"nodes": [{"id": "n", "kind": "Loop", "operation": "loop", "output_type": "i32"}], "edges": [], "obligations": [], "effects": [], "protocols": [], "claims": []}
    lazy = LazySearchEngine().run(
        FiniteParameterGrammar("schedule", {"factor": (1, 2), "banks": (1, 2)}),
        {"semantic_hash": project * 8, "semantic_graph": graph}, mode="exhaustive",
    )
    rows = [{
        "state_id": state.identity, "candidate_id": str(index), "proof_status": "PASS",
        "physical_outcome": "distinct_realization" if index == 0 else "compiler_identical",
        "search_cost": {"evaluation_wall_ms": 1.0, "proof_calls": 1, "compiler_invocation_count": 1},
    } for index, state in enumerate(lazy.terminals)]
    return build_composition_trace(
        root={"root_id": f"root-{project}", "canonical_root_hash": project * 8, "semantic_graph": graph, "contracts": {}, "cross_tu_scope": {}},
        project_id=project, source_frontend="cpp", compiler_target="clang", hardware_context={},
        lazy_result=lazy, terminal_results=rows,
    )


def test_policy_loader_and_oracle_replay(tmp_path: Path) -> None:
    for project in ("duckdb", "llama.cpp", "rocksdb"):
        directory = tmp_path / "roots" / project
        directory.mkdir(parents=True)
        import json
        (directory / "composition-native-search-trace.json").write_text(json.dumps(_trace(project)))
    decisions, trees, traces = POLICY.load_native_corpus(tmp_path)
    assert len(trees) == 3
    assert decisions and traces
    scores = POLICY.baseline_scores(decisions, "oracle")
    replay = POLICY.replay_trees(trees, scores)
    assert replay["recovery"]["1.0"]["useful"] == 1.0
    vocab = POLICY.Vocab.build(decisions)
    batch = POLICY.collate_decisions(list(decisions[:2]), vocab)
    assert batch["delta"].shape[1] == 24
    assert batch["interaction"]["node_cat"].shape[0] > 0


def test_replay_preserves_singleton_transition_priority(tmp_path: Path) -> None:
    project = "duckdb"
    directory = tmp_path / "roots" / project
    directory.mkdir(parents=True)
    import json
    (directory / "composition-native-search-trace.json").write_text(json.dumps(_trace(project)))
    decisions, trees, _ = POLICY.load_native_corpus(tmp_path)
    assert any(len(frontier.options) == 1 for frontier in trees[0].frontiers.values())
    scores = POLICY.baseline_scores(decisions, "oracle")
    replay = POLICY.replay_trees(trees, scores)
    assert replay["recovery"]["1.0"]["useful"] == 1.0
    assert replay["recovery"]["0.5"]["useful"] > 0.0
    assert replay["first_discovery"]["useful"]["roots_evaluable"] == 1
    assert replay["first_discovery"]["useful"]["mean_cost"] is not None


def test_required_policy_variants_are_available() -> None:
    variants = POLICY.configurations("all")
    assert {
        "semantic-only", "semantic-history", "semantic-history-siblings",
        "interaction-frontier", "hetero-transformer", "factor-transformer",
        "no-interaction", "no-history", "no-siblings", "no-delta",
        "no-cost-labels", "no-retained-labels",
    } <= set(variants)
    assert variants["factor-transformer"]["use_interaction"] is True


def test_frontier_ndcg_prefers_the_oracle_sibling_order() -> None:
    decisions = POLICY._trace_decisions(_trace("duckdb"))
    ranked = tuple(item for item in decisions if len(item.options) >= 2)
    oracle = POLICY.baseline_scores(ranked, "oracle")
    reversed_scores = {
        option.action_id: float(option.rank)
        for decision in ranked for option in decision.options
    }
    assert POLICY.frontier_ndcg(ranked, oracle) > POLICY.frontier_ndcg(ranked, reversed_scores)


def test_normalized_topology_is_source_order_invariant_but_contract_sensitive() -> None:
    left = {
        "nodes": [
            {"id": "producer", "kind": "Map", "operation": "decode", "output_type": "i32"},
            {"id": "consumer", "kind": "Reduce", "operation": "sum", "output_type": "i64"},
        ],
        "edges": [{"source": "producer", "destination": "consumer", "relation": "data"}],
        "obligations": [{"category": "numeric", "scope": "region", "proof_method": "z3"}],
    }
    reordered = {
        "nodes": [
            {"id": "renamed-consumer", "kind": "Reduce", "operation": "sum", "output_type": "i64"},
            {"id": "renamed-producer", "kind": "Map", "operation": "decode", "output_type": "i32"},
        ],
        "edges": [{"source": "renamed-producer", "destination": "renamed-consumer", "relation": "data"}],
        "obligations": [{"category": "numeric", "scope": "region", "proof_method": "z3"}],
    }
    different_contract = {**reordered, "obligations": [{
        "category": "ownership", "scope": "transaction", "proof_method": "model-checking",
    }]}
    assert POLICY._normalized_topology_hash(left) == POLICY._normalized_topology_hash(reordered)
    assert POLICY._normalized_topology_hash(left) != POLICY._normalized_topology_hash(different_contract)


def test_runtime_oracle_is_priority_and_proposal_only(tmp_path: Path) -> None:
    decisions = POLICY._trace_decisions(_trace("duckdb"))
    vocab = POLICY.Vocab.build(decisions)
    configuration = {
        **POLICY.configurations("factor-transformer")["factor-transformer"],
        "hidden": 64, "categorical": 16, "layers": 2, "dropout": 0.0,
    }
    model = POLICY.CompositionPolicy(vocab, configuration)
    import torch
    checkpoint = tmp_path / "checkpoint.pt"
    torch.save({"state_dict": model.state_dict(), "vocab": vocab.values, "configuration": configuration}, checkpoint)
    spec = importlib.util.spec_from_file_location(
        "composition_policy_oracle_test", Path(__file__).parents[1] / "scripts" / "composition_policy_oracle.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    oracle = module.Oracle(checkpoint, torch.device("cpu"))
    root_graph = decisions[0].semantic_graph
    root_id = "root"
    assert oracle.handle({"kind": "register_root", "root_id": root_id, "root": {"semantic_graph": root_graph}})["authority"] == "priority-only"
    frontier = [
        {"identity": f"state-{index}", "family": "schedule", "stage": "composition", "action": option.action, "semantic_state": {"selection": {str(index): "x"}}, "decision_projection": {"graph": root_graph}}
        for index, option in enumerate(decisions[0].options)
    ]
    response = oracle.handle({"kind": "rank_frontier", "root_id": root_id, "depth": 2, "parent": None, "history": [], "frontier": frontier})
    assert len(response["scores"]) == len(frontier)
    assert all("score" in item and "uncertainty" in item for item in response["scores"])
    proposal = oracle.handle({"kind": "propose_equivalence", "root_id": root_id, "depth": 2, "parent": None, "history": [], "frontier": frontier})
    assert "exact verifier required" in proposal["authority"]
    unknown_root = "unknown-root"
    oracle.handle({
        "kind": "register_root", "root_id": unknown_root,
        "root": {"semantic_graph": {
            "nodes": [{"id": "x", "kind": "NeverSeenKind", "operation": "unknown", "output_type": "opaque"}],
            "edges": [],
        }},
    })
    unknown = oracle.handle({
        "kind": "rank_frontier", "root_id": unknown_root, "depth": 2,
        "parent": None, "history": [], "frontier": frontier,
    })
    assert all(item["in_distribution"] is False for item in unknown["scores"])
