from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class OperatorContract:
    path: Path
    data: dict[str, Any]
    canonical_json: str
    contract_hash: str

    @property
    def name(self) -> str:
        return str(self.data["operator"])

    @property
    def entrypoint(self) -> str:
        return str(self.data.get("entrypoint", self.name))

    @property
    def language(self) -> str:
        return str(self.data.get("language", "c17"))

    @property
    def output_parameter_indices(self) -> tuple[int, ...]:
        indices: set[int] = set()
        for section in ("outputs", "state"):
            values = self.data.get(section, {})
            if isinstance(values, dict):
                for value in values.values():
                    if isinstance(value, dict) and "param_index" in value:
                        indices.add(int(value["param_index"]))
        return tuple(sorted(indices))

    def to_dict(self) -> dict[str, Any]:
        return {"path": str(self.path), "contract_hash": self.contract_hash, "contract": self.data}


def load_contract(path: Path) -> OperatorContract:
    try:
        parsed = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot load contract {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ContractError("contract root must be a mapping")
    data = _canonicalize(parsed)
    errors = validate_contract(data)
    if errors:
        raise ContractError("invalid operator contract:\n- " + "\n- ".join(errors))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return OperatorContract(path.resolve(), data, canonical, digest)


def validate_contract(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("operator", "inputs", "outputs", "semantics", "distribution", "objective", "constraints", "graph"):
        if key not in data:
            errors.append(f"missing required field: {key}")
    if data.get("language", "c17") not in {"c17", "restricted-c++20"}:
        errors.append("language must be c17 or restricted-c++20")
    for section in ("inputs", "outputs"):
        if section in data and (not isinstance(data[section], dict) or not data[section]):
            errors.append(f"{section} must be a non-empty mapping")
    semantics = data.get("semantics", {})
    if isinstance(semantics, dict):
        if semantics.get("allocation") != "forbidden":
            errors.append("semantics.allocation must be forbidden")
        if semantics.get("io") != "forbidden":
            errors.append("semantics.io must be forbidden")
        has_float = any(_contains_float(v) for section in (data.get("inputs", {}), data.get("outputs", {})) for v in (section.values() if isinstance(section, dict) else []))
        if has_float and "floating_point" not in semantics:
            errors.append("floating-point streams require semantics.floating_point")
        fp = semantics.get("floating_point")
        if isinstance(fp, dict):
            fp_class = fp.get("class")
            if fp_class not in {"bitwise", "ieee_order", "deterministic_tolerance", "distributional_tolerance"}:
                errors.append("floating_point.class is invalid")
            if fp_class in {"deterministic_tolerance", "distributional_tolerance"}:
                for bound in ("max_abs", "max_rel"):
                    if bound not in fp:
                        errors.append(f"tolerance mode requires floating_point.{bound}")
    else:
        errors.append("semantics must be a mapping")
    objective = data.get("objective", {})
    if not isinstance(objective, dict) or "primary" not in objective:
        errors.append("objective.primary is required")
    constraints = data.get("constraints", {})
    if not isinstance(constraints, dict):
        errors.append("constraints must be a mapping")
    else:
        for field in ("max_code_growth_percent", "max_stack_bytes"):
            if field not in constraints:
                errors.append(f"constraints.{field} is required")
            elif not isinstance(constraints[field], (int, float)) or constraints[field] < 0:
                errors.append(f"constraints.{field} must be non-negative")
    state = data.get("state", {})
    if state and not isinstance(state, dict):
        errors.append("state must be a mapping")
    elif isinstance(state, dict):
        for name, spec in state.items():
            if not isinstance(spec, dict) or spec.get("ownership") not in {"single_threaded", "spsc"}:
                errors.append(f"state {name} requires single_threaded or spsc ownership")
    distribution = data.get("distribution", {})
    if not isinstance(distribution, dict) or not distribution:
        errors.append("distribution must be a non-empty mapping")
    seen_params: dict[int, str] = {}
    for section_name in ("inputs", "scratch", "outputs", "state"):
        section = data.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for name, spec in section.items():
            if isinstance(spec, dict) and "param_index" in spec:
                index = int(spec["param_index"])
                if index in seen_params:
                    errors.append(f"parameter index {index} is shared by {seen_params[index]} and {section_name}.{name}")
                seen_params[index] = f"{section_name}.{name}"
    specializations = data.get("specializations", {})
    if specializations and not isinstance(specializations, dict):
        errors.append("specializations must be a mapping")
    elif isinstance(specializations, dict):
        for name, fact in specializations.items():
            if not isinstance(fact, dict) or fact.get("enforcement") not in {"guard", "precondition"}:
                errors.append(f"specialization {name} requires enforcement guard or precondition")
    graph = data.get("graph", {})
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        errors.append("graph requires nodes and edges lists")
    return errors


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ContractError(f"unsupported contract value: {type(value).__name__}")


def _contains_float(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_float(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_float(v) for v in value)
    return isinstance(value, str) and value in {"f16", "bf16", "f32", "f64", "float", "double"}
