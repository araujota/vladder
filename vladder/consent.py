from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any


CONSENT_SCHEMA_VERSION = "vladder-consent-v1"
CONSENT_POLICY_VERSION = "vladder-contribution-consent-v1"
CANONICAL_TRAINING_DATA = "canonical_training_data"
AGENT_EXPERIENCE_REVIEW = "agent_experience_review"
CONSENT_SCOPES = (CANONICAL_TRAINING_DATA, AGENT_EXPERIENCE_REVIEW)
CONSENT_DECISIONS = ("opt_in", "opt_out")


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
    }


def load_consent(path: Path | None = None) -> dict[str, Any]:
    ledger_path = (path or default_consent_path()).expanduser().resolve()
    if not ledger_path.exists():
        ledger = _empty_ledger()
    else:
        value = json.loads(ledger_path.read_text())
        if not isinstance(value, dict) or value.get("schema_version") != CONSENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported vLadder consent ledger at {ledger_path}")
        if value.get("policy_version") != CONSENT_POLICY_VERSION or not isinstance(value.get("decisions"), dict):
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
    return {
        **ledger,
        "path": str(ledger_path),
        "states": states,
        "requires_user_clarification": [scope for scope, decision in states.items() if decision == "unknown"],
    }


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
    }
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
        status = "available_not_executed"
        next_action = "preview the exact record; upload only with record consent and --confirm-upload"
    return {
        "scope": scope,
        "decision": decision,
        "status": status,
        "network_action_performed": False,
        "next_action": next_action,
        "ledger_path": ledger["path"],
    }
