from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid
from typing import Any

from . import __version__
from .consent import AGENT_EXPERIENCE_REVIEW, require_consent
from .contribution_transport import DEFAULT_REVIEW_ENDPOINT, submit_validated_record
from .schema_registry import validate_artifact


REVIEW_SCHEMA_VERSION = "vladder-agent-review-v1"
PROMPT_VERSION = "vladder-agent-review-prompt-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_review_template(
    promotion_summary_path: Path,
    output_path: Path,
    *,
    project_name: str,
    project_revision: str,
    repository: str | None = None,
) -> dict[str, Any]:
    promotion_summary_path = promotion_summary_path.resolve()
    summary = json.loads(promotion_summary_path.read_text())
    if summary.get("schema_version") != "vladder-promotion-summary-v1":
        raise ValueError("review templates require a vladder-promotion-summary-v1 artifact")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    review = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "canonical_prompt_version": PROMPT_VERSION,
        "review_id": f"review:{uuid.uuid4()}",
        "created_at": now,
        "vladder_version": __version__,
        "reviewer": {"agent": "TODO", "model": "TODO", "provider": None},
        "project": {"name": project_name, "repository": repository, "revision": project_revision},
        "scope": {
            "summary": "TODO: selected region and semantic boundary",
            "languages": [str(summary.get("workflow_kind", "unknown"))],
            "region_count": 1,
            "workload": "TODO: exact workload identity",
        },
        "evidence": {
            "promotion_summary_sha256": _sha256(promotion_summary_path),
            "proof_class": str(summary.get("proof_class", "none")),
            "artifact_schema_versions": ["vladder-promotion-summary-v1"],
            "benchmark_summary": "TODO: paired effect, interval, and composed result",
        },
        "assessment": {
            "rating": 0,
            "outcome": "partial_evidence",
            "claim": str(summary.get("claim_boundary", "TODO: bounded evidence claim")),
            "strengths": ["TODO"],
            "limitations": ["TODO"],
            "rejected_candidates": ["TODO or none"],
            "unresolved_boundaries": list(summary.get("blockers", [])) or ["TODO or none"],
            "recommendations": [str(summary.get("next_action", "TODO"))],
        },
        "privacy": {"source_included": False, "raw_artifacts_included": False, "submission_consent": False},
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
    return review


def validate_review(review_path: Path) -> dict[str, Any]:
    return validate_artifact("agent-review", review_path)


def submit_review(
    review_path: Path,
    *,
    endpoint: str | None,
    token: str | None,
    confirm_upload: bool,
    validate_only: bool = False,
    timeout_seconds: float = 20.0,
    consent_path: Path | None = None,
) -> dict[str, Any]:
    require_consent(AGENT_EXPERIENCE_REVIEW, consent_path)
    if not confirm_upload:
        raise ValueError("review upload is disabled by default; pass --confirm-upload after explicit user consent")
    endpoint = endpoint or os.environ.get("VLADDER_REVIEW_ENDPOINT") or DEFAULT_REVIEW_ENDPOINT
    token = token or os.environ.get("VLADDER_CONTRIBUTION_TOKEN") or os.environ.get("VLADDER_REVIEW_TOKEN")
    validation = validate_review(review_path)
    if validation["status"] != "pass":
        raise ValueError(f"review schema validation failed: {validation['errors']}")
    review = json.loads(review_path.resolve().read_text())
    if review.get("privacy", {}).get("submission_consent") is not True:
        raise ValueError("review record must set privacy.submission_consent=true after explicit user consent")
    result = submit_validated_record(
        review_path,
        endpoint=endpoint,
        token=token,
        timeout_seconds=timeout_seconds,
        validate_only=validate_only,
        record_name="agent-review",
    )
    result["review_sha256"] = result.pop("payload_sha256")
    return result
