from __future__ import annotations

import json
from pathlib import Path
import tempfile

from vladder.model_training_data import graph_learning_examples
from vladder.prior_data import PriorExperienceStore, make_candidate, make_observation, make_root
from vladder.search_training import (
    build_search_training_bundle,
    make_branch,
    make_branch_observation,
    make_search,
    search_training_integrity_errors,
)
from vladder.training_workflow import (
    create_training_bundle_from_prior,
    create_training_bundle_from_search_trace,
    validate_training_bundle,
)


def _root() -> dict:
    graph = {
        "schema_version": "semantic-flow-v2",
        "nodes": [
            {"id": "input", "kind": "LoadStream", "operation": "load", "output_type": "i8"},
            {"id": "reduce", "kind": "Reduce", "operation": "reduce", "output_type": "i64"},
        ],
        "edges": [{"source": "input", "destination": "reduce", "relation": "data", "ordering": "ordered"}],
        "obligations": [{"category": "equivalence", "scope": "local", "proof_method": "z3"}],
        "effects": [], "protocols": [], "claims": [],
    }
    return make_root(graph, {"bounded": True, "exactness": "exact"}, [{"source_language": "cpp"}], project_id="fixture")


def _trace(*, positive: bool = True, complete: bool = True) -> dict:
    root = _root()
    search_id = "a" * 64
    root_branch = make_branch(
        search_id, {"family": "baseline", "family_version": "v1", "primitives": ["existing_implementation"]},
        parent_branch_id=None, depth=0, stage="baseline", baseline=True, state="expanded",
        evidence_coverage="partial",
        coverage={
            "children_status": "exhaustive" if complete else "partially_enumerated",
            "emitted_child_count": 1, "expected_child_count": 1 if complete else None,
            "completeness_reason": "exhaustive_grammar" if complete else "budget",
        }, identity_material="root-branch",
    )
    leaf = make_branch(
        search_id, {"family": "simd_mask", "family_version": "v1", "primitives": ["mask", "popcount"]},
        parent_branch_id=root_branch["branch_id"], depth=1, stage="candidate_family", state="terminal",
        evidence_coverage="complete" if complete else "partial",
        coverage={
            "children_status": "not_applicable", "emitted_child_count": 0, "expected_child_count": 0,
            "completeness_reason": "terminal" if complete else "unknown",
        }, identity_material="leaf-branch",
    )
    search = make_search(
        root["root_id"], root_branch["branch_id"], {"architecture": "x86_64"}, {"phase": "other"},
        grammar_version="deep-v2", grammar_hash="b" * 64,
        selection_policy="bounded_exhaustive" if complete else "heuristic",
        coverage="complete" if complete else "truncated",
        stage_coverage={
            "grammar_family": "complete" if complete else "partial",
            "candidate_family": "complete" if complete else "partial",
            "composition": "not_attempted", "cross_tu": "not_attempted",
        }, identity_material="search",
    )
    # make_search owns the canonical search ID; bind both preconstructed branches to it.
    for branch in (root_branch, leaf):
        branch["search_id"] = search["search_id"]
    observation = make_branch_observation(
        leaf["branch_id"], "proof", "proof_passed" if positive else "proof_failed",
        quality_grade="A", proof_class="z3",
    )
    return {
        "grammar_version": "deep-v2", "roots": [root], "searches": [search],
        "branches": [root_branch, leaf], "observations": [observation],
    }


def _bundle(trace: dict) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        return build_search_training_bundle(
            trace["roots"], trace["searches"], trace["branches"], trace["observations"],
            project_identity="fixture", producer_agent="test", producer_model="test",
            producer_provider=None, submission_consent=False,
            identity_path=Path(directory) / "identity.json", grammar_version=trace["grammar_version"],
        )


def test_positive_terminal_propagates_to_every_ancestor() -> None:
    bundle = _bundle(_trace(positive=True, complete=True))
    by_depth = {branch["depth"]: branch for branch in bundle["branches"]}
    assert by_depth[1]["survival"]["class"] == "KEEP"
    assert by_depth[0]["survival"]["class"] == "KEEP"
    assert by_depth[0]["descendant_utility"]["proof_valid"] is True
    assert by_depth[0]["survival"]["positive_descendant_count"] == 1


def test_exhaustive_dead_subtree_is_prunable_but_baseline_is_guarded() -> None:
    bundle = _bundle(_trace(positive=False, complete=True))
    by_depth = {branch["depth"]: branch for branch in bundle["branches"]}
    assert by_depth[1]["survival"] == {
        "class": "PRUNE_HIGH_CONFIDENCE", "authority": "derived_complete_tree",
        "positive_descendant_count": 0, "label_version": "useful-descendant-v1",
    }
    assert by_depth[0]["survival"]["class"] == "KEEP"
    assert by_depth[0]["descendant_utility"]["useful"] is False


def test_truncated_negative_branch_fails_open() -> None:
    bundle = _bundle(_trace(positive=False, complete=False))
    leaf = max(bundle["branches"], key=lambda branch: branch["depth"])
    assert leaf["survival"]["class"] == "KEEP_UNCERTAIN"
    assert leaf["descendant_utility"]["useful"] is None


def test_sound_contract_closure_is_separate_from_empirical_negative() -> None:
    trace = _trace(positive=False, complete=False)
    leaf = trace["branches"][1]
    leaf.update({"state": "blocked", "evidence_coverage": "soundly_blocked"})
    leaf["coverage"] = {
        "children_status": "soundly_closed", "emitted_child_count": 0, "expected_child_count": 0,
        "completeness_reason": "sound_contract", "soundness_proof_class": "z3",
    }
    trace["observations"] = [make_branch_observation(
        leaf["branch_id"], "grammar_disposition", "missing_contract", proof_class="z3",
    )]
    bundle = _bundle(trace)
    result = max(bundle["branches"], key=lambda branch: branch["depth"])
    assert result["survival"]["class"] == "BLOCKED_BY_CONTRACT"
    assert result["survival"]["authority"] == "sound_contract"


def test_tampered_survival_label_and_lineage_fail_validation() -> None:
    bundle = _bundle(_trace(positive=True, complete=True))
    leaf = max(bundle["branches"], key=lambda branch: branch["depth"])
    leaf["survival"]["class"] = "PRUNE_HIGH_CONFIDENCE"
    assert any("noncanonical survival" in error for error in search_training_integrity_errors(bundle))
    leaf["parent_branch_id"] = "f" * 64
    assert any("invalid parent" in error for error in search_training_integrity_errors(bundle))


def test_authoritative_trace_writer_emits_valid_v3() -> None:
    trace = _trace(positive=True, complete=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "bundle.json"
        bundle = create_training_bundle_from_search_trace(
            trace, path, project_id="fixture", producer_agent="test", producer_model="test",
            identity_path=root / "identity.json",
        )
        assert bundle["schema_version"] == "vladder-model-training-bundle-v3"
        assert validate_training_bundle(path)["status"] == "pass"
        serialized = json.loads(path.read_text())
        assert serialized["privacy"]["search_lineage_included"] is True


def test_flat_prior_negative_is_not_promoted_to_pruning_authority() -> None:
    root = _root()
    hardware = {"architecture": "x86_64"}
    workload = {"phase": "other"}
    baseline = make_candidate(
        root["root_id"], {"family": "baseline", "family_version": "v1", "primitives": []},
        hardware, workload, baseline=True,
    )
    candidate = make_candidate(
        root["root_id"], {"family": "simd_mask", "family_version": "v1", "primitives": ["mask"]},
        hardware, workload,
    )
    observation = make_observation(
        candidate["candidate_id"], "proof", "proof_failed", {"proof_class": "z3"}, quality_grade="A",
    )
    with tempfile.TemporaryDirectory() as directory:
        root_path = Path(directory)
        store = PriorExperienceStore(root_path / "prior")
        store.append("roots", [root])
        store.append("candidates", [baseline, candidate])
        store.append("observations", [observation])
        bundle = create_training_bundle_from_prior(
            root_path / "prior", root_path / "bundle.json", project_id="fixture",
            producer_agent="test", producer_model="test", maximum_examples=2,
            identity_path=root_path / "identity.json",
        )
        alternative = next(branch for branch in bundle["branches"] if not branch["baseline"])
        assert alternative["survival"]["class"] == "KEEP_UNCERTAIN"
        assert alternative["descendant_utility"]["useful"] is None


def test_graph_export_contains_ancestor_actions_and_rejects_tampering() -> None:
    trace = _trace(positive=True, complete=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "bundle.json"
        create_training_bundle_from_search_trace(
            trace, path, project_id="fixture", producer_agent="test", producer_model="test",
            identity_path=root / "identity.json",
        )
        examples = graph_learning_examples(path)
        leaf = max(examples, key=lambda example: example["decision_context"]["branch"]["depth"])
        assert [item["stage"] for item in leaf["decision_context"]["branch"]["ancestor_action_path"]] == ["baseline", "candidate_family"]
        assert "observations" not in leaf["decision_context"]
        assert leaf["supervision"]["targets"]["survival"]["class"] == "KEEP"
        payload = json.loads(path.read_text())
        payload["branches"][1]["survival"]["class"] = "PRUNE_HIGH_CONFIDENCE"
        path.write_text(json.dumps(payload))
        try:
            graph_learning_examples(path)
        except ValueError as error:
            assert "lineage validation" in str(error)
        else:
            raise AssertionError("tampered survival labels must not enter GraphML examples")
