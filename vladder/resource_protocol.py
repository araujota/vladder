from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from z3 import BoolVal, Solver, sat


RESOURCE_PROTOCOL_SCHEMA = "vladder-finite-resource-protocol-v1"


@dataclass(frozen=True)
class ResourceTransition:
    id: str
    resource: str
    source: str
    target: str
    event: str
    guards: tuple[str, ...]
    effects: tuple[str, ...]
    outcome: str
    external_boundary: bool
    atomic: bool
    rollback_to: str | None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ResourceTransition":
        required = ("id", "resource", "from", "to", "event")
        missing = [key for key in required if not value.get(key)]
        if missing:
            raise ValueError(f"resource transition is missing: {', '.join(missing)}")
        return cls(
            str(value["id"]), str(value["resource"]), str(value["from"]),
            str(value["to"]), str(value["event"]),
            tuple(sorted(str(item) for item in value.get("guards", ()))),
            tuple(sorted(str(item) for item in value.get("effects", ()))),
            str(value.get("outcome", "success")),
            bool(value.get("external_boundary", False)),
            bool(value.get("atomic", False)),
            str(value["rollback_to"]) if value.get("rollback_to") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "resource": self.resource, "from": self.source,
            "to": self.target, "event": self.event, "guards": list(self.guards),
            "effects": list(self.effects), "outcome": self.outcome,
            "external_boundary": self.external_boundary, "atomic": self.atomic,
            "rollback_to": self.rollback_to,
        }


def verify_resource_protocol(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or raw.get("protocol") != "finite_resource":
        raise ValueError("finite resource manifest requires protocol: finite_resource")
    resources = raw.get("resources")
    if not isinstance(resources, dict) or not resources:
        raise ValueError("finite resource manifest requires a resources mapping")
    transitions = tuple(
        ResourceTransition.from_mapping(item)
        for item in raw.get("transitions", ())
        if isinstance(item, dict)
    )
    obligations: list[dict[str, Any]] = []
    smt_parts: list[str] = []

    def check(identifier: str, valid: bool, detail: Any = None) -> None:
        solver = Solver()
        solver.add(BoolVal(not valid))
        result = solver.check()
        obligations.append({
            "id": identifier,
            "status": "PROVED" if result != sat else "FAIL",
            "solver_result": str(result).upper(),
            "detail": detail,
        })
        smt_parts.append(f"; {identifier}\n{solver.to_smt2()}")

    state_sets: dict[str, set[str]] = {}
    initials: dict[str, str] = {}
    terminals: dict[str, set[str]] = {}
    for name, descriptor in resources.items():
        if not isinstance(descriptor, dict):
            raise ValueError(f"resource {name!r} must be a mapping")
        states = {str(item) for item in descriptor.get("states", ())}
        initial = str(descriptor.get("initial", ""))
        terminal = {str(item) for item in descriptor.get("terminal", ())}
        state_sets[str(name)] = states
        initials[str(name)] = initial
        terminals[str(name)] = terminal
        check(f"resource.{name}.state-domain", bool(states) and initial in states and terminal <= states)

    ids = [item.id for item in transitions]
    check("transition.identities-unique", len(ids) == len(set(ids)))
    endpoints = all(
        item.resource in state_sets
        and item.source in state_sets[item.resource]
        and item.target in state_sets[item.resource]
        and (item.rollback_to is None or item.rollback_to in state_sets[item.resource])
        for item in transitions
    )
    check("transition.endpoints-typed", endpoints)

    reachable: dict[str, set[str]] = {name: {initial} for name, initial in initials.items()}
    changed = True
    while changed:
        changed = False
        for item in transitions:
            if item.resource in reachable and item.source in reachable[item.resource]:
                before = len(reachable[item.resource])
                reachable[item.resource].add(item.target)
                if item.rollback_to:
                    reachable[item.resource].add(item.rollback_to)
                changed |= len(reachable[item.resource]) != before
    unreachable = {
        name: sorted(states - reachable.get(name, set()))
        for name, states in state_sets.items() if states - reachable.get(name, set())
    }
    check("protocol.reachable-state-coverage", not unreachable, unreachable)

    reads_after_terminal = [
        item.id for item in transitions
        if item.source in terminals.get(item.resource, set())
        and any(effect in {"read", "acquire", "reuse", "publish"} for effect in item.effects)
    ]
    check("protocol.no-use-after-retire", not reads_after_terminal, reads_after_terminal)

    publication = [item for item in transitions if "publish" in item.effects]
    check(
        "protocol.publication-atomic",
        all(item.atomic for item in publication),
        [item.id for item in publication if not item.atomic],
    )
    rollback = [item for item in transitions if item.outcome in {"failure", "cancelled"}]
    check(
        "protocol.failure-rollback-explicit",
        all(item.rollback_to is not None or item.target in terminals.get(item.resource, set()) for item in rollback),
        [item.id for item in rollback if item.rollback_to is None],
    )
    external = [item for item in transitions if item.external_boundary]
    check(
        "protocol.external-boundaries-call-preserving",
        all("external-internals-opaque" in item.effects for item in external),
        [item.id for item in external if "external-internals-opaque" not in item.effects],
    )

    order = raw.get("happens_before", ())
    event_ids = set(ids)
    malformed_order = [
        item for item in order
        if not isinstance(item, list) or len(item) != 2
        or str(item[0]) not in event_ids or str(item[1]) not in event_ids
    ]
    graph = {identifier: set() for identifier in ids}
    for item in order:
        if isinstance(item, list) and len(item) == 2 and not malformed_order:
            graph[str(item[0])].add(str(item[1]))
    visiting: set[str] = set()
    visited: set[str] = set()

    def cyclic(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(cyclic(other) for other in graph.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    has_cycle = any(cyclic(node) for node in graph) if not malformed_order else True
    check("protocol.happens-before-well-formed", not malformed_order and not has_cycle, malformed_order)

    payload = {
        "schema_version": RESOURCE_PROTOCOL_SCHEMA,
        "manifest": str(manifest_path),
        "resources": resources,
        "transitions": [item.to_dict() for item in transitions],
        "reachable_states": {key: sorted(value) for key, value in reachable.items()},
        "obligations": obligations,
        "status": "PASS" if all(item["status"] == "PROVED" for item in obligations) else "FAIL",
        "proof_method": "bounded finite-state reachability and Z3 structural obligations",
        "claim_boundary": (
            "declared resource states, outcomes, publication, rollback, retirement, and happens-before; "
            "external implementation internals and physical timing are excluded"
        ),
    }
    payload["protocol_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    smt_path = output_directory / "resource-protocol.smt2"
    report_path = output_directory / "resource-protocol-proof.json"
    smt_path.write_text("\n".join(smt_parts))
    payload["artifact"] = str(smt_path)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def protocol_template(kind: str) -> dict[str, Any]:
    templates = {
        "publication": _publication_template,
        "queue": _queue_template,
        "socket": _socket_template,
        "device": _device_template,
    }
    try:
        return templates[kind]()
    except KeyError as error:
        raise ValueError(f"unknown protocol template {kind!r}; expected {sorted(templates)}") from error


def _publication_template() -> dict[str, Any]:
    return {
        "protocol": "finite_resource",
        "resources": {"generation": {"states": ["private", "published", "retired"], "initial": "private", "terminal": ["retired"]}},
        "transitions": [
            {"id": "publish", "resource": "generation", "from": "private", "to": "published", "event": "commit", "effects": ["publish"], "atomic": True},
            {"id": "retire", "resource": "generation", "from": "published", "to": "retired", "event": "last-reader", "guards": ["reader_count == 0"], "effects": ["retire"]},
        ],
        "happens_before": [["publish", "retire"]],
    }


def _queue_template() -> dict[str, Any]:
    return {
        "protocol": "finite_resource",
        "resources": {"slot": {"states": ["free", "reserved", "published", "consumed"], "initial": "free", "terminal": ["consumed"]}},
        "transitions": [
            {"id": "reserve", "resource": "slot", "from": "free", "to": "reserved", "event": "producer-reserve", "effects": ["acquire"]},
            {"id": "publish", "resource": "slot", "from": "reserved", "to": "published", "event": "release-store", "effects": ["publish"], "atomic": True},
            {"id": "consume", "resource": "slot", "from": "published", "to": "consumed", "event": "acquire-load", "effects": ["read", "retire"]},
        ],
        "happens_before": [["reserve", "publish"], ["publish", "consume"]],
    }


def _socket_template() -> dict[str, Any]:
    return {
        "protocol": "finite_resource",
        "resources": {"batch": {"states": ["owned", "in_call", "complete", "failed"], "initial": "owned", "terminal": ["complete", "failed"]}},
        "transitions": [
            {"id": "submit", "resource": "batch", "from": "owned", "to": "in_call", "event": "sendmmsg/recvmmsg", "effects": ["external-internals-opaque"], "external_boundary": True},
            {"id": "partial", "resource": "batch", "from": "in_call", "to": "owned", "event": "partial-success", "effects": ["refresh"]},
            {"id": "complete", "resource": "batch", "from": "in_call", "to": "complete", "event": "all-complete", "effects": ["retire"]},
            {"id": "error", "resource": "batch", "from": "in_call", "to": "failed", "event": "errno", "effects": ["external-internals-opaque"], "external_boundary": True, "outcome": "failure"},
        ],
        "happens_before": [["submit", "partial"], ["submit", "complete"], ["submit", "error"]],
    }


def _device_template() -> dict[str, Any]:
    return {
        "protocol": "finite_resource",
        "resources": {"resource": {"states": ["host-owned", "submitted", "device-visible", "retired"], "initial": "host-owned", "terminal": ["retired"]}},
        "transitions": [
            {"id": "submit", "resource": "resource", "from": "host-owned", "to": "submitted", "event": "queue-submit", "effects": ["external-internals-opaque"], "external_boundary": True},
            {"id": "visible", "resource": "resource", "from": "submitted", "to": "device-visible", "event": "signal", "effects": ["publish"], "atomic": True},
            {"id": "retire", "resource": "resource", "from": "device-visible", "to": "retired", "event": "completion", "effects": ["retire"]},
        ],
        "happens_before": [["submit", "visible"], ["visible", "retire"]],
    }
