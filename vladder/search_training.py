from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any
import uuid

from . import __version__
from .language_adapter import canonical_hash
from .training_privacy import (
    load_or_create_training_identity,
    private_identity,
    sanitize_root,
    sanitize_training_action,
    sanitize_training_descriptor,
    search_privacy_manifest,
)


MODEL_TRAINING_SCHEMA_VERSION = "vladder-model-training-bundle-v3"
CANONICALIZER_VERSION = "search-pruner-graph-v3"
LABELER_VERSION = "useful-descendant-v1"
TARGET_DEFINITION = "proof-valid-or-stronger-v1"
UTILITY_KEYS = ("proof_valid", "distinct_realization", "physically_material", "retained", "promoted")

POSITIVE_OUTCOMES = {
    "proof_valid": {"proof_passed", "material_regional_win", "composed_win", "retained_candidate", "promoted_candidate"},
    "distinct_realization": {
        "distinct_realization", "measured_regression", "statistical_tie", "small_win_below_floor",
        "material_regional_win", "composed_regression", "composed_win", "resource_regression",
        "retained_candidate", "promoted_candidate",
    },
    "physically_material": {"material_regional_win", "composed_win", "retained_candidate", "promoted_candidate"},
    "retained": {"retained_candidate", "promoted_candidate", "composed_win"},
    "promoted": {"promoted_candidate"},
}
SOUND_REASONS = {"sound_contract", "sound_legality", "sound_dominance"}


def empty_utility() -> dict[str, bool]:
    return {key: False for key in UTILITY_KEYS}


def unknown_descendant_utility() -> dict[str, Any]:
    return {**{key: None for key in UTILITY_KEYS}, "useful": None, "target_definition": TARGET_DEFINITION}


def make_search(
    root_id: str,
    root_branch_id: str,
    hardware: dict[str, Any],
    workload: dict[str, Any],
    *,
    grammar_version: str,
    grammar_hash: str,
    selection_policy: str,
    coverage: str,
    stage_coverage: dict[str, str],
    fragment_kind: str = "full_trace",
    external_parent_branch_id: str | None = None,
    exploration_reserve_fraction: float = 0.0,
    identity_material: Any | None = None,
) -> dict[str, Any]:
    body = {
        "root_id": root_id,
        "root_branch_id": root_branch_id,
        "grammar_version": grammar_version,
        "grammar_hash": grammar_hash,
        "selection_policy": selection_policy,
        "coverage": coverage,
        "stage_coverage": stage_coverage,
        "fragment": {"kind": fragment_kind, "external_parent_branch_id": external_parent_branch_id},
        "exploration_reserve_fraction": exploration_reserve_fraction,
        "hardware": hardware,
        "workload": workload,
    }
    return {"search_id": canonical_hash(identity_material if identity_material is not None else body), **body}


def make_branch(
    search_id: str,
    action: dict[str, Any],
    *,
    parent_branch_id: str | None,
    depth: int,
    stage: str,
    baseline: bool = False,
    state: str = "enumerated",
    evidence_coverage: str = "none",
    coverage: dict[str, Any] | None = None,
    search_cost: dict[str, Any] | None = None,
    identity_material: Any | None = None,
) -> dict[str, Any]:
    default_coverage = {
        "children_status": "not_enumerated",
        "emitted_child_count": 0,
        "expected_child_count": None,
        "completeness_reason": "unknown",
        "soundness_proof_class": "none",
    }
    default_cost = {
        "node_expansions": None,
        "compiler_invocations": None,
        "proof_calls": None,
        "benchmark_runs": None,
        "elapsed_ms": None,
    }
    body = {
        "search_id": search_id,
        "parent_branch_id": parent_branch_id,
        "depth": depth,
        "stage": stage,
        "baseline": baseline,
        "action": action,
        "state": state,
        "evidence_coverage": evidence_coverage,
        "coverage": {**default_coverage, **(coverage or {})},
        "search_cost": {**default_cost, **(search_cost or {})},
    }
    branch_id = canonical_hash(identity_material if identity_material is not None else body)
    return {
        "branch_id": branch_id,
        **body,
        "direct_utility": empty_utility(),
        "descendant_utility": unknown_descendant_utility(),
        "survival": {
            "class": "KEEP_UNCERTAIN",
            "authority": "incomplete_tree",
            "positive_descendant_count": 0,
            "label_version": LABELER_VERSION,
        },
    }


def make_branch_observation(
    branch_id: str,
    kind: str,
    outcome: str,
    *,
    quality_grade: str = "D",
    proof_class: str = "none",
    benchmark_scope: str = "none",
    speedup_percent: float | None = None,
    ci_lower_percent: float | None = None,
    ci_upper_percent: float | None = None,
    sample_count: int = 0,
    resource_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "branch_id": branch_id,
        "kind": kind,
        "outcome": outcome,
        "quality_grade": quality_grade,
        "proof_class": proof_class,
        "benchmark_scope": benchmark_scope,
        "speedup_percent": speedup_percent,
        "ci_lower_percent": ci_lower_percent,
        "ci_upper_percent": ci_upper_percent,
        "sample_count": sample_count,
        "resource_features": resource_features or {"numeric": [], "categorical": []},
    }
    return {"observation_id": canonical_hash(body), **body}


def derive_survival_labels(
    searches: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recompute all utility and survival fields; producer-supplied labels are ignored."""
    result = [deepcopy(item) for item in branches]
    by_id = {item["branch_id"]: item for item in result}
    observations_by_branch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in observations:
        observations_by_branch[item["branch_id"]].append(item)
    children: dict[str, list[str]] = defaultdict(list)
    for branch in result:
        parent = branch["parent_branch_id"]
        if parent is not None:
            children[parent].append(branch["branch_id"])

    for branch in result:
        outcomes = {item["outcome"] for item in observations_by_branch.get(branch["branch_id"], [])}
        branch["direct_utility"] = {
            key: bool(outcomes & POSITIVE_OUTCOMES[key]) for key in UTILITY_KEYS
        }

    memo: dict[str, tuple[dict[str, bool | None], bool, int]] = {}

    def visit(branch_id: str) -> tuple[dict[str, bool | None], bool, int]:
        if branch_id in memo:
            return memo[branch_id]
        branch = by_id[branch_id]
        child_results = [visit(child_id) for child_id in children.get(branch_id, [])]
        complete = _subtree_is_complete(branch, child_results, len(children.get(branch_id, [])))
        values: dict[str, bool | None] = {}
        for key in UTILITY_KEYS:
            positive = branch["direct_utility"][key] or any(child[0][key] is True for child in child_results)
            values[key] = True if positive else False if complete else None
        direct_useful = bool(branch["direct_utility"]["proof_valid"] or branch["direct_utility"]["physically_material"] or branch["direct_utility"]["retained"] or branch["direct_utility"]["promoted"])
        positive_count = int(direct_useful) + sum(child[2] for child in child_results)
        useful: bool | None = True if positive_count else False if complete else None
        branch["descendant_utility"] = {**values, "useful": useful, "target_definition": TARGET_DEFINITION}
        sound_contract = _is_sound_contract_closure(branch)
        if branch["baseline"]:
            classification, authority = "KEEP", "baseline_guard"
        elif useful is True:
            classification, authority = "KEEP", "observed_positive_path"
        elif sound_contract:
            classification, authority = "BLOCKED_BY_CONTRACT", "sound_contract"
        elif complete:
            classification, authority = "PRUNE_HIGH_CONFIDENCE", "derived_complete_tree"
        else:
            classification, authority = "KEEP_UNCERTAIN", "incomplete_tree"
        branch["survival"] = {
            "class": classification,
            "authority": authority,
            "positive_descendant_count": positive_count,
            "label_version": LABELER_VERSION,
        }
        memo[branch_id] = (values, complete, positive_count)
        return memo[branch_id]

    for search in searches:
        visit(search["root_branch_id"])
    return result


def _subtree_is_complete(
    branch: dict[str, Any],
    child_results: list[tuple[dict[str, bool | None], bool, int]],
    actual_children: int,
) -> bool:
    coverage = branch["coverage"]
    if _is_sound_contract_closure(branch):
        return True
    if actual_children:
        expected = coverage["expected_child_count"]
        return (
            coverage["children_status"] == "exhaustive"
            and coverage["emitted_child_count"] == actual_children
            and expected == actual_children
            and all(item[1] for item in child_results)
        )
    return (
        coverage["children_status"] in {"not_applicable", "exhaustive"}
        and coverage["emitted_child_count"] == 0
        and coverage["expected_child_count"] in {None, 0}
        and branch["evidence_coverage"] in {"complete", "soundly_blocked"}
        and coverage["completeness_reason"] in {"terminal", "not_applicable", *SOUND_REASONS}
    )


def _is_sound_contract_closure(branch: dict[str, Any]) -> bool:
    coverage = branch["coverage"]
    return (
        branch["state"] in {"blocked", "pruned_sound"}
        and branch["evidence_coverage"] == "soundly_blocked"
        and coverage["children_status"] == "soundly_closed"
        and coverage["completeness_reason"] in SOUND_REASONS
        and coverage["soundness_proof_class"] not in {"", "none", "other"}
    )


def sanitize_search_trace(
    roots: list[dict[str, Any]],
    searches: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    *,
    project_identity: Any,
    identity_path: Path | None,
    submission_consent: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    identity = load_or_create_training_identity(identity_path)
    sanitized_roots = [sanitize_root(item, identity, project_identity=project_identity) for item in roots]
    root_ids = dict(zip((str(item["root_id"]) for item in roots), (item["root_id"] for item in sanitized_roots), strict=True))
    search_ids = {str(item["search_id"]): private_identity(identity, "search", item["search_id"]) for item in searches}
    branch_ids = {str(item["branch_id"]): private_identity(identity, "branch", item["branch_id"]) for item in branches}

    sanitized_searches = []
    for item in searches:
        external = item["fragment"].get("external_parent_branch_id")
        sanitized_searches.append({
            "search_id": search_ids[str(item["search_id"])],
            "root_id": root_ids[str(item["root_id"])],
            "root_branch_id": branch_ids[str(item["root_branch_id"])],
            "grammar_version": _token(item.get("grammar_version"), "unversioned"),
            "grammar_hash": str(item["grammar_hash"]),
            "selection_policy": item["selection_policy"],
            "coverage": item["coverage"],
            "stage_coverage": dict(item["stage_coverage"]),
            "fragment": {
                "kind": item["fragment"]["kind"],
                "external_parent_branch_id": private_identity(identity, "branch", external) if external is not None else None,
            },
            "exploration_reserve_fraction": float(item.get("exploration_reserve_fraction", 0.0)),
            "hardware": sanitize_training_descriptor(item.get("hardware", {}), kind="hardware"),
            "workload": sanitize_training_descriptor(item.get("workload", {}), kind="workload"),
        })

    sanitized_branches = []
    for item in branches:
        parent = item.get("parent_branch_id")
        sanitized_branches.append({
            "branch_id": branch_ids[str(item["branch_id"])],
            "search_id": search_ids[str(item["search_id"])],
            "parent_branch_id": branch_ids[str(parent)] if parent is not None else None,
            "depth": int(item["depth"]),
            "stage": item["stage"],
            "baseline": bool(item.get("baseline")),
            "action": sanitize_training_action(item.get("action", {})),
            "state": item["state"],
            "evidence_coverage": item["evidence_coverage"],
            "coverage": _sanitize_coverage(item.get("coverage", {})),
            "search_cost": _sanitize_search_cost(item.get("search_cost", {})),
            "direct_utility": empty_utility(),
            "descendant_utility": unknown_descendant_utility(),
            "survival": {"class": "KEEP_UNCERTAIN", "authority": "incomplete_tree", "positive_descendant_count": 0, "label_version": LABELER_VERSION},
        })

    sanitized_observations = []
    for item in observations:
        branch_id = branch_ids[str(item["branch_id"])]
        sanitized_observations.append(make_branch_observation(
            branch_id,
            str(item.get("kind", "grammar_disposition")),
            str(item.get("outcome", "proof_unknown")),
            quality_grade=str(item.get("quality_grade", "D")),
            proof_class=_token(item.get("proof_class"), "none"),
            benchmark_scope=str(item.get("benchmark_scope", "none")),
            speedup_percent=_finite(item.get("speedup_percent")),
            ci_lower_percent=_finite(item.get("ci_lower_percent")),
            ci_upper_percent=_finite(item.get("ci_upper_percent")),
            sample_count=max(0, int(item.get("sample_count", 0))),
            resource_features=(
                _sanitize_public_feature_set(item.get("resource_features"))
                if _is_public_feature_set(item.get("resource_features"))
                else sanitize_training_descriptor(item.get("resource_features", {}), kind="resource")
            ),
        ))
    sanitized_branches = derive_survival_labels(sanitized_searches, sanitized_branches, sanitized_observations)
    return sanitized_roots, sanitized_searches, sanitized_branches, sanitized_observations, search_privacy_manifest(identity, submission_consent=submission_consent)


def build_search_training_bundle(
    roots: list[dict[str, Any]],
    searches: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    *,
    project_identity: Any,
    producer_agent: str,
    producer_model: str,
    producer_provider: str | None,
    submission_consent: bool,
    identity_path: Path | None,
    grammar_version: str,
) -> dict[str, Any]:
    sanitized = sanitize_search_trace(
        roots, searches, branches, observations,
        project_identity=project_identity, identity_path=identity_path,
        submission_consent=submission_consent,
    )
    sanitized_roots, sanitized_searches, sanitized_branches, sanitized_observations, privacy = sanitized
    bundle = {
        "schema_version": MODEL_TRAINING_SCHEMA_VERSION,
        "bundle_id": f"bundle:{uuid.uuid4()}",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "vladder_version": __version__,
        "producer": {"agent": producer_agent, "model": producer_model, "provider": producer_provider},
        "dataset": {
            "grammar_version": grammar_version,
            "grammar_hash": canonical_hash([item["action"] for item in sanitized_branches]),
            "canonicalizer_version": CANONICALIZER_VERSION,
            "labeler_version": LABELER_VERSION,
            "target_definition": TARGET_DEFINITION,
            "identity_epoch": privacy["identity_epoch"],
        },
        "roots": sanitized_roots,
        "searches": sanitized_searches,
        "branches": sanitized_branches,
        "observations": sanitized_observations,
        "privacy": privacy,
    }
    errors = search_training_integrity_errors(bundle)
    if errors:
        raise ValueError("invalid search training bundle: " + "; ".join(errors))
    return bundle


def search_training_integrity_errors(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    roots = {item["root_id"]: item for item in bundle.get("roots", [])}
    searches = {item["search_id"]: item for item in bundle.get("searches", [])}
    branches = {item["branch_id"]: item for item in bundle.get("branches", [])}
    if len(roots) != len(bundle.get("roots", [])): errors.append("duplicate root_id")
    if len(searches) != len(bundle.get("searches", [])): errors.append("duplicate search_id")
    if len(branches) != len(bundle.get("branches", [])): errors.append("duplicate branch_id")
    children: dict[str, list[str]] = defaultdict(list)
    for search in searches.values():
        if search["root_id"] not in roots: errors.append(f"search {search['search_id']} references an unknown root")
        root_branch = branches.get(search["root_branch_id"])
        if root_branch is None or root_branch.get("search_id") != search["search_id"]:
            errors.append(f"search {search['search_id']} has an invalid root branch")
        elif root_branch.get("parent_branch_id") is not None or root_branch.get("depth") != 0 or not root_branch.get("baseline"):
            errors.append(f"search {search['search_id']} root branch must be baseline depth zero with no parent")
    for branch in branches.values():
        if branch["search_id"] not in searches: errors.append(f"branch {branch['branch_id']} references an unknown search")
        parent_id = branch["parent_branch_id"]
        if parent_id is not None:
            parent = branches.get(parent_id)
            if parent is None or parent["search_id"] != branch["search_id"]:
                errors.append(f"branch {branch['branch_id']} has an invalid parent")
            elif parent["depth"] + 1 != branch["depth"]:
                errors.append(f"branch {branch['branch_id']} depth does not follow its parent")
            else:
                children[parent_id].append(branch["branch_id"])
    for branch in branches.values():
        actual_children = len(children.get(branch["branch_id"], []))
        coverage = branch["coverage"]
        if coverage["emitted_child_count"] != actual_children:
            errors.append(f"branch {branch['branch_id']} emitted child count does not match local lineage")
        if coverage["children_status"] == "exhaustive" and coverage["expected_child_count"] != actual_children:
            errors.append(f"branch {branch['branch_id']} exhaustive child count is not complete")
    for observation in bundle.get("observations", []):
        if observation["branch_id"] not in branches:
            errors.append(f"observation {observation['observation_id']} references an unknown branch")
    if not errors:
        expected = derive_survival_labels(list(searches.values()), list(branches.values()), bundle.get("observations", []))
        expected_by_id = {item["branch_id"]: item for item in expected}
        for branch_id, branch in branches.items():
            for field in ("direct_utility", "descendant_utility", "survival"):
                if branch[field] != expected_by_id[branch_id][field]:
                    errors.append(f"branch {branch_id} has noncanonical {field}")
        for search in searches.values():
            reachable: set[str] = set()
            pending = [search["root_branch_id"]]
            while pending:
                branch_id = pending.pop()
                if branch_id in reachable:
                    continue
                reachable.add(branch_id)
                pending.extend(children.get(branch_id, []))
            owned = {branch_id for branch_id, branch in branches.items() if branch["search_id"] == search["search_id"]}
            if reachable != owned:
                errors.append(f"search {search['search_id']} contains disconnected branches")
            root = expected_by_id[search["root_branch_id"]]
            if search["coverage"] in {"complete", "soundly_pruned"} and root["descendant_utility"]["useful"] is None:
                errors.append(f"search {search['search_id']} claims complete coverage with unknown descendant utility")
            if search["fragment"]["kind"] == "full_trace" and search["fragment"]["external_parent_branch_id"] is not None:
                errors.append(f"search {search['search_id']} full trace cannot have an external parent")
    return errors


def _sanitize_coverage(value: dict[str, Any]) -> dict[str, Any]:
    expected = value.get("expected_child_count")
    return {
        "children_status": str(value.get("children_status", "not_enumerated")),
        "emitted_child_count": max(0, int(value.get("emitted_child_count", 0))),
        "expected_child_count": max(0, int(expected)) if isinstance(expected, int) else None,
        "completeness_reason": str(value.get("completeness_reason", "unknown")),
        "soundness_proof_class": _token(value.get("soundness_proof_class"), "none"),
    }


def _sanitize_search_cost(value: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in ("node_expansions", "compiler_invocations", "proof_calls", "benchmark_runs"):
        item = value.get(key)
        output[key] = max(0, int(item)) if isinstance(item, int) and not isinstance(item, bool) else None
    output["elapsed_ms"] = _nonnegative_finite(value.get("elapsed_ms"))
    return output


def _sanitize_public_feature_set(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"numeric": [], "categorical": []}
    numeric = [item for item in value.get("numeric", []) if isinstance(item, dict)][:128]
    categorical = [item for item in value.get("categorical", []) if isinstance(item, dict)][:128]
    return {"numeric": numeric, "categorical": categorical}


def _is_public_feature_set(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("numeric"), list) and isinstance(value.get("categorical"), list)


def _finite(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) else None


def _nonnegative_finite(value: Any) -> float | None:
    finite = _finite(value)
    return finite if finite is not None and finite >= 0 else None


def _token(value: Any, fallback: str) -> str:
    text = str(value or fallback)
    if not text or len(text) > 96 or not text[0].isalnum():
        return fallback
    return "".join(character if character.isalnum() or character in "_.:+/-" else "_" for character in text)
