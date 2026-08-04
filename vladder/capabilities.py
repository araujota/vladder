from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json
from pathlib import Path
from typing import Any, Iterable


ALLOWED_STATUSES = frozenset({"operational", "experimental", "modeled", "research"})
REQUIRED_FAMILY_FIELDS = frozenset(
    {"id", "title", "status", "concerns", "rules", "contract_facts", "proof_strategies", "cost_signals", "lowerer", "source_routes"}
)


@dataclass(frozen=True)
class GrammarRegistry:
    version: str
    language_scope: tuple[str, ...]
    families: tuple[dict[str, Any], ...]
    sha256: str
    source: str

    def family(self, family_id: str) -> dict[str, Any]:
        for family in self.families:
            if family["id"] == family_id:
                return dict(family)
        raise KeyError(f"unknown grammar family: {family_id}")

    def executable_families(self) -> tuple[str, ...]:
        return tuple(str(family["id"]) for family in self.families if family.get("source_routes"))

    def plan_families(self) -> tuple[str, ...]:
        return tuple(str(family["id"]) for family in self.families)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "language_scope": list(self.language_scope),
            "families": [dict(family) for family in self.families],
            "sha256": self.sha256,
            "source": self.source,
        }


def _canonical_hash(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_registry(data: dict[str, Any]) -> None:
    if not isinstance(data.get("version"), str) or not data["version"]:
        raise ValueError("grammar registry requires a non-empty version")
    if not isinstance(data.get("language_scope"), list) or not data["language_scope"]:
        raise ValueError("grammar registry requires language_scope")
    families = data.get("families")
    if not isinstance(families, list) or not families:
        raise ValueError("grammar registry requires at least one family")
    seen: set[str] = set()
    for family in families:
        if not isinstance(family, dict):
            raise ValueError("grammar family must be an object")
        missing = REQUIRED_FAMILY_FIELDS - family.keys()
        if missing:
            raise ValueError(f"grammar family is missing fields: {sorted(missing)}")
        family_id = str(family["id"])
        if family_id in seen:
            raise ValueError(f"duplicate grammar family: {family_id}")
        seen.add(family_id)
        if family["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"invalid status for {family_id}: {family['status']}")
        for field in ("concerns", "rules", "contract_facts", "proof_strategies", "cost_signals"):
            if not isinstance(family[field], list) or not family[field]:
                raise ValueError(f"grammar family {family_id} requires non-empty {field}")
        if not isinstance(family["lowerer"], str) or ":" not in family["lowerer"]:
            raise ValueError(f"grammar family {family_id} requires an importable lowerer entrypoint")
        if not isinstance(family["source_routes"], dict):
            raise ValueError(f"grammar family {family_id} source_routes must be an object")


def load_registry(path: str | Path | None = None, *, validate_lowerers: bool = True) -> GrammarRegistry:
    if path is None:
        resource = files("vladder").joinpath("grammars", "vladder-v1", "capabilities.json")
        source = str(resource)
        data = json.loads(resource.read_text(encoding="utf-8"))
    else:
        source_path = Path(path).resolve()
        source = str(source_path)
        data = json.loads(source_path.read_text(encoding="utf-8"))
    _validate_registry(data)
    registry = GrammarRegistry(
        version=str(data["version"]),
        language_scope=tuple(str(item) for item in data["language_scope"]),
        families=tuple(dict(item) for item in data["families"]),
        sha256=_canonical_hash(data),
        source=source,
    )
    if validate_lowerers:
        from .lowering import validate_lowering_registry

        validate_lowering_registry(registry)
    return registry


def require_executable(registry: GrammarRegistry, family_ids: Iterable[str]) -> None:
    unsupported = []
    for family_id in family_ids:
        family = registry.family(family_id)
        if not family.get("source_routes"):
            unsupported.append(f"{family_id} (plan-only)")
    if unsupported:
        raise RuntimeError("requested grammar families have no production lowerer: " + ", ".join(unsupported))
