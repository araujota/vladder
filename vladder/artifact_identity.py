from __future__ import annotations

import hashlib
import re
from pathlib import Path


DEFAULT_COMPONENT_LIMIT = 180


def bounded_artifact_name(
    kind: str,
    identity: str,
    suffix: str,
    *,
    component_limit: int = DEFAULT_COMPONENT_LIMIT,
) -> str:
    """Return a readable, content-addressed filename below a byte limit."""
    if component_limit < 48:
        raise ValueError("artifact component limit must leave room for kind, hash, and suffix")
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    kind_slug = _slug(kind)[:32] or "artifact"
    identity_slug = _slug(identity) or "identity"
    fixed = f"{kind_slug}--{digest}{normalized_suffix}"
    available = component_limit - len(fixed.encode("utf-8")) - 1
    if available < 1:
        raise ValueError("artifact component limit is too small for the fixed identity fields")
    prefix = identity_slug.encode("ascii")[:available].decode("ascii", errors="ignore").rstrip("-_")
    name = f"{kind_slug}-{prefix}--{digest}{normalized_suffix}"
    if len(name.encode("utf-8")) > component_limit:
        raise AssertionError("bounded artifact name exceeded its configured limit")
    return name


def bounded_artifact_path(
    directory: Path,
    kind: str,
    identity: str,
    suffix: str,
    *,
    component_limit: int = DEFAULT_COMPONENT_LIMIT,
) -> Path:
    return directory / bounded_artifact_name(
        kind, identity, suffix, component_limit=component_limit
    )


def _slug(value: str) -> str:
    ascii_value = value.encode("ascii", errors="ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_value).strip("-._")

