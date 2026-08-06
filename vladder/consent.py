from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any


CONSENT_SCHEMA_VERSION = "vladder-consent-v1"
CONSENT_POLICY_VERSION = "vladder-contribution-consent-v2"
CANONICAL_TRAINING_DATA = "canonical_training_data"
AGENT_EXPERIENCE_REVIEW = "agent_experience_review"
CONSENT_SCOPES = (CANONICAL_TRAINING_DATA, AGENT_EXPERIENCE_REVIEW)
CONSENT_DECISIONS = ("opt_in", "opt_out")
REVIEW_REQUEST_INTERVAL_DAYS = 30

SCOPE_NOTICES: dict[str, dict[str, Any]] = {
    CANONICAL_TRAINING_DATA: {
        "title": "Anonymized canonical optimization training data",
        "opt_in_effect": (
            "At every eligible optimization opportunity, the agent sends all source-free training "
            "record forms supported by the installed vLadder release to the configured Convex moderation database."
        ),
        "frequency": "at every eligible newly produced workflow, candidate, proof, rejection, and measurement opportunity",
        "included": [
            "anonymized canonical information-flow/lifetime graph features and content hashes",
            "structured grammar actions, candidate dispositions, and negative results",
            "proof, differential, compilation, assembly-identity, cost, counter, benchmark, and composition labels",
            "coarsened hardware and workload descriptors plus confidence and quality metadata",
        ],
        "excluded": [
            "source code and source paths", "raw IR, assembly, proofs, traces, patches, prompts, and model files",
            "credentials and declared personal data", "the unredacted local prior store",
        ],
        "destination": "the configured vLadder Convex contribution endpoint; records are private pending moderation",
        "revocation": "opt out at any time; the new decision stops future sends but cannot recall already submitted records",
    },
    AGENT_EXPERIENCE_REVIEW: {
        "title": "Periodic agent experience review",
        "opt_in_effect": (
            "The agent may periodically ask for a source-free qualitative review of the vLadder experience. "
            "Opt-in does not submit a review without presenting the exact review record for approval."
        ),
        "frequency": f"at most once every {REVIEW_REQUEST_INTERVAL_DAYS} days, not after every workflow",
        "included": [
            "rating and outcome classification", "bounded strengths, limitations, rejected candidates, and recommendations",
            "artifact hashes, proof class, benchmark summary, and unresolved-boundary summaries",
        ],
        "excluded": ["source code", "raw artifacts or prompts", "credentials and declared personal data"],
        "destination": "the configured vLadder Convex review endpoint; reviews are private pending moderation",
        "revocation": "opt out at any time; future review requests stop, while already submitted reviews remain moderated records",
    },
}


class ConsentRequiredError(ValueError):
    """Raised before network access when durable contribution consent is absent."""


def default_consent_path() -> Path:
    override = os.environ.get("VLADDER_CONSENT_FILE")
    if override:
        return Path(override).expanduser().resolve()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return (base / "vladder" / "consent.json").resolve()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _empty_ledger() -> dict[str, Any]:
    return {
        "schema_version": CONSENT_SCHEMA_VERSION,
        "policy_version": CONSENT_POLICY_VERSION,
        "updated_at": None,
        "decisions": {},
        "activity": {},
    }


def load_consent(path: Path | None = None) -> dict[str, Any]:
    ledger_path = (path or default_consent_path()).expanduser().resolve()
    if not ledger_path.exists():
        ledger = _empty_ledger()
    else:
        value = json.loads(ledger_path.read_text())
        if not isinstance(value, dict) or value.get("schema_version") != CONSENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported vLadder consent ledger at {ledger_path}")
        if (
            value.get("policy_version") != CONSENT_POLICY_VERSION
            or not isinstance(value.get("decisions"), dict)
            or not isinstance(value.get("activity", {}), dict)
        ):
            raise ValueError(f"invalid vLadder consent ledger at {ledger_path}")
        unknown_scopes = set(value["decisions"]) - set(CONSENT_SCOPES)
        if unknown_scopes:
            raise ValueError(f"unknown consent scopes in {ledger_path}: {', '.join(sorted(unknown_scopes))}")
        for scope, record in value["decisions"].items():
            if (
                not isinstance(record, dict)
                or record.get("decision") not in CONSENT_DECISIONS
                or record.get("policy_version") != CONSENT_POLICY_VERSION
                or not isinstance(record.get("updated_at"), str)
                or not isinstance(record.get("decision_source"), str)
            ):
                raise ValueError(f"invalid consent decision for {scope} in {ledger_path}")
        ledger = value
    states = {}
    for scope in CONSENT_SCOPES:
        record = ledger["decisions"].get(scope)
        decision = record.get("decision") if isinstance(record, dict) else None
        states[scope] = decision if decision in CONSENT_DECISIONS else "unknown"
    result = {
        **ledger,
        "path": str(ledger_path),
        "states": states,
        "requires_user_clarification": [scope for scope, decision in states.items() if decision == "unknown"],
        "scope_notices": SCOPE_NOTICES,
    }
    result["review_request"] = _review_request_state(result)
    return result


def set_consent(
    scope: str,
    decision: str,
    *,
    path: Path | None = None,
    confirmed_user_choice: bool,
    decision_source: str = "explicit_user_direction",
) -> dict[str, Any]:
    if scope not in CONSENT_SCOPES:
        raise ValueError(f"unknown consent scope {scope!r}; expected one of {', '.join(CONSENT_SCOPES)}")
    if decision not in CONSENT_DECISIONS:
        raise ValueError("decision must be opt_in or opt_out")
    if not confirmed_user_choice:
        raise ValueError("refusing to record consent without --confirmed-user-choice after asking the user")
    ledger_path = (path or default_consent_path()).expanduser().resolve()
    loaded = load_consent(ledger_path)
    now = _timestamp()
    decisions = dict(loaded["decisions"])
    decisions[scope] = {
        "decision": decision,
        "updated_at": now,
        "decision_source": decision_source,
        "policy_version": CONSENT_POLICY_VERSION,
    }
    payload = {
        "schema_version": CONSENT_SCHEMA_VERSION,
        "policy_version": CONSENT_POLICY_VERSION,
        "updated_at": now,
        "decisions": decisions,
        "activity": loaded.get("activity", {}),
    }
    _write_ledger(ledger_path, payload)
    return load_consent(ledger_path)


def record_review_request(*, path: Path | None = None, confirmed_user_prompt: bool) -> dict[str, Any]:
    if not confirmed_user_prompt:
        raise ValueError("refusing to record a review request without --confirmed-user-prompt")
    require_consent(AGENT_EXPERIENCE_REVIEW, path)
    ledger_path = (path or default_consent_path()).expanduser().resolve()
    loaded = load_consent(ledger_path)
    now = datetime.now(timezone.utc)
    activity = dict(loaded.get("activity", {}))
    activity["agent_experience_review"] = {
        "last_requested_at": now.isoformat().replace("+00:00", "Z"),
        "next_eligible_at": (now + timedelta(days=REVIEW_REQUEST_INTERVAL_DAYS)).isoformat().replace("+00:00", "Z"),
    }
    _write_ledger(ledger_path, {
        "schema_version": CONSENT_SCHEMA_VERSION,
        "policy_version": CONSENT_POLICY_VERSION,
        "updated_at": _timestamp(),
        "decisions": loaded["decisions"],
        "activity": activity,
    })
    return load_consent(ledger_path)


def require_consent(scope: str, path: Path | None = None) -> dict[str, Any]:
    ledger = load_consent(path)
    if scope not in CONSENT_SCOPES:
        raise ValueError(f"unknown consent scope {scope!r}")
    decision = ledger["states"][scope]
    if decision == "unknown":
        raise ConsentRequiredError(
            f"consent for {scope} is unknown; the agent must ask the user to explicitly opt in or opt out, "
            "then persist that choice with `vladder consent set`"
        )
    if decision == "opt_out":
        raise ConsentRequiredError(
            f"the user opted out of {scope}; do not upload or ask again unless the user explicitly requests "
            "changing the saved decision"
        )
    return ledger["decisions"][scope]


def contribution_stage(scope: str, path: Path | None = None) -> dict[str, Any]:
    ledger = load_consent(path)
    decision = ledger["states"][scope]
    if decision == "unknown":
        status = "consent_required"
        next_action = "agent must ask the user to explicitly opt in or opt out and record the answer"
    elif decision == "opt_out":
        status = "disabled_by_user"
        next_action = "do not upload or ask again unless the user explicitly requests reconsideration"
    else:
        if scope == CANONICAL_TRAINING_DATA:
            status = "continuous_contribution_enabled"
            next_action = (
                "at every eligible opportunity, derive and send every supported anonymized training record form; "
                "do not ask again for each send"
            )
        else:
            review = ledger["review_request"]
            status = f"periodic_review_{review['status']}"
            next_action = (
                "request a review now, record the request, then present the exact review before submission"
                if review["status"] == "due" else
                "do not request another review before next_eligible_at"
            )
    return {
        "scope": scope,
        "decision": decision,
        "status": status,
        "network_action_performed": False,
        "next_action": next_action,
        "ledger_path": ledger["path"],
        "notice": SCOPE_NOTICES[scope],
    }


def _review_request_state(ledger: dict[str, Any]) -> dict[str, Any]:
    decision = ledger["states"][AGENT_EXPERIENCE_REVIEW]
    activity = ledger.get("activity", {}).get("agent_experience_review", {})
    next_value = activity.get("next_eligible_at") if isinstance(activity, dict) else None
    if decision == "unknown":
        status = "consent_clarification_required"
    elif decision == "opt_out":
        status = "disabled_by_user"
    elif not next_value:
        status = "due"
    else:
        try:
            next_time = datetime.fromisoformat(str(next_value).replace("Z", "+00:00"))
            status = "due" if datetime.now(timezone.utc) >= next_time else "not_due"
        except ValueError:
            raise ValueError("invalid next_eligible_at in vLadder consent ledger") from None
    return {
        "status": status,
        "last_requested_at": activity.get("last_requested_at") if isinstance(activity, dict) else None,
        "next_eligible_at": next_value,
        "interval_days": REVIEW_REQUEST_INTERVAL_DAYS,
    }


def _write_ledger(ledger_path: Path, payload: dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".consent-", suffix=".json", dir=ledger_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, ledger_path)
        os.chmod(ledger_path, 0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
