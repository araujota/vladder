from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_ROOT = Path(__file__).resolve().parent / "schemas"
REGISTRY_PATH = SCHEMA_ROOT / "registry.json"


def load_schema_registry() -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text())
    if registry.get("schema_version") != "vladder-schema-registry-v1":
        raise ValueError("unsupported vLadder schema registry")
    return registry


def list_artifact_schemas() -> dict[str, Any]:
    registry = load_schema_registry()
    return {
        "schema_version": registry["schema_version"],
        "compatibility_policy": registry["compatibility_policy"],
        "artifacts": registry["artifacts"],
    }


def schema_for_kind(kind: str) -> dict[str, Any]:
    registry = load_schema_registry()
    entry = registry["artifacts"].get(kind)
    if entry is None:
        raise ValueError(f"unknown artifact kind {kind!r}; expected {sorted(registry['artifacts'])}")
    schema_path = SCHEMA_ROOT / str(entry["file"])
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
    return schema


def validate_artifact(kind: str, artifact_path: Path) -> dict[str, Any]:
    artifact_path = artifact_path.resolve()
    payload = json.loads(artifact_path.read_text())
    schema = schema_for_kind(kind)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    rendered = []
    for error in errors:
        location = "/" + "/".join(str(item) for item in error.absolute_path)
        rendered.append({"path": location, "message": error.message, "validator": error.validator})
    return {
        "schema_version": "vladder-schema-validation-v1",
        "status": "pass" if not rendered else "fail",
        "artifact_kind": kind,
        "artifact": str(artifact_path),
        "artifact_schema": schema.get("$id"),
        "errors": rendered,
    }
