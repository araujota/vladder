from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest


pytest.importorskip("torch")


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "search_pruner.py"
    spec = importlib.util.spec_from_file_location("vladder_search_pruner_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _example(module, branch: str, parent: str | None, target: int, *, state: str = "terminal"):
    utility = {
        "proof_valid": bool(target),
        "distinct_realization": bool(target),
        "physically_material": False,
        "promoted": False,
        "retained": False,
    }
    return module.Example(
        project="p",
        root_id="r",
        search_id="s",
        branch_id=branch,
        parent_branch_id=parent,
        graph={
            "node_features": [{"kind": "Map", "operation": "map", "type_class": "integer"}],
            "edge_index": [[], []],
            "edge_features": [],
            "obligations": [],
            "effects": [],
            "protocols": [],
            "claims": [],
        },
        stage="composition",
        depth=2 if parent else 1,
        baseline=False,
        action={
            "family": "test",
            "family_version": "v1",
            "primitives": ["x"],
            "numeric_parameters": [],
            "categorical_parameters": [],
        },
        lineage=(),
        target=target,
        policy_surface=True,
        branch_state=state,
        children_status="not_applicable" if state == "terminal" else "exhaustive",
        direct_utility=utility,
        descendant_utility={**utility, "useful": bool(target)},
        utility_severity=2 if target else 0,
    )


def test_forest_derivation_propagates_cost_and_useful_terminal() -> None:
    module = _module()
    root = _example(module, "a" * 64, None, 1, state="expanded")
    child = _example(module, "b" * 64, root.branch_id, 1)
    derived = module.derive_search_forest([root, child])
    assert derived[0].subtree_size == 2
    assert derived[0].useful_terminal_count == 1
    assert derived[0].utility_severity == 2


def test_post_search_outcomes_do_not_change_inference_tensors() -> None:
    module = _module()
    positive = _example(module, "a" * 64, None, 1)
    negative = replace(
        positive,
        branch_id="b" * 64,
        target=0,
        failure_class="proof_dead",
        direct_utility={},
        descendant_utility={},
        utility_severity=0,
        subtree_cost=100.0,
    )
    vocab = module.Vocab.build([positive, negative])
    first = module.tensorize(positive, vocab)
    second = module.tensorize(negative, vocab)
    outcome_keys = {"target", "cost_target", "severity_target", "failure_target"}
    for key in first.keys() - outcome_keys:
        assert first[key].equal(second[key]), key


def test_online_replay_counts_pruned_subtree_once() -> None:
    module = _module()
    root = _example(module, "a" * 64, None, 0, state="expanded")
    child = _example(module, "b" * 64, root.branch_id, 0)
    rows = [{"example": item} for item in module.derive_search_forest([root, child])]
    decisions = {
        ("p", "r", root.branch_id): {"prune": True},
        ("p", "r", child.branch_id): {"prune": True},
    }
    replay = module.online_replay(rows, decisions)
    assert replay["avoided_branch_evaluations"] == 2
    assert replay["online_expansion_reduction"] == 1.0


def test_unknown_action_fails_open() -> None:
    module = _module()
    example = _example(module, "a" * 64, None, 0)
    row = {
        "example": example,
        "unknown": True,
        "uncertainty": 0.0,
        "probability": 0.0,
        "embedding": np.zeros(2),
        "signature": "x",
    }
    calibration = {
        "ood": {"composition": {"center": np.zeros(2), "scale": np.ones(2), "limit": 1.0}},
        "known_families": ["test"],
        "exploration_fraction": 0.0,
        "uncertainty_limits": {"composition": 1.0},
        "thresholds": {},
        "exact_history": {},
        "retrieval": {},
        "uncertainty_k": 2.0,
        "minimum_retrieval_support": 1,
        "retrieval_neighbors": 1,
    }
    decision = module.policy_decision(row, calibration)
    assert decision["prune"] is False
    assert decision["reason"] == "unknown_or_new_family"


def _prunable_calibration() -> dict:
    return {
        "ood": {"composition": {"center": np.zeros(2), "scale": np.ones(2), "limit": 1.0}},
        "known_families": ["test"],
        "exploration_fraction": 0.0,
        "uncertainty_limits": {"composition": 1.0},
        "thresholds": {"composition": {"threshold": 0.1}},
        "exact_history": {},
        "retrieval": {
            "composition:test": {
                "embeddings": np.asarray([[1.0, 0.0], [0.9, 0.1]], dtype=np.float32),
                "targets": np.asarray([0, 0], dtype=np.int8),
                "center": np.zeros(2),
                "scale": np.ones(2),
                "ood_limit": 1.0,
            }
        },
        "uncertainty_k": 3.0,
        "minimum_retrieval_support": 2,
        "retrieval_neighbors": 2,
    }


def test_decision_ood_fails_open() -> None:
    module = _module()
    example = _example(module, "a" * 64, None, 0)
    row = {
        "example": example,
        "unknown": False,
        "uncertainty": 0.0,
        "probability": 0.0,
        "embedding": np.asarray([4.0, 4.0], dtype=np.float32),
        "signature": "x",
    }
    decision = module.policy_decision(row, _prunable_calibration())
    assert decision["prune"] is False
    assert decision["reason"] == "decision_ood"


def test_positive_retrieval_neighbor_vetoes_pruning() -> None:
    module = _module()
    example = _example(module, "a" * 64, None, 0)
    row = {
        "example": example,
        "unknown": False,
        "uncertainty": 0.0,
        "probability": 0.0,
        "embedding": np.asarray([1.0, 0.0], dtype=np.float32),
        "signature": "x",
    }
    calibration = _prunable_calibration()
    calibration["retrieval"]["composition:test"]["targets"] = np.asarray([1, 0], dtype=np.int8)
    decision = module.policy_decision(row, calibration)
    assert decision["prune"] is False
    assert decision["reason"] == "positive_nearest_neighbor"
