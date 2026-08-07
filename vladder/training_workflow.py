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
from .contribution_transport import DEFAULT_TRAINING_ENDPOINT, submit_validated_record
from .language_adapter import canonical_hash
from .prior_data import PHYSICAL_OUTCOMES, QUALITY_GRADES, SEMANTIC_OUTCOMES, PriorExperienceStore
from .schema_registry import validate_artifact


TRAINING_SCHEMA_VERSION = "vladder-training-bundle-v1"
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
    return validate_artifact("training-bundle", bundle_path)


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
) -> dict[str, Any]:
    if maximum_examples < 1 or maximum_examples > 256:
        raise ValueError("maximum_examples must be between 1 and 256")
    if apply_durable_consent:
        require_consent(CANONICAL_TRAINING_DATA, consent_path)
    dataset = PriorExperienceStore(store_path).load()
    roots = {item["root_id"]: item for item in dataset["roots"]}
    observations: dict[str, list[dict[str, Any]]] = {}
    for observation in dataset["observations"]:
        observations.setdefault(observation["candidate_id"], []).append(observation)
    all_candidates = sorted(dataset["candidates"], key=lambda item: item["candidate_id"])
    candidates = all_candidates[candidate_offset:candidate_offset + maximum_examples]
    examples = []
    for candidate in candidates[:maximum_examples]:
        root = roots[candidate["root_id"]]
        action = candidate["action"]
        observed = observations.get(candidate["candidate_id"], [])
        semantic = _preferred_outcome(observed, SEMANTIC_OUTCOMES, "proof_unknown")
        physical = _preferred_outcome(observed, PHYSICAL_OUTCOMES, "not_measured")
        benchmark = next(
            (item for item in reversed(observed) if item.get("outcome") == physical and item.get("kind") in {"benchmark", "composition"}),
            None,
        )
        payload = benchmark.get("payload", {}) if benchmark else {}
        paired = payload.get("paired_speedup", {}) if isinstance(payload.get("paired_speedup", {}), dict) else {}
        median = paired.get("median", payload.get("speedup"))
        low = paired.get("bootstrap_ci_low")
        high = paired.get("bootstrap_ci_high")
        quality = min(
            (str(item["quality_grade"]) for item in observed),
            key=lambda grade: ("A", "B", "C", "D").index(grade),
            default="D",
        )
        language = str(root.get("provenance", [{}])[0].get("source_language", "other"))
        if language not in {"c", "cpp", "rust", "zig", "julia", "cuda", "spirv"}:
            language = "other"
        summary = root.get("summary", {})
        numeric = {
            "graph.node_count": summary.get("node_count", 0),
            "graph.edge_count": summary.get("edge_count", 0),
            "graph.obligation_count": summary.get("obligation_count", 0),
            "graph.effect_count": summary.get("effect_count", 0),
            "graph.protocol_count": summary.get("protocol_count", 0),
            "graph.claim_count": summary.get("claim_count", 0),
        }
        numeric.update(_numeric_features("action", action.get("parameters", {})))
        numeric.update(_numeric_features("hardware", candidate.get("hardware", {})))
        numeric.update(_numeric_features("workload", candidate.get("workload", {})))
        canonical = root.get("canonical_graph", {})
        for label, count in canonical.get("nodes", []):
            numeric[f"canonical.node.{str(label)[:24]}"] = float(count)
        for label, count in canonical.get("edges", []):
            numeric[f"canonical.edge.{str(label)[:24]}"] = float(count)
        for label, count in canonical.get("feature_inventory", {}).items():
            numeric[f"canonical.feature.{canonical_hash(str(label))[:24]}"] = float(count)
        for item in observed:
            kind = _token(item.get("kind", "unknown"), "unknown")
            outcome = _token(item.get("outcome", "unknown"), "unknown")
            kind_key = f"observation.kind.{kind}.count"
            outcome_key = f"observation.outcome.{outcome}.count"
            numeric[kind_key] = numeric.get(kind_key, 0.0) + 1.0
            numeric[outcome_key] = numeric.get(outcome_key, 0.0) + 1.0
            numeric.update(_numeric_features(f"observation.{kind}", item.get("payload", {})))
        family = _anonymous_label("family", action.get("family", "baseline"))
        primitives = action.get("primitives", [])
        rule = _anonymous_label("rule", primitives[0] if primitives else action.get("family", "baseline"))
        categories = {
            "action.family_version": str(action.get("family_version", 1)),
            "candidate.baseline": "true" if candidate.get("baseline") else "false",
            "root.graph_version": _token(root.get("graph_version", "unknown"), "unknown"),
        }
        examples.append({
            "example_id": f"example:{candidate['candidate_id'][:32]}",
            "semantic_root_hash": candidate["root_id"],
            "candidate_hash": candidate["candidate_id"],
            "language": language,
            "region_kind": _anonymous_label(
                "region", root.get("contract", {}).get("semantic_family", "bounded_region"),
            ),
            "grammar_family": family,
            "grammar_rule": rule,
            "numeric_features": [
                {"name": _feature_name(name), "value": float(value)}
                for name, value in sorted(numeric.items())[:256]
            ],
            "categorical_features": [
                {"name": _feature_name(name), "value": _token(value, "unknown")}
                for name, value in sorted(categories.items())[:128]
            ],
            "evidence": {
                "semantic_outcome": semantic,
                "physical_outcome": physical,
                "proof_class": semantic,
                "quality_grade": quality if quality in QUALITY_GRADES else "D",
                "benchmark_scope": "composed" if benchmark and benchmark.get("kind") == "composition" else "micro" if benchmark else "none",
                "speedup_percent": float(median) * 100.0 if median is not None else None,
                "ci_lower_percent": float(low) * 100.0 if low is not None else None,
                "ci_upper_percent": float(high) * 100.0 if high is not None else None,
                "sample_count": int(payload.get("process_count", payload.get("sample_count", 0))),
            },
        })
    if not examples:
        raise ValueError("the prior store contains no candidate examples")
    hardware_descriptors = [item.get("hardware", {}) for item in candidates]
    bundle = {
        "schema_version": TRAINING_SCHEMA_VERSION,
        "bundle_id": f"bundle:{uuid.uuid4()}",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "vladder_version": __version__,
        "producer": {"agent": producer_agent, "model": producer_model, "provider": producer_provider},
        "dataset": {
            "project_id": f"project:{canonical_hash(project_id)[:24]}",
            "grammar_version": "structured-open-actions-v1",
            "grammar_hash": canonical_hash([item["action"] for item in candidates]),
            "hardware_class": "mixed" if len({item["hardware_id"] for item in candidates}) > 1 else _token(hardware_descriptors[0].get("architecture", "unknown"), "unknown"),
            "hardware_manifest_hash": canonical_hash(hardware_descriptors),
        },
        "examples": examples,
        "privacy": {
            "source_included": False,
            "raw_artifacts_included": False,
            "prompts_included": False,
            "personal_data_included": False,
            "submission_consent": apply_durable_consent,
        },
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
    paths = []
    for offset in range(0, candidate_count, examples_per_bundle):
        path = output_directory / f"training-bundle-{offset // examples_per_bundle:04d}.json"
        create_training_bundle_from_prior(
            store_path, path, project_id=project_id,
            producer_agent=producer_agent, producer_model=producer_model,
            producer_provider=producer_provider, maximum_examples=examples_per_bundle,
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
            "canonical_semantic_graph_features": True,
            "structured_grammar_actions": True,
            "candidate_and_negative_dispositions": True,
            "observation_kinds": observation_kinds,
            "hardware_and_workload_descriptors": True,
        },
        "export_gaps": [],
        "privacy": "source-free anonymized canonical features; no local prior records are transmitted directly",
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
    endpoint = endpoint or os.environ.get("VLADDER_TRAINING_ENDPOINT") or DEFAULT_TRAINING_ENDPOINT
    token = token or os.environ.get("VLADDER_CONTRIBUTION_TOKEN")
    validation = validate_training_bundle(bundle_path)
    if validation["status"] != "pass":
        raise ValueError(f"training bundle schema validation failed: {validation['errors']}")
    bundle = json.loads(bundle_path.resolve().read_text())
    if bundle.get("privacy", {}).get("submission_consent") is not True:
        raise ValueError("training bundle must set privacy.submission_consent=true after explicit user consent")
    return submit_validated_record(
        bundle_path,
        endpoint=endpoint,
        token=token,
        timeout_seconds=timeout_seconds,
        validate_only=validate_only,
        record_name="training-bundle",
    )
