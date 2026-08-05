from __future__ import annotations

import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlparse
from typing import Any

from . import __version__


DEFAULT_CONTRIBUTION_BASE = "https://ceaseless-manatee-888.convex.site"
DEFAULT_REVIEW_ENDPOINT = f"{DEFAULT_CONTRIBUTION_BASE}/api/reviews"
DEFAULT_TRAINING_ENDPOINT = f"{DEFAULT_CONTRIBUTION_BASE}/api/training"
MAX_CONTRIBUTION_BYTES = 128 * 1024


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
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"vladder/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(target, data=payload, method="POST", headers=headers)
    try:
        # Endpoint schemes are constrained above.
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            body = response.read().decode("utf-8")
            result = json.loads(body) if body else {}
            status_code = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{record_name} service rejected submission ({exc.code}): {body[:1000]}") from exc
    return {
        "schema_version": "vladder-contribution-submission-v1",
        "status": "validated_remotely" if validate_only else "submitted",
        "endpoint": endpoint,
        "http_status": status_code,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "service_response": result,
        "privacy": f"only the validated {record_name} record was transmitted",
    }
