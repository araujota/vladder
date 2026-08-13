from __future__ import annotations

from importlib.resources import files
import json
from typing import Any

from .schema_registry import validate_payload


CANONICAL_SEARCH_ARTIFACT = "artifacts/production-canonical-search-rc29.json"


def load_canonical_search_release_artifact() -> dict[str, Any]:
    """Load and validate the canonical-search qualification bundled in the wheel."""
    resource = files("vladder").joinpath(CANONICAL_SEARCH_ARTIFACT)
    payload = json.loads(resource.read_text(encoding="utf-8"))
    validation = validate_payload(
        "canonical-search-release-artifact",
        payload,
        artifact=f"package:vladder/{CANONICAL_SEARCH_ARTIFACT}",
    )
    if validation["status"] != "pass":
        raise ValueError(f"bundled canonical-search evidence is invalid: {validation['errors']}")
    return payload
