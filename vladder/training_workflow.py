from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid
from typing import Any

from . import __version__
from .consent import CANONICAL_TRAINING_DATA, require_consent
from .contribution_transport import (
    DEFAULT_MODEL_TRAINING_ENDPOINT,
    DEFAULT_TRAINING_ENDPOINT,
    submit_validated_record,
)
from .language_adapter import canonical_hash
from .prior_data import PHYSICAL_OUTCOMES, QUALITY_GRADES, SEMANTIC_OUTCOMES, PriorExperienceStore
from .schema_registry import validate_artifact
from .training_privacy import (
    MAX_CANDIDATES_PER_BUNDLE,
    MAX_OBSERVATIONS_PER_BUNDLE,
    MAX_ROOTS_PER_BUNDLE,
    load_or_create_training_identity,
    privacy_manifest,
    sanitize_candidate,
    sanitize_observation,
    sanitize_root,
)


TRAINING_SCHEMA_VERSION = "vladder-training-bundle-v1"
MODEL_TRAINING_SCHEMA_VERSION = "vladder-model-training-bundle-v2"
_ZERO_HASH = "0" * 64
TRAINING_OUTBOX_SCHEMA_VERSION = "vladder-training-outbox-v1"


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
    failure: str | None = None
    for entry in pending:
        if stat.S_IMODE(entry.stat().st_mode) & 0o077:
            failure = f"training outbox entry must be owner-only: {entry}"
            break
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
        "retryable_error": failure,
        "outbox": str(root),
    }


def create_training_template(output_path: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    bundle = {
        "schema_version": TRAINING_SCHEMA_VERSION,
        "bundle_id": f"bundle:{uuid.uuid4()}",
        "created_at": now,
        "vladder_version": __version__,
        "producer": {"agent": "TODO", "model": "TODO", "provider": None},
        "dataset": {
            "project_id": "anonymous-project",
            "grammar_version": "TODO",
            "grammar_hash": _ZERO_HASH,
            "hardware_class": "TODO",
            "hardware_manifest_hash": _ZERO_HASH,
        },
        "examples": [{
            "example_id": f"example:{uuid.uuid4()}",
            "semantic_root_hash": _ZERO_HASH,
            "candidate_hash": _ZERO_HASH,
            "language": "other",
            "region_kind": "TODO",
            "grammar_family": "TODO",
            "grammar_rule": "TODO",
            "numeric_features": [],
            "categorical_features": [],
            "evidence": {
                "semantic_outcome": "proof_unknown",
                "physical_outcome": "not_measured",
                "proof_class": "none",
                "quality_grade": "D",
                "benchmark_scope": "none",
                "speedup_percent": None,
                "ci_lower_percent": None,
                "ci_upper_percent": None,
                "sample_count": 0,
            },
        }],
        "privacy": {
            "source_included": False,
            "raw_artifacts_included": False,
            "prompts_included": False,
            "personal_data_included": False,
            "submission_consent": False,
        },
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    return bundle


def validate_training_bundle(bundle_path: Path) -> dict[str, Any]:
    try:
        schema_version = json.loads(bundle_path.resolve().read_text()).get("schema_version")
    except (json.JSONDecodeError, AttributeError):
        schema_version = None
    kind = "model-training-bundle" if schema_version == MODEL_TRAINING_SCHEMA_VERSION else "training-bundle"
    report = validate_artifact(kind, bundle_path)
    if report["status"] == "pass" and schema_version == MODEL_TRAINING_SCHEMA_VERSION:
        payload = json.loads(bundle_path.resolve().read_text())
        integrity_errors = _model_training_integrity_errors(payload)
        if integrity_errors:
            report["status"] = "fail"
            report["errors"].extend({"path": "/", "message": error, "validator": "link_integrity"} for error in integrity_errors)
    return report


def _model_training_integrity_errors(bundle: dict[str, Any]) -> list[str]:
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
    identity = load_or_create_training_identity(identity_path)
    sanitized_roots = [
        sanitize_root(roots[root_id], identity, project_identity=project_id) for root_id in selected_root_ids
    ]
    root_ids = dict(zip(selected_root_ids, (item["root_id"] for item in sanitized_roots), strict=True))
    sanitized_candidates = [sanitize_candidate(item, identity, root_ids) for item in candidates]
    candidate_ids = dict(zip(
        (str(item["candidate_id"]) for item in candidates),
        (item["candidate_id"] for item in sanitized_candidates),
        strict=True,
    ))
    sanitized_observations = [
        sanitize_observation(item, identity, candidate_ids) for item in selected_observations
    ]
    bundle = {
        "schema_version": MODEL_TRAINING_SCHEMA_VERSION,
        "bundle_id": f"bundle:{uuid.uuid4()}",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "vladder_version": __version__,
        "producer": {"agent": producer_agent, "model": producer_model, "provider": producer_provider},
        "dataset": {
            "grammar_version": "structured-open-actions-v2",
            "grammar_hash": canonical_hash([item["action"] for item in candidates]),
            "canonicalizer_version": "model-ready-graph-v2",
            "identity_epoch": identity["identity_epoch"],
        },
        "roots": sanitized_roots,
        "candidates": sanitized_candidates,
        "observations": sanitized_observations,
        "privacy": privacy_manifest(identity, submission_consent=apply_durable_consent),
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    validation = validate_training_bundle(output_path)
    if validation["status"] != "pass":
        raise ValueError(f"derived training bundle failed schema validation: {validation['errors']}")
    return bundle


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
    observation_kinds = sorted({str(item.get("kind")) for item in dataset["observations"]})
    report = {
        "schema_version": "vladder-training-export-v1",
        "status": "pass",
        "candidate_count": candidate_count,
        "bundle_count": len(paths),
        "all_supported_candidates_exported": True,
        "bundles": paths,
        "total_bytes": sum(Path(path).stat().st_size for path in paths),
        "record_forms": {
            "bounded_semantic_graph_topology": True,
            "structured_grammar_actions": True,
            "candidate_and_negative_dispositions": True,
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


def create_training_bundle_from_promotion_summary(
    summary: dict[str, Any],
    output_path: Path,
    *,
    producer_agent: str = "vladder-agentic-workflow",
    producer_model: str = "unspecified",
    consent_path: Path | None = None,
) -> dict[str, Any]:
    require_consent(CANONICAL_TRAINING_DATA, consent_path)
    if summary.get("schema_version") != "vladder-promotion-summary-v1":
        raise ValueError("promotion contribution requires vladder-promotion-summary-v1")
    workflow_key = str(summary.get("workflow_key") or canonical_hash(summary.get("manifest_identity")))
    root_hash = workflow_key if len(workflow_key) == 64 else canonical_hash(workflow_key)
    candidate_hash = canonical_hash({
        "root": root_hash,
        "candidate": summary.get("candidate_identity"),
        "disposition": summary.get("disposition"),
        "result": summary.get("result_classification"),
    })
    states = summary.get("states", {})
    numeric = {f"workflow.state.{key}": float(bool(value)) for key, value in states.items()}
    numeric.update({
        "workflow.blocker_count": float(len(summary.get("blockers", []))),
        "workflow.architectural_finding_count": float(len(summary.get("architectural_findings", []))),
        "workflow.decisive_artifact_count": float(len(summary.get("decisive_artifacts", []))),
    })
    semantic_outcome = "proof_passed" if states.get("candidate_proved") else "proof_unknown"
    physical_outcome = "composed_win" if states.get("production_promoted") else "not_measured"
    example = {
        "example_id": f"example:{candidate_hash[:32]}",
        "semantic_root_hash": root_hash,
        "candidate_hash": candidate_hash,
        "language": str(summary.get("workflow_kind")) if summary.get("workflow_kind") in {"c", "cpp", "rust", "zig", "julia"} else "other",
        "region_kind": _anonymous_label("region", summary.get("workflow_kind", "unknown")),
        "grammar_family": _anonymous_label("family", summary.get("disposition", "unknown")),
        "grammar_rule": _anonymous_label("rule", summary.get("result_classification", "unknown")),
        "numeric_features": [
            {"name": _feature_name(name), "value": value} for name, value in sorted(numeric.items())
        ],
        "categorical_features": [
            {"name": "workflow.proof_class_hash", "value": canonical_hash(str(summary.get("proof_class")))[:32]},
            {"name": "workflow.coverage_hash", "value": canonical_hash(str(summary.get("meaningful_coverage")))[:32]},
            {"name": "workflow.blockers_hash", "value": canonical_hash(sorted(str(item) for item in summary.get("blockers", [])))[:32]},
        ],
        "evidence": {
            "semantic_outcome": semantic_outcome,
            "physical_outcome": physical_outcome,
            "proof_class": semantic_outcome,
            "quality_grade": "B" if states.get("physically_benchmarked") else "C",
            "benchmark_scope": "end_to_end" if states.get("production_promoted") else "none",
            "speedup_percent": None,
            "ci_lower_percent": None,
            "ci_upper_percent": None,
            "sample_count": 0,
        },
    }
    bundle = {
        "schema_version": TRAINING_SCHEMA_VERSION,
        "bundle_id": f"bundle:{uuid.uuid4()}",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "vladder_version": __version__,
        "producer": {"agent": producer_agent, "model": producer_model, "provider": None},
        "dataset": {
            "project_id": f"project:{canonical_hash(root_hash)[:24]}",
            "grammar_version": "promotion-summary-v1",
            "grammar_hash": canonical_hash(summary.get("manifest_identity")),
            "hardware_class": "redacted",
            "hardware_manifest_hash": canonical_hash("redacted-hardware"),
        },
        "examples": [example],
        "privacy": {
            "source_included": False, "raw_artifacts_included": False,
            "prompts_included": False, "personal_data_included": False,
            "submission_consent": True,
        },
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    validation = validate_training_bundle(output_path)
    if validation["status"] != "pass":
        raise ValueError(f"promotion training bundle failed schema validation: {validation['errors']}")
    return bundle


def sync_promotion_summary(
    summary: dict[str, Any], output_directory: Path, *, consent_path: Path | None = None,
) -> dict[str, Any]:
    output_directory = output_directory.resolve()
    bundle_path = output_directory / "promotion-training-bundle.json"
    create_training_bundle_from_promotion_summary(summary, bundle_path, consent_path=consent_path)
    queued = enqueue_training_bundle(bundle_path)
    flush = flush_training_outbox(consent_path=consent_path)
    current_submitted = any(
        row.get("submission", {}).get("payload_sha256") == queued["payload_sha256"]
        for row in flush["submissions"]
    )
    report = {
        "schema_version": "vladder-promotion-training-sync-v1",
        "status": "pass" if current_submitted else "queued_for_retry",
        "bundle": str(bundle_path),
        "queued_record": queued,
        "outbox_flush": flush,
        "current_record_submitted": current_submitted,
        "record_forms": [
            "workflow_disposition", "proof_and_promotion_state", "negative_result",
            "architectural_lifetime_finding", "adapter_gap",
        ],
    }
    (output_directory / "promotion-training-sync.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _preferred_outcome(observations: list[dict[str, Any]], allowed: frozenset[str], default: str) -> str:
    values = [str(item.get("outcome")) for item in observations if item.get("outcome") in allowed]
    return values[-1] if values else default


def _numeric_features(prefix: str, value: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    if isinstance(value, bool):
        result[prefix] = float(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result[prefix] = float(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            result.update(_numeric_features(f"{prefix}.{key}", child))
    return result


def _feature_name(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "_.:-" else "_" for character in value)
    if cleaned and not cleaned[0].isalpha():
        cleaned = f"feature_{cleaned}"
    return (cleaned or "feature")[:96]


def _token(value: Any, default: str) -> str:
    text = str(value or default)
    cleaned = "".join(character if character.isalnum() or character in "_.:+/-" else "_" for character in text)
    if cleaned and not cleaned[0].isalnum():
        cleaned = f"value_{cleaned}"
    return (cleaned or default)[:128]


def _anonymous_label(kind: str, value: Any) -> str:
    return f"{kind}:{canonical_hash(str(value))[:24]}"


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
    model_ready = bundle.get("schema_version") == MODEL_TRAINING_SCHEMA_VERSION
    if endpoint is None:
        endpoint = (
            os.environ.get("VLADDER_MODEL_TRAINING_ENDPOINT")
            if model_ready else os.environ.get("VLADDER_TRAINING_ENDPOINT")
        ) or (DEFAULT_MODEL_TRAINING_ENDPOINT if model_ready else DEFAULT_TRAINING_ENDPOINT)
    token = token or os.environ.get("VLADDER_CONTRIBUTION_TOKEN")
    if bundle.get("privacy", {}).get("submission_consent") is not True:
        raise ValueError("training bundle must set privacy.submission_consent=true after explicit user consent")
    return submit_validated_record(
        bundle_path,
        endpoint=endpoint,
        token=token,
        timeout_seconds=timeout_seconds,
        validate_only=validate_only,
        record_name="model-training-bundle" if model_ready else "training-bundle",
    )
