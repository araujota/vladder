from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from .capabilities import GrammarRegistry, load_registry


class LoweringMode(str, Enum):
    PLAN = "plan"
    SOURCE = "source"


class LoweringStatus(str, Enum):
    PLANNED = "planned"
    ROUTED = "routed"
    REJECTED = "rejected"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class LoweringRequest:
    family: str
    rule: str
    contract_facts: Mapping[str, Any] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    mode: LoweringMode = LoweringMode.PLAN
    source: Path | None = None
    function: str | None = None
    input_identity: str = "unbound-region"

    def resolved_input_identity(self) -> str:
        if self.input_identity != "unbound-region" or self.source is None:
            return self.input_identity
        source = self.source.resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        suffix = f"#{self.function}" if self.function else ""
        return f"sha256:{digest}{suffix}"


@dataclass(frozen=True)
class LoweringOperation:
    opcode: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opcode": self.opcode,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class LoweringPlan:
    plan_id: str
    grammar_version: str
    grammar_sha256: str
    family: str
    rule: str
    maturity: str
    required_facts: tuple[str, ...]
    required_parameters: tuple[str, ...]
    operations: tuple[LoweringOperation, ...]
    proof_obligations: tuple[str, ...]
    cost_signals: tuple[str, ...]
    backend: str | None
    source_emission: str
    input_identity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "grammar_version": self.grammar_version,
            "grammar_sha256": self.grammar_sha256,
            "family": self.family,
            "rule": self.rule,
            "maturity": self.maturity,
            "required_facts": list(self.required_facts),
            "required_parameters": list(self.required_parameters),
            "operations": [item.to_dict() for item in self.operations],
            "proof_obligations": list(self.proof_obligations),
            "cost_signals": list(self.cost_signals),
            "backend": self.backend,
            "source_emission": self.source_emission,
            "input_identity": self.input_identity,
        }


@dataclass(frozen=True)
class LoweringResult:
    status: LoweringStatus
    plan: LoweringPlan | None
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "vladder-lowering-result-v1",
            "status": self.status.value,
            "plan": self.plan.to_dict() if self.plan else None,
            "diagnostics": list(self.diagnostics),
        }


class FamilyLowerer(Protocol):
    family_id: str

    def covered_rules(self, family: Mapping[str, Any]) -> tuple[str, ...]: ...

    def lower(
        self,
        registry: GrammarRegistry,
        family: Mapping[str, Any],
        request: LoweringRequest,
    ) -> LoweringResult: ...


def resolve_entrypoint(entrypoint: str) -> type[FamilyLowerer]:
    if ":" not in entrypoint:
        raise ValueError(f"lowerer entrypoint must use module:object syntax: {entrypoint}")
    module_name, object_name = entrypoint.split(":", 1)
    try:
        module = importlib.import_module(module_name)
        symbol = getattr(module, object_name)
    except (ImportError, AttributeError) as error:
        raise ValueError(f"cannot import lowerer {entrypoint}: {error}") from error
    if not isinstance(symbol, type):
        raise ValueError(f"lowerer entrypoint is not a class: {entrypoint}")
    return symbol


def instantiate_lowerer(family: Mapping[str, Any]) -> FamilyLowerer:
    entrypoint = str(family.get("lowerer", ""))
    lowerer_type = resolve_entrypoint(entrypoint)
    lowerer = lowerer_type()
    family_id = str(family["id"])
    if getattr(lowerer, "family_id", None) != family_id:
        raise ValueError(
            f"lowerer {entrypoint} owns {getattr(lowerer, 'family_id', None)!r}, expected {family_id!r}"
        )
    declared = {str(rule) for rule in family["rules"]}
    covered = set(lowerer.covered_rules(family))
    if declared != covered:
        missing = sorted(declared - covered)
        extra = sorted(covered - declared)
        raise ValueError(f"lowerer {entrypoint} rule coverage mismatch: missing={missing}, extra={extra}")
    return lowerer


def validate_lowering_registry(registry: GrammarRegistry | None = None) -> dict[str, Any]:
    registry = registry or load_registry(validate_lowerers=False)
    families: list[dict[str, Any]] = []
    all_rules: set[tuple[str, str]] = set()
    for family in registry.families:
        lowerer = instantiate_lowerer(family)
        rules = tuple(lowerer.covered_rules(family))
        for rule in rules:
            key = (str(family["id"]), rule)
            if key in all_rules:
                raise ValueError(f"duplicate lowering owner for {key[0]}/{key[1]}")
            all_rules.add(key)
        routes = dict(family.get("source_routes", {}))
        unknown_routes = sorted(set(routes) - set(rules))
        if unknown_routes:
            raise ValueError(f"source routes reference unknown rules in {family['id']}: {unknown_routes}")
        for route in routes.values():
            resolve_callable(str(route))
        families.append(
            {
                "family": family["id"],
                "lowerer": family["lowerer"],
                "rules": len(rules),
                "plan_coverage": len(rules),
                "source_route_coverage": len(routes),
            }
        )
    return {
        "schema_version": "vladder-lowering-coverage-v1",
        "status": "pass",
        "grammar_version": registry.version,
        "grammar_sha256": registry.sha256,
        "family_count": len(families),
        "rule_count": len(all_rules),
        "plan_coverage": len(all_rules),
        "source_route_coverage": sum(item["source_route_coverage"] for item in families),
        "families": families,
    }


def resolve_callable(entrypoint: str) -> Any:
    if ":" not in entrypoint:
        raise ValueError(f"backend route must use module:object syntax: {entrypoint}")
    module_name, object_name = entrypoint.split(":", 1)
    try:
        value = getattr(importlib.import_module(module_name), object_name)
    except (ImportError, AttributeError) as error:
        raise ValueError(f"cannot import backend route {entrypoint}: {error}") from error
    if not callable(value):
        raise ValueError(f"backend route is not callable: {entrypoint}")
    return value


class LoweringEngine:
    def __init__(self, registry: GrammarRegistry | None = None) -> None:
        self.registry = registry or load_registry()
        self._lowerers = {
            str(family["id"]): instantiate_lowerer(family) for family in self.registry.families
        }

    def coverage(self) -> dict[str, Any]:
        return validate_lowering_registry(self.registry)

    def inspect(self, family_id: str, rule: str | None = None) -> dict[str, Any]:
        family = self.registry.family(family_id)
        rules = [rule] if rule else list(family["rules"])
        unknown = [item for item in rules if item not in family["rules"]]
        if unknown:
            raise KeyError(f"unknown rules for {family_id}: {unknown}")
        lowerer = self._lowerers[family_id]
        routes = dict(family.get("source_routes", {}))
        return {
            "schema_version": "vladder-lowering-inspection-v1",
            "family": family_id,
            "maturity": family["status"],
            "lowerer": family["lowerer"],
            "rules": [
                {
                    "rule": item,
                    "required_facts": list(lowerer.required_facts(family, item)),
                    "source_route": routes.get(item),
                    "source_emission": "specialized" if item in routes else "plan",
                }
                for item in rules
            ],
        }

    def lower(self, request: LoweringRequest) -> LoweringResult:
        try:
            family = self.registry.family(request.family)
        except KeyError:
            return LoweringResult(LoweringStatus.UNSUPPORTED, None, (f"unknown family: {request.family}",))
        if request.rule not in family["rules"]:
            return LoweringResult(
                LoweringStatus.UNSUPPORTED,
                None,
                (f"unknown rule for {request.family}: {request.rule}",),
            )
        return self._lowerers[request.family].lower(self.registry, family, request)


def canonical_plan_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
