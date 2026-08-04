from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from .lifetime_graph import LifetimeFlowGraph, LifetimeInformation


EVENT_KINDS = {"construct", "publish", "consume", "mutate", "invalidate", "retire", "destroy", "transfer"}


@dataclass(frozen=True)
class LifetimeEvent:
    sequence: int
    timestamp_ns: int
    information_id: str
    semantic_identity: str
    event: str
    scope_instances: dict[str, str]
    mutation: str | None
    equivalence_key: str | None
    placement: str | None
    destination: str | None
    byte_count: int


@dataclass(frozen=True)
class LifetimeAttribution:
    information_id: str
    construction_count: int
    consumer_count: int
    mutation_count: int
    invalidation_count: int
    transfer_count: int
    bytes_materialized: int
    bytes_transferred: int
    minimum_required_realizations: int
    realization_redundancy_ratio: float
    retention_waste_ratio: float
    transfer_redundancy_ratio: float
    observed_scope_instances: dict[str, int]
    observed_placements: tuple[str, ...]
    contract_extension_scopes: tuple[str, ...]
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_lifetime_trace(path: Path | str, graph: LifetimeFlowGraph) -> tuple[LifetimeEvent, ...]:
    path = Path(path)
    events: list[LifetimeEvent] = []
    known_items = {item.id for item in graph.information}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"trace line {line_number} must be an object")
        event = str(raw.get("event", ""))
        information_id = str(raw.get("information_id", ""))
        if event not in EVENT_KINDS:
            raise ValueError(f"trace line {line_number} has unsupported event: {event}")
        if information_id not in known_items:
            raise ValueError(f"trace line {line_number} references unknown information: {information_id}")
        scopes = raw.get("scope_instances")
        if not isinstance(scopes, dict) or not scopes:
            raise ValueError(f"trace line {line_number} requires scope_instances")
        unknown = set(scopes) - set(graph.scopes.scopes)
        if unknown:
            raise ValueError(f"trace line {line_number} uses unknown scopes: {sorted(unknown)}")
        events.append(LifetimeEvent(
            sequence=int(raw.get("sequence", line_number - 1)),
            timestamp_ns=int(raw.get("timestamp_ns", raw.get("sequence", line_number - 1))),
            information_id=information_id,
            semantic_identity=str(raw.get("semantic_identity", "")),
            event=event,
            scope_instances={str(key): str(value) for key, value in scopes.items()},
            mutation=str(raw["mutation"]) if raw.get("mutation") is not None else None,
            equivalence_key=str(raw["equivalence_key"]) if raw.get("equivalence_key") is not None else None,
            placement=str(raw["placement"]) if raw.get("placement") is not None else None,
            destination=str(raw["destination"]) if raw.get("destination") is not None else None,
            byte_count=int(raw.get("byte_count", 0)),
        ))
    if not events:
        raise ValueError("lifetime trace is empty")
    sequences = [event.sequence for event in events]
    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        raise ValueError("trace sequence numbers must be unique and monotonic")
    return tuple(events)


def attribute_lifetimes(graph: LifetimeFlowGraph, events: Iterable[LifetimeEvent]) -> dict[str, LifetimeAttribution]:
    all_events = tuple(events)
    result: dict[str, LifetimeAttribution] = {}
    for item in graph.information:
        item_events = tuple(event for event in all_events if event.information_id == item.id)
        result[item.id] = _attribute_item(graph, item, item_events)
    return result


def _attribute_item(
    graph: LifetimeFlowGraph,
    item: LifetimeInformation,
    events: tuple[LifetimeEvent, ...],
) -> LifetimeAttribution:
    constructs = tuple(event for event in events if event.event == "construct")
    consumes = tuple(event for event in events if event.event == "consume")
    mutations = tuple(event for event in events if event.event == "mutate")
    invalidations = tuple(event for event in events if event.event == "invalidate")
    transfers = tuple(event for event in events if event.event == "transfer")
    diagnostics: list[str] = []

    candidate_scope = _broadest_contract_scope(graph, item)
    scope_instances = {
        event.scope_instances[candidate_scope]
        for event in events
        if candidate_scope in event.scope_instances
    }
    invalidating_transitions = sum(
        1 for event in mutations if event.mutation in item.invalidators
    )
    minimum = max(1, len(scope_instances) + invalidating_transitions)
    actual = len(constructs)
    redundancy = actual / minimum if minimum else 1.0
    if actual == 0:
        diagnostics.append("no construction events observed")

    retention_waste = _retention_waste(events)
    transfer_bytes = sum(max(0, event.byte_count) for event in transfers)
    unique_transfer_bytes = 0
    unique_transfers: set[tuple[str, str | None, str | None, str | None]] = set()
    for event in transfers:
        key = (event.semantic_identity, event.equivalence_key, event.destination, event.placement)
        if key not in unique_transfers:
            unique_transfers.add(key)
            unique_transfer_bytes += max(0, event.byte_count)
    transfer_redundancy = transfer_bytes / unique_transfer_bytes if unique_transfer_bytes else 1.0

    observed_scopes = {
        scope: len({event.scope_instances[scope] for event in events if scope in event.scope_instances})
        for scope in graph.scopes.scopes
        if any(scope in event.scope_instances for event in events)
    }
    placements = tuple(sorted({event.placement for event in events if event.placement}))
    bytes_materialized = sum(max(0, event.byte_count or item.byte_size) for event in constructs)
    return LifetimeAttribution(
        item.id,
        actual,
        len(consumes),
        len(mutations),
        len(invalidations),
        len(transfers),
        bytes_materialized,
        transfer_bytes,
        minimum,
        redundancy,
        retention_waste,
        transfer_redundancy,
        observed_scopes,
        placements,
        item.candidate_scopes,
        tuple(diagnostics),
    )


def _broadest_contract_scope(graph: LifetimeFlowGraph, item: LifetimeInformation) -> str:
    candidates = list(item.candidate_scopes)
    for candidate in candidates:
        if all(graph.scopes.contains(candidate, other) for other in candidates):
            return candidate
    return item.current.scope


def _retention_waste(events: tuple[LifetimeEvent, ...]) -> float:
    by_identity: dict[str, list[LifetimeEvent]] = {}
    for event in events:
        by_identity.setdefault(event.semantic_identity, []).append(event)
    residency = 0
    waste = 0
    for identity_events in by_identity.values():
        constructs = [event.timestamp_ns for event in identity_events if event.event == "construct"]
        retires = [event.timestamp_ns for event in identity_events if event.event in {"retire", "destroy"}]
        consumes = [event.timestamp_ns for event in identity_events if event.event == "consume"]
        if not constructs or not retires:
            continue
        start = min(constructs)
        end = max(retires)
        last_use = max(consumes) if consumes else start
        residency += max(0, end - start)
        waste += max(0, end - last_use)
    return waste / residency if residency else 0.0


def attribution_report(attribution: dict[str, LifetimeAttribution]) -> dict[str, Any]:
    return {
        "schema_version": "vladder-lifetime-attribution-v1",
        "items": {key: value.to_dict() for key, value in sorted(attribution.items())},
        "summary": {
            "repeated_realization_items": sum(item.realization_redundancy_ratio > 1.0 for item in attribution.values()),
            "over_retained_items": sum(item.retention_waste_ratio >= 0.5 for item in attribution.values()),
            "redundant_transfer_items": sum(item.transfer_redundancy_ratio > 1.0 for item in attribution.values()),
        },
        "semantic_authority": "manifest",
        "trace_role": "cost-and-observed-reuse-only",
    }
