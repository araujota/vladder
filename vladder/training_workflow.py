from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import tempfile
import uuid
from typing import Any

from . import __version__
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
    load_or_create_training_identity,
    privacy_manifest,
    sanitize_candidate,
    sanitize_observation,
    sanitize_root,
)


LEGACY_TRAINING_SCHEMA_VERSION = "vladder-training-bundle-v1"
MODEL_TRAINING_SCHEMA_VERSION = "vladder-model-training-bundle-v2"
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
    schema_version = json.loads(bundle_path.resolve().read_text()).get("schema_version")
    if schema_version != MODEL_TRAINING_SCHEMA_VERSION:
        raise ValueError(
            f"training emission requires {MODEL_TRAINING_SCHEMA_VERSION}; legacy v1 records are historical only"
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
        if payload.get("schema_version") == LEGACY_TRAINING_SCHEMA_VERSION:
            quarantine = root / "legacy-v1-quarantine"
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
    source_roots = {str(item["root_id"]): item for item in roots}
    if len(source_roots) != len(roots):
        raise ValueError("model bundle roots must have unique identities")
    identity = load_or_create_training_identity(identity_path)
    sanitized_roots = [
        sanitize_root(item, identity, project_identity=project_identity) for item in roots
    ]
    root_ids = dict(zip(
        (str(item["root_id"]) for item in roots),
        (item["root_id"] for item in sanitized_roots),
        strict=True,
    ))
    sanitized_candidates = [sanitize_candidate(item, identity, root_ids) for item in candidates]
    candidate_ids = dict(zip(
        (str(item["candidate_id"]) for item in candidates),
        (item["candidate_id"] for item in sanitized_candidates),
        strict=True,
    ))
    sanitized_observations = [
        sanitize_observation(item, identity, candidate_ids) for item in observations
    ]
    bundle = {
        "schema_version": MODEL_TRAINING_SCHEMA_VERSION,
        "bundle_id": f"bundle:{uuid.uuid4()}",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "vladder_version": __version__,
        "producer": {
            "agent": producer_agent,
            "model": producer_model,
            "provider": producer_provider,
        },
        "dataset": {
            "grammar_version": grammar_version,
            "grammar_hash": canonical_hash([item["action"] for item in candidates]),
            "canonicalizer_version": "model-ready-graph-v2",
            "identity_epoch": identity["identity_epoch"],
        },
        "roots": sanitized_roots,
        "candidates": sanitized_candidates,
        "observations": sanitized_observations,
        "privacy": privacy_manifest(identity, submission_consent=submission_consent),
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    validation = validate_training_bundle(output_path)
    if validation["status"] != "pass":
        raise ValueError(f"model training bundle failed schema validation: {validation['errors']}")
    return bundle


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
    bundle_path = output_directory / "promotion-model-training-bundle-v2.json"
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
        "schema_version": "vladder-promotion-training-sync-v2",
        "status": "pass" if current_submitted else "queued_for_retry",
        "bundle": str(bundle_path),
        "queued_record": queued,
        "outbox_flush": flush,
        "current_record_submitted": current_submitted,
        "record_forms": [
            "bounded_graph_topology", "structured_baseline_and_candidate_actions",
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
            f"training submission requires {MODEL_TRAINING_SCHEMA_VERSION}; legacy v1 upload is disabled"
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
