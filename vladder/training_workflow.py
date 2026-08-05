from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
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
    maximum_examples: int = 256,
) -> dict[str, Any]:
    if maximum_examples < 1 or maximum_examples > 256:
        raise ValueError("maximum_examples must be between 1 and 256")
    dataset = PriorExperienceStore(store_path).load()
    roots = {item["root_id"]: item for item in dataset["roots"]}
    observations: dict[str, list[dict[str, Any]]] = {}
    for observation in dataset["observations"]:
        observations.setdefault(observation["candidate_id"], []).append(observation)
    candidates = sorted(dataset["candidates"], key=lambda item: item["candidate_id"])
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
        family = _token(action.get("family", "baseline"), "baseline")
        primitives = action.get("primitives", [])
        rule = _token(primitives[0] if primitives else family, family)
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
            "region_kind": _token(root.get("contract", {}).get("semantic_family", "bounded_region"), "bounded_region"),
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
            "project_id": project_id,
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
            "submission_consent": False,
        },
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    validation = validate_training_bundle(output_path)
    if validation["status"] != "pass":
        raise ValueError(f"derived training bundle failed schema validation: {validation['errors']}")
    return bundle


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
