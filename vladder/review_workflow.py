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
        "reviewer": {"agent": "unspecified-agent", "model": "unspecified-model", "provider": None},
        "project": {"name": project_name, "repository": repository, "revision": project_revision},
        "scope": {
            "summary": f"{summary.get('workflow_kind', 'unknown')} workflow: {summary.get('disposition', 'unclassified')}",
            "languages": [str(summary.get("workflow_kind", "unknown"))],
            "region_count": 1,
            "workload": str(summary.get("workflow_key") or "workflow identity unavailable"),
        },
        "evidence": {
            "promotion_summary_sha256": _sha256(promotion_summary_path),
            "proof_class": str(summary.get("proof_class", "none")),
            "artifact_schema_versions": ["vladder-promotion-summary-v1"],
            "benchmark_summary": (
                f"physically_benchmarked={bool(summary.get('states', {}).get('physically_benchmarked'))}; "
                f"application_integrated={bool(summary.get('states', {}).get('application_integrated'))}; "
                f"promotion_permitted={bool(summary.get('promotion_permitted'))}"
            ),
        },
        "assessment": {
            "rating": 0,
            "outcome": "partial_evidence",
            "claim": str(summary.get("claim_boundary", "TODO: bounded evidence claim")),
            "strengths": ["TODO"],
            "limitations": ["TODO"],
            "rejected_candidates": (
                [str(summary.get("candidate_identity") or summary.get("disposition"))]
                if summary.get("states", {}).get("candidate_generated") and not summary.get("promotion_permitted")
                else ["none recorded in the promotion summary"]
            ),
            "unresolved_boundaries": list(summary.get("blockers", [])) or ["none recorded in the promotion summary"],
            "recommendations": ["TODO: qualitative recommendation; objective next action was " + str(summary.get("next_action", "unavailable"))],
        },
        "privacy": {"source_included": False, "raw_artifacts_included": False, "submission_consent": False},
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
    return review


def create_campaign_review_template(
    promotion_summary_paths: list[Path],
    output_path: Path,
    *,
    project_name: str,
    project_revision: str,
    repository: str | None = None,
) -> dict[str, Any]:
    if not promotion_summary_paths:
        raise ValueError("campaign review requires at least one promotion summary")
    resolved = [path.resolve() for path in promotion_summary_paths]
    summaries = [json.loads(path.read_text()) for path in resolved]
    if any(item.get("schema_version") != "vladder-promotion-summary-v1" for item in summaries):
        raise ValueError("campaign review inputs must all be vladder-promotion-summary-v1 artifacts")
    combined_hash = hashlib.sha256(
        "".join(_sha256(path) for path in resolved).encode()
    ).hexdigest()
    languages = sorted({str(item.get("workflow_kind", "unknown")) for item in summaries})
    proof_classes = sorted({str(item.get("proof_class", "none")) for item in summaries})
    promoted = [item for item in summaries if item.get("promotion_permitted")]
    rejected = [item for item in summaries if item.get("states", {}).get("candidate_generated") and not item.get("promotion_permitted")]
    blockers = sorted({str(blocker) for item in summaries for blocker in item.get("blockers", [])})
    measured = sum(bool(item.get("states", {}).get("physically_benchmarked")) for item in summaries)
    integrated = sum(bool(item.get("states", {}).get("application_integrated")) for item in summaries)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    review = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "canonical_prompt_version": PROMPT_VERSION,
        "review_id": f"review:{uuid.uuid4()}",
        "created_at": now,
        "vladder_version": __version__,
        "reviewer": {"agent": "unspecified-agent", "model": "unspecified-model", "provider": None},
        "project": {"name": project_name, "repository": repository, "revision": project_revision},
        "scope": {
            "summary": f"Campaign review across {len(summaries)} terminal vLadder workflows",
            "languages": languages,
            "region_count": len(summaries),
            "workload": "multiple workflow identities; see aggregate promotion-summary hash",
        },
        "evidence": {
            "promotion_summary_sha256": combined_hash,
            "proof_class": "; ".join(proof_classes),
            "artifact_schema_versions": ["vladder-promotion-summary-v1"],
            "benchmark_summary": (
                f"workflows={len(summaries)}; measured={measured}; integrated={integrated}; "
                f"promoted={len(promoted)}; rejected_candidates={len(rejected)}"
            ),
        },
        "assessment": {
            "rating": 0,
            "outcome": (
                "retained_win" if promoted else
                "verified_negative" if measured == len(summaries) else
                "partial_evidence"
            ),
            "claim": "Campaign aggregation preserves each source promotion summary's claim boundary; it creates no new proof or compounded speedup claim.",
            "strengths": ["TODO: qualitative strength"],
            "limitations": ["TODO: qualitative limitation"],
            "rejected_candidates": [
                str(item.get("candidate_identity") or item.get("disposition")) for item in rejected
            ] or ["none recorded across campaign"],
            "unresolved_boundaries": blockers or ["none recorded across campaign"],
            "recommendations": ["TODO: qualitative recommendation"],
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
