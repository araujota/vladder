from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import tempfile
from typing import Any
from copy import deepcopy

from .consent import CANONICAL_TRAINING_DATA, require_consent
from .contribution_transport import (
    DEFAULT_MODEL_TRAINING_ENDPOINT,
    submit_validated_record,
)
from .language_adapter import canonical_hash
from .prior_data import PriorExperienceStore, make_candidate, make_observation, make_root
from .schema_registry import validate_artifact
from .training_privacy import (
    MAX_CANDIDATES_PER_BUNDLE,
    MAX_OBSERVATIONS_PER_BUNDLE,
    MAX_ROOTS_PER_BUNDLE,
)
from .search_training import (
    MODEL_TRAINING_SCHEMA_VERSION,
    build_search_training_bundle,
    make_branch,
    make_branch_observation,
    search_training_integrity_errors,
)


LEGACY_TRAINING_SCHEMA_VERSION = "vladder-training-bundle-v1"
HISTORICAL_MODEL_TRAINING_SCHEMA_VERSION = "vladder-model-training-bundle-v2"
TRAINING_OUTBOX_SCHEMA_VERSION = "vladder-training-outbox-v1"
SEARCH_TRACE_FRAGMENT_BRANCH_LIMIT = 16


def default_training_outbox_directory() -> Path:
    override = os.environ.get("VLADDER_TRAINING_OUTBOX_DIR")
    if override:
        return Path(override).expanduser()
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "vladder" / "training-outbox"


def _atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".training-outbox-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def enqueue_training_bundle(bundle_path: Path, *, outbox_directory: Path | None = None) -> dict[str, Any]:
    """Durably retain a validated source-free bundle before any network attempt."""
    validation = validate_training_bundle(bundle_path)
    if validation["status"] != "pass":
        raise ValueError(f"training bundle schema validation failed: {validation['errors']}")
    schema_version = json.loads(bundle_path.resolve().read_text()).get("schema_version")
    if schema_version != MODEL_TRAINING_SCHEMA_VERSION:
        raise ValueError(
            f"training emission requires {MODEL_TRAINING_SCHEMA_VERSION}; historical v1/v2 records are validation-only"
        )
    payload = bundle_path.resolve().read_bytes()
    payload_hash = hashlib.sha256(payload).hexdigest()
    root = (outbox_directory or default_training_outbox_directory()).expanduser().resolve()
    entry_path = root / f"{payload_hash}.json"
    if not entry_path.exists():
        _atomic_private_json(entry_path, json.loads(payload))
    elif stat.S_IMODE(entry_path.stat().st_mode) & 0o077:
        raise PermissionError(f"training outbox entry must be owner-only: {entry_path}")
    return {
        "schema_version": TRAINING_OUTBOX_SCHEMA_VERSION,
        "payload_sha256": payload_hash,
        "entry": str(entry_path),
        "queued": True,
    }


def flush_training_outbox(
    *,
    outbox_directory: Path | None = None,
    endpoint: str | None = None,
    token: str | None = None,
    timeout_seconds: float = 20.0,
    consent_path: Path | None = None,
) -> dict[str, Any]:
    """Submit queued records in order, retaining every unacknowledged entry for a later run."""
    require_consent(CANONICAL_TRAINING_DATA, consent_path)
    root = (outbox_directory or default_training_outbox_directory()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    pending = sorted(root.glob("*.json"), key=lambda path: (path.stat().st_mtime_ns, path.name))
    submissions: list[dict[str, Any]] = []
    quarantined: list[str] = []
    failure: str | None = None
    for entry in pending:
        if stat.S_IMODE(entry.stat().st_mode) & 0o077:
            failure = f"training outbox entry must be owner-only: {entry}"
            break
        payload = json.loads(entry.read_text())
        if payload.get("schema_version") in {LEGACY_TRAINING_SCHEMA_VERSION, HISTORICAL_MODEL_TRAINING_SCHEMA_VERSION}:
            version = "v1" if payload.get("schema_version") == LEGACY_TRAINING_SCHEMA_VERSION else "v2"
            quarantine = root / f"legacy-{version}-quarantine"
            quarantine.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(quarantine, 0o700)
            destination = quarantine / entry.name
            entry.replace(destination)
            os.chmod(destination, 0o600)
            quarantined.append(str(destination))
            continue
        validation = validate_training_bundle(entry)
        if validation["status"] != "pass":
            failure = f"queued training bundle failed schema validation: {entry}"
            break
        try:
            submission = submit_training_bundle(
                entry,
                endpoint=endpoint,
                token=token,
                confirm_upload=True,
                timeout_seconds=timeout_seconds,
                consent_path=consent_path,
            )
        except Exception as error:  # A retained record is safer than losing a transient transport failure.
            failure = str(error)
            break
        submissions.append({"entry": str(entry), "submission": submission})
        entry.unlink()
    remaining = len(list(root.glob("*.json")))
    return {
        "schema_version": "vladder-training-outbox-flush-v1",
        "status": "pass" if failure is None else "queued_for_retry",
        "submitted_count": len(submissions),
        "pending_count": remaining,
        "submissions": submissions,
        "quarantined_legacy_count": len(quarantined),
        "quarantined_legacy_entries": quarantined,
        "retryable_error": failure,
        "outbox": str(root),
    }


def create_training_template(output_path: Path) -> dict[str, Any]:
    graph = _workflow_evidence_graph({
        "workflow_kind": "other",
        "states": {"workflow_completed": True},
        "proof_class": "none",
    })
    root = make_root(
        graph,
        {"bounded": True, "exactness": "other", "semantic_family": "other"},
        [{"source_language": "other"}],
        project_id="model-training-template",
        graph_version="workflow-evidence-flow-v2",
    )
    baseline = make_candidate(
        root["root_id"],
        {"family": "baseline", "family_version": "v1", "primitives": ["existing_implementation"]},
        {"architecture": "other", "device_class": "cpu"},
        {"phase": "other"},
        baseline=True,
    )
    observation = make_observation(
        baseline["candidate_id"], "grammar_disposition", "proof_unknown",
        {"proof_class": "none", "benchmark_scope": "none"}, quality_grade="D",
    )
    return _write_model_training_bundle(
        [root], [baseline], [observation], output_path,
        project_identity="model-training-template", producer_agent="TODO", producer_model="TODO",
        submission_consent=False,
    )


def validate_training_bundle(bundle_path: Path) -> dict[str, Any]:
    try:
        schema_version = json.loads(bundle_path.resolve().read_text()).get("schema_version")
    except (json.JSONDecodeError, AttributeError):
        schema_version = None
    kind = (
        "model-training-bundle" if schema_version == MODEL_TRAINING_SCHEMA_VERSION else
        "model-training-bundle-v2" if schema_version == HISTORICAL_MODEL_TRAINING_SCHEMA_VERSION else
        "training-bundle"
    )
    report = validate_artifact(kind, bundle_path)
    if report["status"] == "pass" and schema_version == MODEL_TRAINING_SCHEMA_VERSION:
        payload = json.loads(bundle_path.resolve().read_text())
        integrity_errors = search_training_integrity_errors(payload)
        if integrity_errors:
            report["status"] = "fail"
            report["errors"].extend({"path": "/", "message": error, "validator": "link_integrity"} for error in integrity_errors)
    return report


def _model_training_integrity_errors(bundle: dict[str, Any]) -> list[str]:
    """Historical v2 integrity checker retained for local artifact inspection."""
    errors: list[str] = []
    root_ids = [item["root_id"] for item in bundle["roots"]]
    candidate_ids = [item["candidate_id"] for item in bundle["candidates"]]
    if len(root_ids) != len(set(root_ids)):
        errors.append("duplicate root_id")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("duplicate candidate_id")
    root_set = set(root_ids); candidate_set = set(candidate_ids)
    for root in bundle["roots"]:
        node_ids = [item["index"] for item in root["graph"]["nodes"]]
        if node_ids != list(range(len(node_ids))):
            errors.append(f"root {root['root_id']} node indices must be contiguous from zero")
        known = set(node_ids)
        if any(edge["source"] not in known or edge["destination"] not in known for edge in root["graph"]["edges"]):
            errors.append(f"root {root['root_id']} has an edge referencing an unknown node")
    for candidate in bundle["candidates"]:
        if candidate["root_id"] not in root_set:
            errors.append(f"candidate {candidate['candidate_id']} references an unknown root")
    for observation in bundle["observations"]:
        if observation["candidate_id"] not in candidate_set:
            errors.append(f"observation {observation['observation_id']} references an unknown candidate")
    if bundle["dataset"]["identity_epoch"] != bundle["privacy"]["identity_epoch"]:
        errors.append("dataset/privacy identity epoch mismatch")
    return errors


def _write_model_training_bundle(
    roots: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    output_path: Path,
    *,
    project_identity: Any,
    producer_agent: str,
    producer_model: str,
    producer_provider: str | None = None,
    submission_consent: bool,
    identity_path: Path | None = None,
    grammar_version: str = "structured-open-actions-v2",
) -> dict[str, Any]:
    if not roots or len(roots) > MAX_ROOTS_PER_BUNDLE:
        raise ValueError(f"model bundle requires 1 to {MAX_ROOTS_PER_BUNDLE} roots")
    if not candidates or len(candidates) > MAX_CANDIDATES_PER_BUNDLE:
        raise ValueError(f"model bundle requires 1 to {MAX_CANDIDATES_PER_BUNDLE} candidates")
    if len(observations) > MAX_OBSERVATIONS_PER_BUNDLE:
        raise ValueError(f"model bundle permits at most {MAX_OBSERVATIONS_PER_BUNDLE} observations")
    searches, branches, branch_observations = _flat_candidates_to_partial_searches(
        roots, candidates, observations, grammar_version=grammar_version,
    )
    bundle = build_search_training_bundle(
        roots, searches, branches, branch_observations,
        project_identity=project_identity, producer_agent=producer_agent,
        producer_model=producer_model, producer_provider=producer_provider,
        submission_consent=submission_consent, identity_path=identity_path,
        grammar_version=grammar_version,
    )
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    validation = validate_training_bundle(output_path)
    if validation["status"] != "pass":
        raise ValueError(f"model training bundle failed schema validation: {validation['errors']}")
    return bundle


def create_training_bundle_from_search_trace(
    trace: dict[str, Any], output_path: Path, *, project_id: str,
    producer_agent: str, producer_model: str, producer_provider: str | None = None,
    apply_durable_consent: bool = False, consent_path: Path | None = None,
    identity_path: Path | None = None,
) -> dict[str, Any]:
    """Emit an authoritative v3 trace without flattening branch lineage."""
    if apply_durable_consent:
        require_consent(CANONICAL_TRAINING_DATA, consent_path)
    required = ("roots", "searches", "branches", "observations")
    missing = [key for key in required if not isinstance(trace.get(key), list)]
    if missing:
        raise ValueError(f"search trace is missing list fields: {missing}")
    bundle = build_search_training_bundle(
        trace["roots"], trace["searches"], trace["branches"], trace["observations"],
        project_identity=project_id, producer_agent=producer_agent, producer_model=producer_model,
        producer_provider=producer_provider, submission_consent=apply_durable_consent,
        identity_path=identity_path, grammar_version=str(trace.get("grammar_version", "structured-open-actions-v3")),
    )
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    validation = validate_training_bundle(output_path)
    if validation["status"] != "pass":
        raise ValueError(f"search training bundle failed schema validation: {validation['errors']}")
    return bundle


def create_training_bundles_from_search_trace(
    trace: dict[str, Any], output_path: Path, *, project_id: str,
    producer_agent: str, producer_model: str, producer_provider: str | None = None,
    apply_durable_consent: bool = False, consent_path: Path | None = None,
    identity_path: Path | None = None,
    maximum_branches: int = SEARCH_TRACE_FRAGMENT_BRANCH_LIMIT,
) -> tuple[tuple[dict[str, Any], Path], ...]:
    """Emit one or more independently valid v3 packets for a complete search trace."""
    if maximum_branches < 1 or maximum_branches > 1024:
        raise ValueError("maximum_branches must be between 1 and 1024")
    fragments = _fragment_search_trace(trace, maximum_branches=maximum_branches)
    if len(fragments) == 1:
        paths = (output_path.resolve(),)
    else:
        directory = output_path.resolve().with_suffix(".fragments")
        paths = tuple(directory / f"part-{index:05d}.json" for index in range(len(fragments)))
    emitted = []
    for fragment, path in zip(fragments, paths, strict=True):
        bundle = create_training_bundle_from_search_trace(
            fragment,
            path,
            project_id=project_id,
            producer_agent=producer_agent,
            producer_model=producer_model,
            producer_provider=producer_provider,
            apply_durable_consent=apply_durable_consent,
            consent_path=consent_path,
            identity_path=identity_path,
        )
        emitted.append((bundle, path))
    return tuple(emitted)


def _fragment_search_trace(
    trace: dict[str, Any], *, maximum_branches: int,
) -> tuple[dict[str, Any], ...]:
    required = ("roots", "searches", "branches", "observations")
    if any(not isinstance(trace.get(key), list) for key in required):
        raise ValueError("search trace cannot be fragmented without roots, searches, branches, and observations")
    if len(trace["branches"]) <= maximum_branches:
        return (trace,)
    roots = {str(item["root_id"]): item for item in trace["roots"]}
    observations_by_branch: dict[str, list[dict[str, Any]]] = {}
    for observation in trace["observations"]:
        observations_by_branch.setdefault(str(observation["branch_id"]), []).append(observation)
    fragments: list[dict[str, Any]] = []
    for search in trace["searches"]:
        search_id = str(search["search_id"])
        selected = [item for item in trace["branches"] if str(item["search_id"]) == search_id]
        by_id = {str(item["branch_id"]): item for item in selected}
        children: dict[str, list[str]] = {branch_id: [] for branch_id in by_id}
        for branch in selected:
            parent = branch.get("parent_branch_id")
            if parent is not None and str(parent) in children:
                children[str(parent)].append(str(branch["branch_id"]))
        for values in children.values():
            values.sort()
        sizes: dict[str, int] = {}

        def subtree_size(branch_id: str) -> int:
            if branch_id not in sizes:
                sizes[branch_id] = 1 + sum(subtree_size(child) for child in children[branch_id])
            return sizes[branch_id]

        frontier: list[str] = []

        def select_frontier(branch_id: str) -> None:
            if subtree_size(branch_id) <= maximum_branches:
                frontier.append(branch_id)
                return
            for child in children[branch_id]:
                select_frontier(child)

        root_branch_id = str(search["root_branch_id"])
        select_frontier(root_branch_id)
        component_nodes: set[str] = set()
        for frontier_root in frontier:
            pending = [frontier_root]
            while pending:
                current = pending.pop()
                if current in component_nodes:
                    continue
                component_nodes.add(current)
                pending.extend(children[current])
            fragments.append(_search_trace_fragment(
                trace,
                roots[str(search["root_id"])],
                search,
                by_id,
                children,
                observations_by_branch,
                component_nodes=_subtree_ids(frontier_root, children),
                fragment_root=frontier_root,
                kind="full_trace" if frontier_root == root_branch_id else "complete_subtree",
                external_parent=by_id[frontier_root].get("parent_branch_id"),
            ))
        spine = set(by_id) - component_nodes
        if spine:
            if len(spine) <= maximum_branches:
                fragments.append(_search_trace_fragment(
                    trace, roots[str(search["root_id"])], search, by_id, children,
                    observations_by_branch, component_nodes=spine,
                    fragment_root=root_branch_id, kind="partial_snapshot", external_parent=None,
                ))
            else:
                for branch_id in sorted(spine):
                    fragments.append(_search_trace_fragment(
                        trace, roots[str(search["root_id"])], search, by_id, children,
                        observations_by_branch, component_nodes={branch_id},
                        fragment_root=branch_id, kind="partial_snapshot",
                        external_parent=by_id[branch_id].get("parent_branch_id"),
                    ))
    return tuple(fragments)


def _subtree_ids(root: str, children: dict[str, list[str]]) -> set[str]:
    result: set[str] = set()
    pending = [root]
    while pending:
        current = pending.pop()
        if current in result:
            continue
        result.add(current)
        pending.extend(children[current])
    return result


def _search_trace_fragment(
    trace: dict[str, Any],
    root: dict[str, Any],
    search: dict[str, Any],
    branches: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
    observations_by_branch: dict[str, list[dict[str, Any]]],
    *,
    component_nodes: set[str],
    fragment_root: str,
    kind: str,
    external_parent: Any,
) -> dict[str, Any]:
    selected = []
    for branch_id in sorted(component_nodes, key=lambda value: (int(branches[value]["depth"]), value)):
        branch = deepcopy(branches[branch_id])
        local_children = [child for child in children[branch_id] if child in component_nodes]
        if branch_id == fragment_root:
            branch["parent_branch_id"] = None
        if len(local_children) != len(children[branch_id]):
            branch["evidence_coverage"] = "partial"
            branch["coverage"] = {
                **branch["coverage"],
                "children_status": "partially_enumerated",
                "emitted_child_count": len(local_children),
                "expected_child_count": None,
                "completeness_reason": "interrupted",
                "soundness_proof_class": "none",
            }
        selected.append(branch)
    fragment_search = deepcopy(search)
    fragment_search["root_branch_id"] = fragment_root
    fragment_search["fragment"] = {
        "kind": kind,
        "external_parent_branch_id": external_parent,
    }
    if kind == "partial_snapshot":
        fragment_search["coverage"] = "partial"
        fragment_search["stage_coverage"] = {
            key: "partial" if value == "complete" else value
            for key, value in fragment_search["stage_coverage"].items()
        }
    observations = [
        deepcopy(observation)
        for branch_id in component_nodes
        for observation in observations_by_branch.get(branch_id, ())
    ]
    return {
        "grammar_version": trace.get("grammar_version", "structured-open-actions-v3"),
        "roots": [deepcopy(root)],
        "searches": [fragment_search],
        "branches": selected,
        "observations": observations,
    }


def _flat_candidates_to_partial_searches(
    roots: list[dict[str, Any]], candidates: list[dict[str, Any]], observations: list[dict[str, Any]],
    *, grammar_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates_by_root: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        candidates_by_root.setdefault(str(candidate["root_id"]), []).append(candidate)
    observations_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        observations_by_candidate.setdefault(str(observation["candidate_id"]), []).append(observation)
    searches: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    branch_observations: list[dict[str, Any]] = []
    for root in roots:
        root_id = str(root["root_id"])
        selected = candidates_by_root.get(root_id, [])
        baseline_candidate = next((item for item in selected if item.get("baseline")), None)
        if baseline_candidate is None:
            baseline_candidate = make_candidate(
                root_id,
                {"family": "baseline", "family_version": "v1", "primitives": ["existing_implementation"]},
                selected[0].get("hardware", {}) if selected else {}, selected[0].get("workload", {}) if selected else {},
                baseline=True,
            )
        alternatives = [item for item in selected if not item.get("baseline")]
        search_id = canonical_hash({
            "root_id": root_id, "grammar_version": grammar_version,
            "hardware": baseline_candidate.get("hardware", {}), "workload": baseline_candidate.get("workload", {}),
            "candidate_ids": sorted(str(item["candidate_id"]) for item in alternatives), "flat_import": True,
        })
        baseline_branch = make_branch(
            search_id, baseline_candidate["action"], parent_branch_id=None, depth=0, stage="baseline",
            baseline=True, state="expanded", evidence_coverage="partial",
            coverage={
                "children_status": "partially_enumerated" if alternatives else "not_enumerated",
                "emitted_child_count": len(alternatives), "expected_child_count": None,
                "completeness_reason": "unknown", "soundness_proof_class": "none",
            }, identity_material={"candidate_id": baseline_candidate["candidate_id"], "search_id": search_id},
        )
        searches.append({
            "search_id": search_id, "root_id": root_id, "root_branch_id": baseline_branch["branch_id"],
            "grammar_version": grammar_version, "grammar_hash": canonical_hash([item["action"] for item in selected]),
            "selection_policy": "terminal_workflow_import" if grammar_version.startswith("terminal-") else "flat_prior_import",
            "coverage": "partial",
            "stage_coverage": {"grammar_family": "partial", "candidate_family": "partial", "composition": "not_attempted", "cross_tu": "not_attempted"},
            "fragment": {"kind": "partial_snapshot", "external_parent_branch_id": None},
            "exploration_reserve_fraction": 0.0,
            "hardware": baseline_candidate.get("hardware", {}), "workload": baseline_candidate.get("workload", {}),
        })
        branches.append(baseline_branch)
        branch_observations.extend(
            _convert_flat_observation(item, baseline_branch["branch_id"])
            for item in observations_by_candidate.get(str(baseline_candidate["candidate_id"]), [])
        )
        terminal_import = grammar_version.startswith("terminal-")
        for candidate in alternatives:
            candidate_observations = observations_by_candidate.get(str(candidate["candidate_id"]), [])
            observed_coverage = _flat_evidence_coverage(candidate_observations)
            # A flat prior record says what happened to one realization, not whether every
            # descendant below that grammar choice was explored. Preserve positives, but keep
            # negative descendant utility unknown unless the source is an explicit terminal
            # workflow summary.
            evidence_coverage = observed_coverage if terminal_import else "partial" if candidate_observations else "none"
            branch = make_branch(
                search_id, candidate["action"], parent_branch_id=baseline_branch["branch_id"], depth=1,
                stage="candidate_family", state=_flat_branch_state(candidate_observations),
                evidence_coverage=evidence_coverage,
                coverage={
                    "children_status": "not_applicable" if terminal_import else "not_enumerated",
                    "emitted_child_count": 0,
                    "expected_child_count": 0 if terminal_import else None,
                    "completeness_reason": "terminal" if terminal_import and evidence_coverage == "complete" else "unknown",
                    "soundness_proof_class": "none",
                }, identity_material={"candidate_id": candidate["candidate_id"], "search_id": search_id},
            )
            branches.append(branch)
            branch_observations.extend(
                _convert_flat_observation(item, branch["branch_id"]) for item in candidate_observations
            )
    return searches, branches, branch_observations


def _flat_evidence_coverage(observations: list[dict[str, Any]]) -> str:
    outcomes = {str(item.get("outcome")) for item in observations}
    definitive = {
        "inapplicable", "missing_contract", "semantic_mismatch", "illegal", "proof_failed", "proof_passed",
        "compiler_identical", "measured_regression", "statistical_tie", "small_win_below_floor",
        "material_regional_win", "composed_regression", "composed_win", "resource_regression",
    }
    return "complete" if outcomes & definitive else "partial" if observations else "none"


def _flat_branch_state(observations: list[dict[str, Any]]) -> str:
    outcomes = {str(item.get("outcome")) for item in observations}
    if "compiler_identical" in outcomes:
        return "compiler_identical"
    if outcomes & {"inapplicable", "missing_contract", "semantic_mismatch", "illegal", "proof_failed"}:
        return "terminal"
    return "terminal" if _flat_evidence_coverage(observations) == "complete" else "enumerated"


def _convert_flat_observation(observation: dict[str, Any], branch_id: str) -> dict[str, Any]:
    payload = observation.get("payload", {}) if isinstance(observation.get("payload"), dict) else {}
    paired = payload.get("paired_speedup", {}) if isinstance(payload.get("paired_speedup"), dict) else {}
    def percent(value: Any) -> float | None:
        return float(value) * 100.0 if isinstance(value, (int, float)) else None
    return make_branch_observation(
        branch_id, str(observation.get("kind", "grammar_disposition")), str(observation.get("outcome", "proof_unknown")),
        quality_grade=str(observation.get("quality_grade", "D")),
        proof_class=str(payload.get("proof_class", payload.get("method", "none"))),
        benchmark_scope=str(payload.get("benchmark_scope", "none")),
        speedup_percent=percent(paired.get("median", payload.get("speedup"))),
        ci_lower_percent=percent(paired.get("bootstrap_ci_low")),
        ci_upper_percent=percent(paired.get("bootstrap_ci_high")),
        sample_count=max(0, int(payload.get("sample_count", payload.get("process_count", 0)) or 0)),
        resource_features=payload.get("resources", {}),
    )


def create_training_bundle_from_prior(
    store_path: Path,
    output_path: Path,
    *,
    project_id: str,
    producer_agent: str,
    producer_model: str,
    producer_provider: str | None = None,
    maximum_examples: int = 8,
    apply_durable_consent: bool = False,
    consent_path: Path | None = None,
    candidate_offset: int = 0,
    identity_path: Path | None = None,
) -> dict[str, Any]:
    if maximum_examples < 1 or maximum_examples > MAX_CANDIDATES_PER_BUNDLE:
        raise ValueError(f"maximum_examples must be between 1 and {MAX_CANDIDATES_PER_BUNDLE}")
    if apply_durable_consent:
        require_consent(CANONICAL_TRAINING_DATA, consent_path)
    dataset = PriorExperienceStore(store_path).load()
    roots = {item["root_id"]: item for item in dataset["roots"]}
    all_candidates = sorted(dataset["candidates"], key=lambda item: (item["root_id"], item["candidate_id"]))
    candidates = all_candidates[candidate_offset:candidate_offset + maximum_examples]
    if not candidates:
        raise ValueError("the prior store contains no candidate examples")
    selected_root_ids = sorted({str(item["root_id"]) for item in candidates})
    if len(selected_root_ids) > MAX_ROOTS_PER_BUNDLE:
        raise ValueError(
            f"candidate slice spans {len(selected_root_ids)} roots; model bundles permit {MAX_ROOTS_PER_BUNDLE}"
        )
    selected_candidate_ids = {str(item["candidate_id"]) for item in candidates}
    selected_observations = [
        item for item in dataset["observations"] if str(item.get("candidate_id")) in selected_candidate_ids
    ]
    if len(selected_observations) > MAX_OBSERVATIONS_PER_BUNDLE:
        raise ValueError(
            f"candidate slice has {len(selected_observations)} observations; model bundles permit "
            f"{MAX_OBSERVATIONS_PER_BUNDLE}; reduce the candidate slice"
        )
    return _write_model_training_bundle(
        [roots[root_id] for root_id in selected_root_ids], candidates, selected_observations, output_path,
        project_identity=project_id, producer_agent=producer_agent, producer_model=producer_model,
        producer_provider=producer_provider, submission_consent=apply_durable_consent,
        identity_path=identity_path, grammar_version="structured-open-actions-v3",
    )


def export_all_training_bundles_from_prior(
    store_path: Path,
    output_directory: Path,
    *,
    project_id: str,
    producer_agent: str,
    producer_model: str,
    producer_provider: str | None = None,
    examples_per_bundle: int = 12,
    apply_durable_consent: bool = False,
    consent_path: Path | None = None,
) -> dict[str, Any]:
    if examples_per_bundle < 1 or examples_per_bundle > 64:
        raise ValueError("examples_per_bundle must be between 1 and 64")
    dataset = PriorExperienceStore(store_path).load()
    candidate_count = len(dataset["candidates"])
    if not candidate_count:
        raise ValueError("the prior store contains no candidates")
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    ordered = sorted(dataset["candidates"], key=lambda item: (item["root_id"], item["candidate_id"]))
    observation_counts: dict[str, int] = {}
    for item in dataset["observations"]:
        candidate_id = str(item.get("candidate_id"))
        observation_counts[candidate_id] = observation_counts.get(candidate_id, 0) + 1
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < candidate_count:
        roots: set[str] = set()
        observation_count = 0
        end = start
        while end < candidate_count and end - start < examples_per_bundle:
            candidate = ordered[end]
            next_roots = roots | {str(candidate["root_id"])}
            next_observations = observation_count + observation_counts.get(str(candidate["candidate_id"]), 0)
            if end > start and (
                len(next_roots) > MAX_ROOTS_PER_BUNDLE
                or next_observations > MAX_OBSERVATIONS_PER_BUNDLE
            ):
                break
            roots = next_roots
            observation_count = next_observations
            end += 1
        if end == start:
            end += 1
        chunks.append((start, end - start))
        start = end
    paths = []
    for bundle_index, (offset, count) in enumerate(chunks):
        path = output_directory / f"training-bundle-{bundle_index:04d}.json"
        create_training_bundle_from_prior(
            store_path, path, project_id=project_id,
            producer_agent=producer_agent, producer_model=producer_model,
            producer_provider=producer_provider, maximum_examples=count,
            apply_durable_consent=apply_durable_consent, consent_path=consent_path,
            candidate_offset=offset,
        )
        paths.append(str(path))
    search_branch_count = sum(len(json.loads(Path(path).read_text())["branches"]) for path in paths)
    observation_kinds = sorted({str(item.get("kind")) for item in dataset["observations"]})
    report = {
        "schema_version": "vladder-training-export-v1",
        "status": "pass",
        "candidate_count": candidate_count,
        "search_branch_count": search_branch_count,
        "bundle_count": len(paths),
        "all_supported_candidates_exported": True,
        "bundles": paths,
        "total_bytes": sum(Path(path).stat().st_size for path in paths),
        "record_forms": {
            "bounded_semantic_graph_topology": True,
            "structured_grammar_actions": True,
            "search_lineage": True,
            "candidate_and_negative_dispositions": True,
            "negative_label_authority": "partial flat imports remain KEEP_UNCERTAIN",
            "observation_kinds": observation_kinds,
            "hardware_and_workload_descriptors": True,
        },
        "export_gaps": [],
        "privacy": (
            "pseudonymized structural data: normalized topology is included; source identifiers, literals, "
            "and raw local prior records are excluded"
        ),
    }
    (output_directory / "training-export.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def sync_all_training_bundles_from_prior(
    store_path: Path,
    output_directory: Path,
    *,
    project_id: str,
    producer_agent: str,
    producer_model: str,
    producer_provider: str | None = None,
    examples_per_bundle: int = 12,
    endpoint: str | None = None,
    token: str | None = None,
    validate_only: bool = False,
    timeout_seconds: float = 20.0,
    consent_path: Path | None = None,
) -> dict[str, Any]:
    require_consent(CANONICAL_TRAINING_DATA, consent_path)
    exported = export_all_training_bundles_from_prior(
        store_path, output_directory, project_id=project_id,
        producer_agent=producer_agent, producer_model=producer_model,
        producer_provider=producer_provider, examples_per_bundle=examples_per_bundle,
        apply_durable_consent=True, consent_path=consent_path,
    )
    submissions = [
        submit_training_bundle(
            Path(path), endpoint=endpoint, token=token, confirm_upload=True,
            validate_only=validate_only, timeout_seconds=timeout_seconds, consent_path=consent_path,
        )
        for path in exported["bundles"]
    ]
    report = {
        "schema_version": "vladder-training-sync-v1",
        "status": "pass",
        "continuous_opt_in_applied": True,
        "export": exported,
        "submissions": submissions,
    }
    (output_directory.resolve() / "training-sync.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _training_language(value: Any) -> str:
    language = str(value or "other").lower()
    return language if language in {"c", "cpp", "rust", "zig", "julia", "cuda", "spirv"} else "other"


def _safe_action_token(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    if not text or len(text) > 80:
        return fallback
    cleaned = "".join(character if character.isalnum() or character in "_.:+/-" else "_" for character in text)
    return cleaned if cleaned and cleaned[0].isalnum() else fallback


def _training_graph(report: dict[str, Any] | None, summary: dict[str, Any]) -> tuple[dict[str, Any], str]:
    captured = _find_bounded_graph(report or {})
    if captured is not None:
        return _normalize_training_graph(captured), str(captured.get("schema_version", "semantic-flow-v2"))[:64]
    return _workflow_evidence_graph(summary), "workflow-evidence-flow-v2"


def _find_bounded_graph(value: Any, *, depth: int = 0) -> dict[str, Any] | None:
    if depth > 8:
        return None
    if isinstance(value, dict):
        nodes = value.get("nodes")
        edges = value.get("edges")
        if isinstance(nodes, list) and nodes and isinstance(edges, list):
            return value
        priority = ("semantic_graph", "operator_graph", "lifetime_graph", "kernel_graph", "graph")
        for key in priority:
            if key in value:
                found = _find_bounded_graph(value[key], depth=depth + 1)
                if found is not None:
                    return found
        for key, child in value.items():
            if key in priority or key in {"source", "source_text", "assembly", "llvm_ir", "prompt"}:
                continue
            found = _find_bounded_graph(child, depth=depth + 1)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value[:128]:
            found = _find_bounded_graph(child, depth=depth + 1)
            if found is not None:
                return found
    return None


def _normalize_training_graph(graph: dict[str, Any]) -> dict[str, Any]:
    source_nodes = [item for item in graph.get("nodes", []) if isinstance(item, dict)][:512]
    identifiers = [str(item.get("id", item.get("index", f"node:{index}"))) for index, item in enumerate(source_nodes)]
    if len(set(identifiers)) != len(identifiers):
        identifiers = [f"node:{index}" for index in range(len(source_nodes))]
    remap = {identifier: f"node:{index}" for index, identifier in enumerate(identifiers)}
    nodes = [{**item, "id": remap[identifiers[index]]} for index, item in enumerate(source_nodes)]
    edges = []
    for item in graph.get("edges", []):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", item.get("src", "")))
        destination = str(item.get("destination", item.get("dst", "")))
        if source in remap and destination in remap:
            edges.append({**item, "source": remap[source], "destination": remap[destination]})
        if len(edges) >= 2048:
            break
    return {
        "schema_version": str(graph.get("schema_version", "semantic-flow-v2")),
        "nodes": nodes,
        "edges": edges,
        "obligations": [item for item in graph.get("obligations", []) if isinstance(item, dict)][:128],
        "effects": [item for item in graph.get("effects", []) if isinstance(item, dict)][:128],
        "protocols": [item for item in graph.get("protocols", []) if isinstance(item, dict)][:64],
        "claims": [item for item in graph.get("claims", []) if isinstance(item, dict)][:128],
        "contracts": graph.get("contracts", {}) if isinstance(graph.get("contracts"), dict) else {},
    }


def _workflow_evidence_graph(summary: dict[str, Any]) -> dict[str, Any]:
    states = summary.get("states", {}) if isinstance(summary.get("states"), dict) else {}
    stages = (
        ("source", "input", True, "local"),
        ("semantic_capture", "map", states.get("meaningful_semantic_coverage", False), "local"),
        ("candidate", "dispatch", states.get("candidate_generated", False), "local"),
        ("proof", "guard", states.get("candidate_proved", False), "local"),
        ("benchmark", "reduce", states.get("physically_benchmarked", False), "regional"),
        ("integration", "publish", states.get("application_integrated", False), "composed"),
        ("promotion", "commit", states.get("production_promoted", False), "end_to_end"),
    )
    nodes = [
        {
            "id": name,
            "kind": "Other",
            "operation": operation,
            "output_type": "bool",
            "state": bool(enabled),
            "scope": scope,
        }
        for name, operation, enabled, scope in stages
    ]
    edges = [
        {
            "source": stages[index][0],
            "destination": stages[index + 1][0],
            "relation": "precedes",
            "ordering": "program_order",
        }
        for index in range(len(stages) - 1)
    ]
    return {
        "schema_version": "workflow-evidence-flow-v2",
        "nodes": nodes,
        "edges": edges,
        "obligations": [{
            "category": "equivalence",
            "scope": "local",
            "proof_method": _proof_method(summary.get("proof_class")),
        }],
        "effects": [],
        "protocols": [],
        "claims": [
            {
                "status": "proved" if enabled else "unverified",
                "scope": scope,
            }
            for _, _, enabled, scope in stages[1:]
        ],
        "contracts": {
            "bounded": True,
            "exactness": "exact" if states.get("candidate_proved") else "other",
        },
    }


def _proof_method(value: Any) -> str:
    text = str(value or "").lower()
    for token in ("alive2", "z3", "smt", "differential", "protocol", "structural", "runtime_oracle"):
        if token in text:
            return token
    return "none"


def _training_hardware(report: dict[str, Any] | None) -> dict[str, Any]:
    architecture = platform.machine().lower()
    if architecture in {"amd64", "x64"}:
        architecture = "x86_64"
    result: dict[str, Any] = {"architecture": architecture, "device_class": "cpu"}
    descriptor = _find_descriptor(report or {}, {"architecture", "vendor", "microarchitecture", "isa", "device_class", "vector_width_bits", "vector_register_count", "l1d_bytes", "l2_bytes", "l3_bytes", "memory_channels", "measured_stream_bandwidth", "compiler_family", "compiler_major"})
    result.update(descriptor)
    return result


def _training_workload(report: dict[str, Any] | None, summary: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "phase": "other",
        "lifecycle_scope": "end_to_end" if summary.get("states", {}).get("application_integrated") else "local",
    }
    result.update(_find_descriptor(report or {}, {"input_size", "alignment", "sparsity", "mutation_density", "cache_regime", "concurrency", "warm_state", "batch_size", "lifecycle_scope", "critical_path_weight", "regional_promotion_floor", "token_count", "sequence_count", "context_bucket", "output_cardinality", "phase"}))
    return result


def _find_descriptor(value: Any, keys: set[str], *, depth: int = 0) -> dict[str, Any]:
    if depth > 6:
        return {}
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in keys and isinstance(child, (str, int, float, bool, list, tuple)):
                result[normalized] = child
            elif isinstance(child, (dict, list)):
                for found_key, found_value in _find_descriptor(child, keys - result.keys(), depth=depth + 1).items():
                    result.setdefault(found_key, found_value)
    elif isinstance(value, list):
        for child in value[:32]:
            for found_key, found_value in _find_descriptor(child, keys - result.keys(), depth=depth + 1).items():
                result.setdefault(found_key, found_value)
    return result


def _promotion_observations(
    summary: dict[str, Any], report: dict[str, Any] | None, candidate_id: str,
) -> list[dict[str, Any]]:
    states = summary.get("states", {})
    proof_class = _safe_action_token(summary.get("proof_class"), "none")
    semantic_outcome = (
        "proof_passed" if states.get("candidate_proved") else
        "missing_contract" if not states.get("meaningful_semantic_coverage") else
        "proof_unknown"
    )
    quality = (
        "A" if states.get("application_integrated") and states.get("physically_benchmarked") and states.get("candidate_proved") else
        "B" if states.get("physically_benchmarked") and states.get("candidate_proved") else
        "C" if states.get("meaningful_semantic_coverage") else "D"
    )
    observations = [make_observation(
        candidate_id, "grammar_disposition", semantic_outcome,
        {
            "proof_class": proof_class,
            "benchmark_scope": "none",
            "resources": {
                "code_size": len(summary.get("decisive_artifacts", [])),
            },
        },
        quality_grade=quality,
    )]
    if states.get("candidate_generated"):
        observations.append(make_observation(
            candidate_id, "proof", "proof_passed" if states.get("candidate_proved") else "proof_unknown",
            {"proof_class": proof_class, "benchmark_scope": "none"},
            quality_grade=quality,
        ))
    if states.get("physically_benchmarked"):
        payload = _measurement_payload(report or {})
        payload["proof_class"] = proof_class
        payload["benchmark_scope"] = "composed" if states.get("application_integrated") else "regional"
        observations.append(make_observation(
            candidate_id, "benchmark", _physical_outcome(summary, report), payload,
            quality_grade=quality,
        ))
    if states.get("application_integrated") or states.get("production_promoted"):
        outcome = "composed_win" if states.get("production_promoted") else "composed_regression"
        payload = _measurement_payload(report or {})
        payload.update({"proof_class": proof_class, "benchmark_scope": "end_to_end"})
        observations.append(make_observation(
            candidate_id, "composition", outcome, payload, quality_grade=quality,
        ))
        observations.append(make_observation(
            candidate_id,
            "retention",
            "promoted_candidate" if states.get("production_promoted") else "retained_candidate",
            {"proof_class": proof_class, "benchmark_scope": "end_to_end"},
            quality_grade=quality,
        ))
    return observations


def _physical_outcome(summary: dict[str, Any], report: dict[str, Any] | None) -> str:
    if summary.get("states", {}).get("production_promoted"):
        return "composed_win" if summary.get("states", {}).get("application_integrated") else "material_regional_win"
    text = json.dumps(report or {}, sort_keys=True).lower()
    if "measured_regression" in text or "resource_regression" in text:
        return "measured_regression"
    if "small_win_below_floor" in text or "below_floor" in text:
        return "small_win_below_floor"
    if "compiler_identical" in text:
        return "compiler_identical"
    return "statistical_tie"


def _measurement_payload(report: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "speedup": {"speedup", "speedup_percent", "speedup_pct", "median_speedup_percent"},
        "bootstrap_ci_low": {"ci_lower_percent", "ci_low", "bootstrap_ci_low"},
        "bootstrap_ci_high": {"ci_upper_percent", "ci_high", "bootstrap_ci_high"},
        "sample_count": {"sample_count", "process_count", "independent_processes"},
    }
    found: dict[str, Any] = {}

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 8 or len(found) == len(aliases):
            return
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).lower()
                for target, names in aliases.items():
                    if target not in found and normalized in names and isinstance(child, (int, float)):
                        found[target] = child
                if isinstance(child, (dict, list)):
                    visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:64]:
                visit(child, depth + 1)

    visit(report)
    payload: dict[str, Any] = {
        "sample_count": max(0, int(found.get("sample_count", 0))),
        "resources": {},
    }
    if "speedup" in found:
        payload["paired_speedup"] = {
            "median": float(found["speedup"]),
            "bootstrap_ci_low": float(found["bootstrap_ci_low"]) if "bootstrap_ci_low" in found else None,
            "bootstrap_ci_high": float(found["bootstrap_ci_high"]) if "bootstrap_ci_high" in found else None,
        }
    return payload


def create_training_bundle_from_promotion_summary(
    summary: dict[str, Any],
    output_path: Path,
    *,
    report: dict[str, Any] | None = None,
    producer_agent: str = "vladder-agentic-workflow",
    producer_model: str = "unspecified",
    producer_provider: str | None = None,
    consent_path: Path | None = None,
    identity_path: Path | None = None,
) -> dict[str, Any]:
    require_consent(CANONICAL_TRAINING_DATA, consent_path)
    if summary.get("schema_version") != "vladder-promotion-summary-v1":
        raise ValueError("promotion contribution requires vladder-promotion-summary-v1")
    workflow_key = str(summary.get("workflow_key") or canonical_hash(summary.get("manifest_identity")))
    states = summary.get("states", {})
    language = _training_language(summary.get("workflow_kind"))
    graph, graph_version = _training_graph(report, summary)
    root = make_root(
        graph,
        {
            "bounded": True,
            "exactness": "exact" if states.get("candidate_proved") else "other",
            "semantic_family": _safe_action_token(summary.get("workflow_kind"), "other"),
        },
        [{"source_language": language}],
        project_id=f"workflow:{workflow_key}",
        graph_version=graph_version,
    )
    hardware = _training_hardware(report)
    workload = _training_workload(report, summary)
    baseline = make_candidate(
        root["root_id"],
        {"family": "baseline", "family_version": "v1", "primitives": ["existing_implementation"]},
        hardware, workload, baseline=True,
    )
    candidates = [baseline]
    selected = baseline
    if states.get("candidate_generated"):
        selected = make_candidate(
            root["root_id"],
            {
                "family": _safe_action_token(summary.get("disposition"), "generated_candidate"),
                "family_version": "promotion-summary-v2",
                "primitives": [_safe_action_token(summary.get("result_classification"), "candidate")],
                "parameters": {
                    "mode": _safe_action_token(summary.get("workflow_kind"), "other"),
                },
            },
            hardware, workload, baseline=False,
            derivation=[_safe_action_token(summary.get("result_classification"), "candidate")],
        )
        candidates.append(selected)
    observations = _promotion_observations(summary, report, selected["candidate_id"])
    return _write_model_training_bundle(
        [root], candidates, observations, output_path,
        project_identity=f"workflow:{workflow_key}", producer_agent=producer_agent,
        producer_model=producer_model, producer_provider=producer_provider,
        submission_consent=True, identity_path=identity_path,
        grammar_version="terminal-promotion-graph-v2",
    )


def sync_promotion_summary(
    summary: dict[str, Any], output_directory: Path, *, report: dict[str, Any] | None = None,
    consent_path: Path | None = None,
) -> dict[str, Any]:
    output_directory = output_directory.resolve()
    bundle_path = output_directory / "promotion-model-training-bundle-v3.json"
    create_training_bundle_from_promotion_summary(
        summary, bundle_path, report=report, consent_path=consent_path,
    )
    queued = enqueue_training_bundle(bundle_path)
    flush = flush_training_outbox(consent_path=consent_path)
    current_submitted = any(
        row.get("submission", {}).get("payload_sha256") == queued["payload_sha256"]
        for row in flush["submissions"]
    )
    report = {
        "schema_version": "vladder-promotion-training-sync-v3",
        "status": "pass" if current_submitted else "queued_for_retry",
        "bundle": str(bundle_path),
        "queued_record": queued,
        "outbox_flush": flush,
        "current_record_submitted": current_submitted,
        "record_forms": [
            "bounded_graph_topology", "search_branch_lineage", "structured_baseline_and_candidate_actions",
            "workflow_disposition", "proof_and_promotion_observations", "negative_result",
            "architectural_lifetime_finding", "adapter_gap",
        ],
    }
    (output_directory / "promotion-training-sync.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def submit_training_bundle(
    bundle_path: Path,
    *,
    endpoint: str | None,
    token: str | None,
    confirm_upload: bool,
    validate_only: bool = False,
    timeout_seconds: float = 20.0,
    consent_path: Path | None = None,
) -> dict[str, Any]:
    require_consent(CANONICAL_TRAINING_DATA, consent_path)
    if not confirm_upload:
        raise ValueError("training upload is disabled by default; pass --confirm-upload after explicit user consent")
    validation = validate_training_bundle(bundle_path)
    if validation["status"] != "pass":
        raise ValueError(f"training bundle schema validation failed: {validation['errors']}")
    bundle = json.loads(bundle_path.resolve().read_text())
    if bundle.get("schema_version") != MODEL_TRAINING_SCHEMA_VERSION:
        raise ValueError(
            f"training submission requires {MODEL_TRAINING_SCHEMA_VERSION}; historical v1/v2 upload is disabled"
        )
    if endpoint is None:
        endpoint = os.environ.get("VLADDER_MODEL_TRAINING_ENDPOINT") or DEFAULT_MODEL_TRAINING_ENDPOINT
    token = token or os.environ.get("VLADDER_CONTRIBUTION_TOKEN")
    if bundle.get("privacy", {}).get("submission_consent") is not True:
        raise ValueError("training bundle must set privacy.submission_consent=true after explicit user consent")
    return submit_validated_record(
        bundle_path,
        endpoint=endpoint,
        token=token,
        timeout_seconds=timeout_seconds,
        validate_only=validate_only,
        record_name="model-training-bundle",
    )
