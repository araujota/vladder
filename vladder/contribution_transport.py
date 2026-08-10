from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlparse
from typing import Any

from . import __version__


DEFAULT_CONTRIBUTION_BASE = "https://ceaseless-manatee-888.convex.site"
DEFAULT_REVIEW_ENDPOINT = f"{DEFAULT_CONTRIBUTION_BASE}/api/reviews"
DEFAULT_MODEL_TRAINING_ENDPOINT = f"{DEFAULT_CONTRIBUTION_BASE}/api/training/v2"
MAX_CONTRIBUTION_BYTES = 768 * 1024
CAPABILITY_SCHEMA_VERSION = "vladder-contributor-capability-v1"
CAPABILITY_FILE_VERSION = "vladder-contributor-credentials-v1"
CAPABILITY_SCOPES = {
    "agent-review": "review:write",
    "training-bundle": "training:write",
    "model-training-bundle": "training:write",
}


def default_credential_path() -> Path:
    override = os.environ.get("VLADDER_CONTRIBUTION_CREDENTIAL_FILE")
    if override:
        return Path(override).expanduser()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "vladder" / "contribution-credentials.json"


def _credential_key(endpoint: str, scope: str) -> str:
    parsed = urlparse(endpoint)
    return f"{parsed.scheme}://{parsed.netloc}|{scope}"


def _load_credentials(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": CAPABILITY_FILE_VERSION, "credentials": {}}
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"contribution credential file must be owner-only, found mode {mode:o}: {path}")
    value = json.loads(path.read_text())
    if value.get("schema_version") != CAPABILITY_FILE_VERSION or not isinstance(value.get("credentials"), dict):
        raise ValueError(f"invalid contribution credential file: {path}")
    return value


def _write_credentials(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".contribution-credentials-", dir=path.parent)
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


def _register_capability(endpoint: str, scope: str, timeout_seconds: float) -> dict[str, str]:
    parsed = urlparse(endpoint)
    registration_endpoint = f"{parsed.scheme}://{parsed.netloc}/api/contributors/register"
    payload = json.dumps({"scope": scope, "client_version": __version__}, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        registration_endpoint,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": f"vladder/{__version__}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"contributor capability registration failed ({exc.code}): {body[:1000]}") from exc
    if (
        result.get("schema_version") != CAPABILITY_SCHEMA_VERSION
        or result.get("scope") != scope
        or not isinstance(result.get("token"), str)
        or not result["token"].startswith("vc1_")
    ):
        raise RuntimeError("contribution service returned an invalid capability")
    return {"credential_id": str(result.get("credential_id", "unknown")), "scope": scope, "token": result["token"]}


def load_or_register_capability(
    endpoint: str,
    scope: str,
    *,
    timeout_seconds: float,
    credential_path: Path | None = None,
    force_refresh: bool = False,
) -> str:
    if scope not in CAPABILITY_SCOPES.values():
        raise ValueError(f"unsupported contribution capability scope: {scope}")
    path = (credential_path or default_credential_path()).expanduser().resolve()
    ledger = _load_credentials(path)
    key = _credential_key(endpoint, scope)
    if not force_refresh:
        existing = ledger["credentials"].get(key)
        if isinstance(existing, dict) and isinstance(existing.get("token"), str):
            return existing["token"]
    capability = _register_capability(endpoint, scope, timeout_seconds)
    ledger["credentials"][key] = capability
    _write_credentials(path, ledger)
    return capability["token"]


def remove_capability(endpoint: str, scope: str, *, credential_path: Path | None = None) -> None:
    path = (credential_path or default_credential_path()).expanduser().resolve()
    ledger = _load_credentials(path)
    if ledger["credentials"].pop(_credential_key(endpoint, scope), None) is not None:
        _write_credentials(path, ledger)


def probe_contribution_service(
    *,
    base_url: str = DEFAULT_CONTRIBUTION_BASE,
    timeout_seconds: float = 20.0,
    credential_path: Path | None = None,
) -> dict[str, Any]:
    """Exercise authorization boundaries without sending a schema-valid contribution."""
    base_url = base_url.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError("contribution service must use HTTPS or loopback HTTP")

    def request_status(path: str, method: str, payload: bytes | None, token: str | None = None) -> tuple[int, Any]:
        headers = {"User-Agent": f"vladder/{__version__}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(base_url + path, data=payload, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
                body = response.read().decode("utf-8", errors="replace")
                return response.status, json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                value = json.loads(body)
            except json.JSONDecodeError:
                value = body
            return exc.code, value

    training_endpoint = base_url + "/api/training/v2"
    review_endpoint = base_url + "/api/reviews"
    training_token = load_or_register_capability(
        training_endpoint, "training:write", timeout_seconds=timeout_seconds, credential_path=credential_path,
    )
    review_token = load_or_register_capability(
        review_endpoint, "review:write", timeout_seconds=timeout_seconds, credential_path=credential_path,
    )
    health = request_status("/api/health", "GET", None)
    empty = b"{}"
    checks = {
        "health": {"observed": health[0], "expected": [200]},
        "legacy_training_submission_retired": {
            "observed": request_status("/api/training?validate_only=true", "POST", empty, training_token)[0],
            "expected": [410],
        },
        "model_training_scope_reaches_schema": {
            "observed": request_status("/api/training/v2?validate_only=true", "POST", empty, training_token)[0],
            "expected": [400],
        },
        "review_scope_reaches_schema": {
            "observed": request_status("/api/reviews?validate_only=true", "POST", empty, review_token)[0],
            "expected": [400],
        },
        "training_scope_cannot_write_review": {
            "observed": request_status("/api/reviews?validate_only=true", "POST", empty, training_token)[0],
            "expected": [403],
        },
        "review_scope_cannot_write_training": {
            "observed": request_status("/api/training/v2?validate_only=true", "POST", empty, review_token)[0],
            "expected": [403],
        },
        "contributor_cannot_moderate": {
            "observed": request_status(
                "/api/training/approval", "PATCH", b'{"submissionId":"untrusted","approved":true}', training_token,
            )[0],
            "expected": [401],
        },
        "contributor_cannot_moderate_model_training": {
            "observed": request_status(
                "/api/training/v2/approval", "PATCH", b'{"submissionId":"untrusted","approved":true}', training_token,
            )[0],
            "expected": [401],
        },
        "private_training_read_absent": {
            "observed": request_status("/api/training", "GET", None, training_token)[0],
            "expected": [404, 405],
        },
        "private_model_training_read_absent": {
            "observed": request_status("/api/training/v2", "GET", None, training_token)[0],
            "expected": [404, 405],
        },
    }
    for value in checks.values():
        value["pass"] = value["observed"] in value["expected"]
    return {
        "schema_version": "vladder-contribution-access-probe-v1",
        "status": "pass" if all(value["pass"] for value in checks.values()) else "fail",
        "base_url": base_url,
        "checks": checks,
        "credential_storage": str((credential_path or default_credential_path()).expanduser().resolve()),
        "records_stored": 0,
        "boundary": "scope-specific append capabilities; no private read, mutation, moderation, or deployment authority",
    }


def submit_validated_record(
    artifact_path: Path,
    *,
    endpoint: str,
    token: str | None,
    timeout_seconds: float,
    validate_only: bool,
    record_name: str,
) -> dict[str, Any]:
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError(f"{record_name} endpoint must use HTTPS or loopback HTTP")
    payload = artifact_path.resolve().read_bytes()
    if len(payload) > MAX_CONTRIBUTION_BYTES:
        raise ValueError(f"{record_name} payload exceeds {MAX_CONTRIBUTION_BYTES // 1024} KiB")
    target = endpoint + ("&" if "?" in endpoint else "?") + "validate_only=true" if validate_only else endpoint
    scope = CAPABILITY_SCOPES.get(record_name)
    managed_credential = token is None and scope is not None
    if managed_credential:
        token = load_or_register_capability(endpoint, scope, timeout_seconds=timeout_seconds)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"vladder/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    def perform(current_headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(target, data=payload, method="POST", headers=current_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
                body = response.read().decode("utf-8")
                return response.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if managed_credential and exc.code == 401 and scope is not None:
                return exc.code, {"error": body, "credential_refresh_required": True}
            raise RuntimeError(f"{record_name} service rejected submission ({exc.code}): {body[:1000]}") from exc

    status_code, result = perform(headers)
    if result.pop("credential_refresh_required", False) and scope is not None:
        remove_capability(endpoint, scope)
        token = load_or_register_capability(endpoint, scope, timeout_seconds=timeout_seconds, force_refresh=True)
        headers["Authorization"] = f"Bearer {token}"
        status_code, result = perform(headers)
        if status_code == 401:
            raise RuntimeError(f"{record_name} service rejected refreshed contributor credential")
    return {
        "schema_version": "vladder-contribution-submission-v1",
        "status": "validated_remotely" if validate_only else "submitted",
        "endpoint": endpoint,
        "http_status": status_code,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "service_response": result,
        "authorization": "installation_scoped_capability" if managed_credential else "explicit_credential",
        "privacy": f"only the validated {record_name} record was transmitted",
    }
