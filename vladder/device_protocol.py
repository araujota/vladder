from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import yaml
from z3 import BoolVal, Int, Solver, sat

from .language_adapter import (
    ProtocolTransition,
    SemanticEffect,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    file_sha256,
    obligation,
)


DEVICE_PROTOCOL_SCHEMA_VERSION = "device-protocol-graph-v1"
SUPPORTED_DEVICE_PROTOCOLS = frozenset({"queue", "dma", "presentation"})


@dataclass(frozen=True)
class ProtocolIssue:
    id: str
    category: str
    message: str
    counterexample: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeviceProtocolEvidence:
    kind: str
    manifest: str
    graph: SemanticFlowGraph
    status: str
    obligations: tuple[dict[str, Any], ...]
    issues: tuple[ProtocolIssue, ...]
    artifacts: dict[str, str]
    proof_scope: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DEVICE_PROTOCOL_SCHEMA_VERSION,
            "kind": self.kind,
            "manifest": self.manifest,
            "graph": self.graph.to_dict(),
            "status": self.status,
            "obligations": list(self.obligations),
            "issues": [item.to_dict() for item in self.issues],
            "artifacts": self.artifacts,
            "proof_method": "bounded event/state verification with Z3 witness checks",
            "proof_scope": self.proof_scope,
        }


def verify_device_protocol(manifest_path: Path, output_directory: Path) -> DeviceProtocolEvidence:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("device protocol manifest must be a mapping")
    kind = str(raw.get("kind", ""))
    if kind not in SUPPORTED_DEVICE_PROTOCOLS:
        raise ValueError(f"unsupported device protocol {kind!r}; expected {sorted(SUPPORTED_DEVICE_PROTOCOLS)}")
    if kind == "queue":
        graph, obligations, issues, smt = _verify_queue(raw, manifest_path)
        scope = "declared finite submissions, resources, stage/access scopes, queue ownership, and semaphore values"
    elif kind == "dma":
        graph, obligations, issues, smt = _verify_dma(raw, manifest_path)
        scope = "declared devices, links, registration, transfer ordering, completion, publication, and reuse"
    else:
        graph, obligations, issues, smt = _verify_presentation(raw, manifest_path)
        scope = "declared images and acquire-render-present-scanout-release event sequences"
    smt_path = output_directory / "protocol-obligations.smt2"
    graph_path = output_directory / "device-protocol-graph.json"
    smt_path.write_text(smt)
    graph_path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n")
    evidence = DeviceProtocolEvidence(
        kind,
        str(manifest_path),
        graph,
        "PASS" if not issues and all(item["status"] == "PROVED" for item in obligations) else "FAIL",
        tuple(obligations),
        tuple(issues),
        {"graph": str(graph_path), "smt2": str(smt_path)},
        scope + "; driver, firmware, device loss, and undeclared external actors remain integration obligations",
    )
    (output_directory / "device-protocol-proof.json").write_text(json.dumps(evidence.to_dict(), indent=2, sort_keys=True) + "\n")
    return evidence


def _prove_fact(identifier: str, fact: bool, detail: dict[str, Any]) -> tuple[dict[str, Any], str]:
    solver = Solver()
    solver.add(BoolVal(not fact))
    result = solver.check()
    model = {str(key): str(solver.model()[key]) for key in solver.model()} if result == sat else {}
    return ({
        "id": identifier,
        "status": "FAIL" if result == sat else "PROVED",
        "solver_result": str(result).upper(),
        "detail": detail,
        "counterexample": model,
    }, solver.to_smt2())


def _base_node(identifier: str, kind: str, operation: str, inputs: tuple[str, ...], attributes: dict[str, Any], native: str) -> SemanticFlowNode:
    return SemanticFlowNode(
        identifier,
        kind,
        operation,
        inputs,
        "protocol-state",
        attributes,
        {"adapter": DEVICE_PROTOCOL_SCHEMA_VERSION, "native_construct": native},
        (),
    )


def _graph(
    *,
    name: str,
    kind: str,
    manifest_path: Path,
    nodes: list[SemanticFlowNode],
    contracts: dict[str, Any],
    obligations: tuple[Any, ...],
    effects: tuple[SemanticEffect, ...],
    protocols: tuple[ProtocolTransition, ...],
) -> SemanticFlowGraph:
    edges: list[SemanticFlowEdge] = []
    for node in nodes:
        for ordinal, source in enumerate(node.inputs):
            edges.append(SemanticFlowEdge(
                f"{source}->{node.id}:{ordinal}", source, node.id, "protocol-state",
                "external-device", "protocol-resource", "event-sequence", "declared-happens-before",
                realization=kind, memory_region="external-device", validity_scope="declared-protocol-run",
            ))
    return SemanticFlowGraph(
        name,
        "heterogeneous-protocol",
        "manifest",
        DEVICE_PROTOCOL_SCHEMA_VERSION,
        file_sha256(manifest_path),
        tuple(nodes),
        tuple(edges),
        contracts,
        ("driver implementation", "firmware scheduling", "undeclared external actors", "device-loss behavior unless explicitly modeled"),
        obligations,
        effects,
        protocols,
    )


def _verify_queue(raw: dict[str, Any], manifest_path: Path) -> tuple[SemanticFlowGraph, list[dict[str, Any]], list[ProtocolIssue], str]:
    operations = raw.get("operations", [])
    resources = raw.get("resources", [])
    barriers = raw.get("barriers", [])
    semaphore_types = {
        str(item["id"]): str(item.get("type", "timeline")).lower()
        for item in raw.get("semaphores", [])
        if isinstance(item, dict) and "id" in item
    }
    invalid_semaphore_types = {
        identifier: kind for identifier, kind in semaphore_types.items()
        if kind not in {"binary", "timeline"}
    }
    if invalid_semaphore_types:
        raise ValueError(f"unsupported queue semaphore types: {invalid_semaphore_types}")
    if not isinstance(operations, list) or not operations:
        raise ValueError("queue protocol requires a non-empty operations list")
    resource_ids = {str(item["id"]) for item in resources if isinstance(item, dict) and "id" in item}
    operation_ids = [str(item.get("id", "")) for item in operations]
    if any(not item for item in operation_ids) or len(operation_ids) != len(set(operation_ids)):
        raise ValueError("queue operation identifiers must be non-empty and unique")
    index = {identifier: ordinal for ordinal, identifier in enumerate(operation_ids)}
    signals: dict[str, list[tuple[int, int, str]]] = {}
    for ordinal, operation in enumerate(operations):
        for signal in operation.get("signals", []):
            signals.setdefault(str(signal["semaphore"]), []).append((ordinal, int(signal.get("value", 1)), operation_ids[ordinal]))
    execution_edges: set[tuple[str, str]] = set()
    last_operation_by_queue: dict[str, str] = {}
    for operation in operations:
        queue = str(operation.get("queue", ""))
        operation_id = str(operation["id"])
        previous = last_operation_by_queue.get(queue)
        if previous is not None:
            execution_edges.add((previous, operation_id))
        last_operation_by_queue[queue] = operation_id
    semaphore_resources: set[tuple[str, str, str]] = set()
    timeline_checks: list[tuple[str, bool, dict[str, Any]]] = []
    device_binding = raw.get("device_binding")
    if device_binding is not None:
        if not isinstance(device_binding, dict):
            raise ValueError("queue device_binding must be a mapping")
        queue_families = {
            int(item["index"]): item
            for item in device_binding.get("queue_families", [])
            if isinstance(item, dict) and "index" in item
        }
        timeline_checks.extend((
            (
                "queue.binding.identity",
                bool(device_binding.get("topology_hash")) and bool(device_binding.get("device_uuid")),
                {"topology_hash": device_binding.get("topology_hash"), "device_uuid": device_binding.get("device_uuid")},
            ),
            (
                "queue.binding.synchronization2",
                not bool(raw.get("requires_synchronization2", False)) or bool(device_binding.get("synchronization2", False)),
                {"required": bool(raw.get("requires_synchronization2", False)), "supported": device_binding.get("synchronization2")},
            ),
        ))
        uses_timeline = any(
            semaphore_types.get(str(event.get("semaphore")), "timeline") == "timeline"
            for operation in operations
            for event in [*operation.get("signals", []), *operation.get("waits", [])]
        )
        timeline_checks.append((
            "queue.binding.timeline",
            not uses_timeline or bool(device_binding.get("timeline_semaphore", False)),
            {"used": uses_timeline, "supported": device_binding.get("timeline_semaphore")},
        ))
        for operation in operations:
            family_index = operation.get("queue_family_index")
            if family_index is None:
                timeline_checks.append((
                    f"queue.binding.family.{operation.get('id')}", False,
                    {"reason": "queue_family_index missing from a physically bound operation"},
                ))
                continue
            family = queue_families.get(int(family_index))
            required = _required_queue_capabilities(operation)
            flags = set(map(str, family.get("flags", []))) if family else set()
            queue_index = int(operation.get("queue_index", 0))
            valid = bool(family) and required.issubset(flags) and 0 <= queue_index < int(family.get("queue_count", 0))
            timeline_checks.append((
                f"queue.binding.family.{operation.get('id')}", valid,
                {
                    "family_index": family_index, "queue_index": queue_index,
                    "required_capabilities": sorted(required), "observed_family": family,
                },
            ))
    for semaphore, values in sorted(signals.items()):
        if semaphore_types.get(semaphore, "timeline") != "timeline":
            continue
        monotonic = all(left[1] < right[1] for left, right in zip(values, values[1:]))
        timeline_checks.append((
            f"queue.timeline.signal.{semaphore}",
            monotonic,
            {"signals": values, "requirement": "strictly increasing timeline values"},
        ))
    binary_state: dict[str, tuple[int, str] | None] = {
        identifier: None for identifier, kind in semaphore_types.items() if kind == "binary"
    }
    for ordinal, operation in enumerate(operations):
        for wait in operation.get("waits", []):
            semaphore = str(wait["semaphore"])
            kind = semaphore_types.get(semaphore, "timeline")
            if kind == "binary":
                producer = binary_state.get(semaphore)
                valid = producer is not None and producer[0] < ordinal
                timeline_checks.append((
                    f"queue.binary.wait.{operation_ids[ordinal]}.{semaphore}", valid,
                    {"available_signal": producer, "requirement": "one prior unconsumed signal"},
                ))
                if valid and producer is not None:
                    execution_edges.add((producer[1], operation_ids[ordinal]))
                    for resource in wait.get("resources", []):
                        semaphore_resources.add((producer[1], operation_ids[ordinal], str(resource)))
                    binary_state[semaphore] = None
                continue
            value = int(wait.get("value", 1))
            producers = [item for item in signals.get(semaphore, []) if item[0] < ordinal and item[1] >= value]
            valid = bool(producers)
            timeline_checks.append((f"queue.timeline.{operation_ids[ordinal]}.{semaphore}", valid, {"wait_value": value, "candidate_signals": producers}))
            if valid:
                producer = max(producers, key=lambda item: item[0])
                execution_edges.add((producer[2], operation_ids[ordinal]))
                for resource in wait.get("resources", []):
                    semaphore_resources.add((producer[2], operation_ids[ordinal], str(resource)))
        for signal in operation.get("signals", []):
            semaphore = str(signal["semaphore"])
            if semaphore_types.get(semaphore, "timeline") != "binary":
                continue
            available = binary_state.get(semaphore)
            valid = available is None
            timeline_checks.append((
                f"queue.binary.signal.{operation_ids[ordinal]}.{semaphore}", valid,
                {"outstanding_signal": available, "requirement": "binary signal must be consumed before re-signal"},
            ))
            if valid:
                binary_state[semaphore] = (ordinal, operation_ids[ordinal])
    closure = _transitive_closure(operation_ids, execution_edges)
    barrier_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in barriers:
        if isinstance(item, dict):
            barrier_by_key.setdefault(
                (str(item.get("src")), str(item.get("dst")), str(item.get("resource"))), []
            ).append(item)
    accesses: list[tuple[int, str, str, str, str]] = []
    issues: list[ProtocolIssue] = []
    for ordinal, operation in enumerate(operations):
        for access in operation.get("accesses", []):
            resource = str(access["resource"])
            if resource_ids and resource not in resource_ids:
                issues.append(ProtocolIssue(f"queue.resource.{operation_ids[ordinal]}.{resource}", "unknown_resource", "operation references an undeclared resource", {"operation": operation_ids[ordinal], "resource": resource}))
            accesses.append((ordinal, operation_ids[ordinal], resource, str(access["mode"]).lower(), str(access.get("stage", "unspecified"))))
    obligations: list[dict[str, Any]] = []
    smt_parts: list[str] = []
    for identifier, valid, detail in timeline_checks:
        proof, smt = _prove_fact(identifier, valid, detail)
        obligations.append(proof); smt_parts.append(smt)
        if not valid:
            category = "binary_semaphore" if ".binary." in identifier else "timeline"
            message = (
                "binary semaphore signal/wait state is invalid"
                if category == "binary_semaphore"
                else "wait has no preceding signal at the required timeline value"
            )
            issues.append(ProtocolIssue(identifier, category, message, detail))
    for left_index, left_id, resource, left_mode, left_stage in accesses:
        for right_index, right_id, right_resource, right_mode, right_stage in accesses:
            left_reads, left_writes = "read" in left_mode, "write" in left_mode
            right_reads, right_writes = "read" in right_mode, "write" in right_mode
            if right_index <= left_index or resource != right_resource or not (left_writes or right_writes):
                continue
            hazard = "RAW" if left_writes and right_reads else ("WAR" if left_reads and right_writes else "WAW")
            ordered = (left_id, right_id) in closure
            visibility_required = hazard == "RAW"
            matching_barriers = barrier_by_key.get((left_id, right_id, resource), [])
            scoped_barriers = [
                item for item in matching_barriers
                if _scope_covers(item.get("src_stage"), left_stage)
                and _scope_covers(item.get("dst_stage"), right_stage)
                and _access_covers(item.get("src_access"), left_mode)
                and _access_covers(item.get("dst_access"), right_mode)
            ]
            visible = bool(scoped_barriers) or (left_id, right_id, resource) in semaphore_resources
            valid = ordered and (visible or not visibility_required)
            identifier = f"queue.hazard.{left_id}.{right_id}.{resource}"
            detail = {
                "hazard": hazard,
                "producer_stage": left_stage,
                "consumer_stage": right_stage,
                "execution_dependency": ordered,
                "memory_visibility": visible,
                "visibility_required": visibility_required,
                "matching_barriers": matching_barriers,
                "scope_covering_barriers": scoped_barriers,
            }
            proof, smt = _prove_fact(identifier, valid, detail)
            obligations.append(proof); smt_parts.append(smt)
            if not valid:
                issues.append(ProtocolIssue(identifier, "hazard", "resource hazard lacks sufficient execution or memory dependency", detail))
    ownership = {str(item["id"]): str(item.get("owner", "shared")) for item in resources if isinstance(item, dict) and "id" in item}
    for operation in operations:
        queue_family = str(operation.get("queue_family", operation.get("queue", "shared")))
        for access in operation.get("accesses", []):
            resource = str(access["resource"])
            owner = ownership.get(resource, "shared")
            transfers = [
                item for item in barriers
                if str(item.get("resource")) == resource
                and str(item.get("ownership_from")) == owner
                and str(item.get("ownership_to")) == queue_family
                and str(item.get("dst")) in index
                and (
                    str(item.get("dst")) == str(operation["id"])
                    or (str(item.get("dst")), str(operation["id"])) in closure
                )
            ]
            if owner not in {"shared", queue_family} and not transfers:
                detail = {"resource": resource, "owner": owner, "consumer_queue_family": queue_family}
                identifier = f"queue.ownership.{operation['id']}.{resource}"
                proof, smt = _prove_fact(identifier, False, detail)
                obligations.append(proof); smt_parts.append(smt)
                issues.append(ProtocolIssue(identifier, "ownership", "resource is used by a queue family without an ownership transfer", detail))
    nodes: list[SemanticFlowNode] = [_base_node("initial", "Input", "queue-protocol-start", (), {}, "VkQueue/device-state")]
    previous = "initial"
    for operation in operations:
        operation_id = str(operation["id"])
        node_id = f"submit.{operation_id}"
        nodes.append(_base_node(node_id, "QueueSubmit", "queue-operation", (previous,), dict(operation), "vkQueueSubmit2/command-buffer"))
        for wait_index, wait in enumerate(operation.get("waits", [])):
            wait_id = f"wait.{operation_id}.{wait_index}"
            nodes.append(_base_node(wait_id, "SemaphoreWait", "timeline-wait", (node_id,), dict(wait), "VkSemaphoreSubmitInfo.wait"))
        for signal_index, signal in enumerate(operation.get("signals", [])):
            signal_id = f"signal.{operation_id}.{signal_index}"
            nodes.append(_base_node(signal_id, "SemaphoreSignal", "timeline-signal", (node_id,), dict(signal), "VkSemaphoreSubmitInfo.signal"))
        previous = node_id
    for ordinal, barrier in enumerate(barriers):
        src = f"submit.{barrier.get('src')}" if str(barrier.get("src")) in index else "initial"
        nodes.append(_base_node(f"barrier.{ordinal}", "Barrier", "execution-memory-dependency", (src,), dict(barrier), "VkDependencyInfo/Vk*MemoryBarrier2"))
    nodes.append(_base_node("output", "Output", "queue-protocol-complete", (previous,), {}, "queue-completion"))
    hazard_obligation = obligation("queue.hazards.complete", "synchronization", "all declared resource hazards have sufficient dependencies", scope="bounded-queue-trace", proof_method="Z3 fact obligations plus dependency closure", native_construct="Vulkan synchronization2")
    timeline_obligation = obligation("queue.timeline.monotonic", "state", "every timeline wait is satisfied by an earlier signal value", scope="bounded-queue-trace", proof_method="Z3 integer/fact obligations", native_construct="timeline semaphore")
    binary_obligation = obligation("queue.binary.lifecycle", "state", "binary semaphore signals are consumed exactly once before re-signal", scope="bounded-queue-trace", proof_method="bounded semaphore state machine", native_construct="binary semaphore")
    graph = _graph(
        name=str(raw.get("name", "queue-protocol")), kind="queue", manifest_path=manifest_path,
        nodes=nodes,
        contracts={
            "resources": resources, "operation_ids": operation_ids, "barriers": barriers,
            "device_binding": device_binding, "semaphores": raw.get("semaphores", []),
        },
        obligations=(hazard_obligation, timeline_obligation, binary_obligation),
        effects=(SemanticEffect("queue.sync", "Synchronize", "submit", "device-queues", "declared-resource-results", "queue-and-semaphore-order", tuple(node.id for node in nodes if node.kind in {"QueueSubmit", "Barrier", "SemaphoreWait", "SemaphoreSignal"}), ("queue.hazards.complete", "queue.timeline.monotonic", "queue.binary.lifecycle")),),
        protocols=(ProtocolTransition("queue.submit", "Queue", "recorded", "submit/wait/signal", "complete", "all declared waits and hazards pass", ("queue.hazards.complete", "queue.timeline.monotonic", "queue.binary.lifecycle"), {"api": "Vulkan synchronization2"}),),
    )
    return graph, obligations, issues, "\n; ---- obligation ----\n".join(smt_parts)


def _scope_covers(declared: Any, actual: str) -> bool:
    if isinstance(declared, list):
        scopes = {str(item).lower() for item in declared}
    elif declared is None:
        return False
    else:
        scopes = {item.strip().lower() for item in str(declared).split("|") if item.strip()}
    return bool(scopes & {actual.lower(), "all", "all_commands", "all_graphics"})


def _required_queue_capabilities(operation: dict[str, Any]) -> set[str]:
    explicit = operation.get("required_capabilities")
    if explicit:
        return {str(item).lower() for item in explicit}
    stages = " ".join(str(item.get("stage", "")) for item in operation.get("accesses", [])).lower()
    required: set[str] = set()
    if any(token in stages for token in ("compute", "ray_tracing")):
        required.add("compute")
    if any(token in stages for token in ("graphics", "vertex", "fragment", "color", "depth")):
        required.add("graphics")
    if any(token in stages for token in ("transfer", "copy", "blit", "resolve")):
        required.add("transfer")
    return required or {"transfer"}


def _access_covers(declared: Any, mode: str) -> bool:
    if isinstance(declared, list):
        accesses = {str(item).lower() for item in declared}
    elif declared is None:
        return False
    else:
        accesses = {item.strip().lower() for item in str(declared).split("|") if item.strip()}
    required = {kind for kind in ("read", "write") if kind in mode.lower()}
    return bool(required) and ("all" in accesses or all(
        any(kind in access for access in accesses) for kind in required
    ))


def _verify_dma(raw: dict[str, Any], manifest_path: Path) -> tuple[SemanticFlowGraph, list[dict[str, Any]], list[ProtocolIssue], str]:
    devices = raw.get("devices", [])
    links = raw.get("links", [])
    transfer = raw.get("transfer", {})
    device_by_id = {str(item["id"]): item for item in devices if isinstance(item, dict) and "id" in item}
    route = [str(item) for item in transfer.get("route", [])]
    source = str(transfer.get("source", ""))
    destination = str(transfer.get("destination", ""))
    checks: list[tuple[str, bool, dict[str, Any]]] = []
    checks.append(("dma.endpoints.declared", source in device_by_id and destination in device_by_id, {"source": source, "destination": destination}))
    if not route:
        route = [source, destination]
    checks.append(("dma.route.endpoints", bool(route) and route[0] == source and route[-1] == destination, {"route": route}))
    link_keys = {(str(item["from"]), str(item["to"])) for item in links if isinstance(item, dict)}
    link_by_pair = {
        (str(item["from"]), str(item["to"])): item
        for item in links if isinstance(item, dict)
    }
    route_connected = all((left, right) in link_keys or (right, left) in link_keys for left, right in zip(route, route[1:]))
    checks.append(("dma.route.connected", route_connected, {"route": route, "links": sorted(link_keys)}))
    direct = bool(transfer.get("direct", False))
    if direct:
        source_caps = set(map(str, device_by_id.get(source, {}).get("capabilities", [])))
        destination_caps = set(map(str, device_by_id.get(destination, {}).get("capabilities", [])))
        checks.append(("dma.direct.capability", "peer_dma_export" in source_caps and "peer_dma_import" in destination_caps, {"source_capabilities": sorted(source_caps), "destination_capabilities": sorted(destination_caps)}))
        direct_links = []
        for left, right in zip(route, route[1:]):
            link = link_by_pair.get((left, right)) or link_by_pair.get((right, left), {})
            direct_links.append(bool(link.get("direct", False)))
        checks.append(("dma.direct.route", bool(direct_links) and all(direct_links), {"route": route, "direct_links": direct_links}))
    mechanism_fields = {
        "dma.registration.mechanism": "registration_api",
        "dma.producer.mechanism": "producer_sync",
        "dma.completion.mechanism": "completion_signal",
        "dma.publication.mechanism": "publication_order",
        "dma.reuse.mechanism": "reuse_guard",
    }
    for identifier, field in mechanism_fields.items():
        checks.append((identifier, bool(transfer.get(field)), {field: transfer.get(field)}))
    event_sequence = [str(item.get("type")) for item in transfer.get("events", []) if isinstance(item, dict)]
    if event_sequence:
        required_events = ("producer_complete", "dma_begin", "dma_complete", "publish", "consumer_complete", "reuse")
        positions = {kind: [index for index, value in enumerate(event_sequence) if value == kind] for kind in required_events}
        ordered_events = all(positions[kind] for kind in required_events) and all(
            positions[left][0] < positions[right][0] for left, right in zip(required_events, required_events[1:])
        )
        checks.append(("dma.events.ordered", ordered_events, {"events": event_sequence, "required": required_events}))
    checks.extend((
        ("dma.memory.registered", bool(transfer.get("memory_registered", False)), {"memory_registered": transfer.get("memory_registered")}),
        ("dma.producer.ordered", bool(transfer.get("producer_complete_before_dma", False)), {"producer_complete_before_dma": transfer.get("producer_complete_before_dma")}),
        ("dma.publication.ordered", bool(transfer.get("dma_complete_before_publish", False)), {"dma_complete_before_publish": transfer.get("dma_complete_before_publish")}),
        ("dma.reuse.safe", bool(transfer.get("consumer_complete_before_reuse", False)), {"consumer_complete_before_reuse": transfer.get("consumer_complete_before_reuse")}),
        ("dma.fallback.declared", bool(transfer.get("fallback")), {"fallback": transfer.get("fallback")}),
    ))
    obligations: list[dict[str, Any]] = []
    issues: list[ProtocolIssue] = []
    smt_parts: list[str] = []
    for identifier, valid, detail in checks:
        proof, smt = _prove_fact(identifier, valid, detail)
        obligations.append(proof); smt_parts.append(smt)
        if not valid:
            issues.append(ProtocolIssue(identifier, identifier.split(".")[1], "DMA protocol obligation failed", detail))
    nodes: list[SemanticFlowNode] = [_base_node("source", "Input", "producer-resident-bytes", (), {"device": source}, "GPU/host allocation")]
    nodes.append(_base_node("register", "DMARegister", "register-device-memory", ("source",), {"registered": transfer.get("memory_registered", False)}, "peer-memory/dma-buf registration"))
    previous = "register"
    for ordinal, device in enumerate(route):
        route_id = f"route.{ordinal}"
        nodes.append(_base_node(route_id, "TopologyRoute", "physical-hop", (previous,), {"device": device}, "PCIe/NVLink/IOMMU topology"))
        previous = route_id
    nodes.append(_base_node("transfer", "DMATransfer", "device-to-device-transfer", (previous,), dict(transfer), "GPUDirect/RDMA/dma-buf"))
    nodes.append(_base_node("fence", "Fence", "dma-completion", ("transfer",), {}, "DMA completion/fence"))
    nodes.append(_base_node("output", "Output", "consumer-visible-bytes", ("fence",), {"device": destination}, "consumer publication"))
    ordering_obligation = obligation("dma.ordering.complete", "synchronization", "producer, DMA, publication, consumer, and reuse order is complete", scope="bounded-transfer", proof_method="Z3 bounded event ordering", native_construct="CUDA synchronization/dma-fence/RDMA completion")
    topology_obligation = obligation("dma.topology.reachable", "topology", "declared route connects registered compatible endpoints", scope="declared-machine", proof_method="topology path and capability validation", native_construct="PCIe/NVLink/IOMMU route")
    graph = _graph(
        name=str(raw.get("name", "dma-protocol")), kind="dma", manifest_path=manifest_path,
        nodes=nodes,
        contracts={"devices": devices, "links": links, "transfer": transfer, "route": route},
        obligations=(ordering_obligation, topology_obligation),
        effects=(SemanticEffect("dma.transfer", "DMA", "transfer", source, "consumer-bytes", "producer-complete -> dma -> publish -> reuse", ("register", "transfer", "fence"), ("dma.ordering.complete", "dma.topology.reachable")),),
        protocols=(
            ProtocolTransition("dma.ownership", "DMA", "producer-owned", "registered transfer", "consumer-owned", "completion and publication observed", ("dma.ordering.complete",), {"route": route}),
            ProtocolTransition("dma.route", "Topology", source, "DMA route", destination, "all links and capabilities valid", ("dma.topology.reachable",), {"route": route}),
        ),
    )
    return graph, obligations, issues, "\n; ---- obligation ----\n".join(smt_parts)


def _verify_presentation(raw: dict[str, Any], manifest_path: Path) -> tuple[SemanticFlowGraph, list[dict[str, Any]], list[ProtocolIssue], str]:
    images = {str(item) for item in raw.get("images", [])}
    events = raw.get("events", [])
    states = {item: "available" for item in images}
    completed_cycles = {item: 0 for item in images}
    histories: dict[str, list[dict[str, Any]]] = {item: [] for item in images}
    checks: list[tuple[str, bool, dict[str, Any]]] = []
    transitions = {
        "acquire": ({"available"}, "acquired"),
        "reuse": ({"available"}, "acquired"),
        "render_begin": ({"acquired"}, "rendering"),
        "render_complete": ({"acquired", "rendering"}, "rendered"),
        "present": ({"rendered"}, "presented"),
        "scanout": ({"presented"}, "scanning"),
        "release": ({"scanning"}, "available"),
    }
    for index, event in enumerate(events):
        image = str(event.get("image", ""))
        event_type = str(event.get("type", ""))
        if image not in states:
            checks.append((f"presentation.image.{index}", False, {"image": image, "event": event_type, "reason": "undeclared image"}))
            continue
        before = states[image]
        allowed, after = transitions.get(event_type, (set(), before))
        valid = before in allowed
        histories[image].append({"index": index, "event": event_type, "before": before, "after": after if valid else before, "valid": valid})
        checks.append((
            f"presentation.transition.{image}.{index}", valid,
            {"event": event_type, "state": before, "allowed": sorted(allowed)},
        ))
        if valid:
            states[image] = after
            if event_type == "release":
                completed_cycles[image] += 1
    for image in sorted(images):
        complete = completed_cycles[image] > 0 and states[image] == "available"
        checks.append((
            f"presentation.lifecycle.{image}", complete,
            {"history": histories[image], "completed_cycles": completed_cycles[image], "final_state": states[image]},
        ))
    checks.append(("presentation.images.declared", bool(images), {"images": sorted(images)}))
    checks.append(("presentation.deadline.policy", bool(raw.get("deadline_policy")), {"deadline_policy": raw.get("deadline_policy")}))
    connector_binding = raw.get("connector_binding")
    if connector_binding is not None:
        if not isinstance(connector_binding, dict):
            raise ValueError("presentation connector_binding must be a mapping")
        checks.extend((
            (
                "presentation.binding.identity",
                bool(connector_binding.get("capability_hash")) and bool(connector_binding.get("connector")),
                {"capability_hash": connector_binding.get("capability_hash"), "connector": connector_binding.get("connector")},
            ),
            (
                "presentation.binding.connected",
                str(connector_binding.get("status", "")) == "connected",
                {"status": connector_binding.get("status"), "connector": connector_binding.get("connector")},
            ),
        ))
    obligations: list[dict[str, Any]] = []
    issues: list[ProtocolIssue] = []
    smt_parts: list[str] = []
    for identifier, valid, detail in checks:
        proof, smt = _prove_fact(identifier, valid, detail)
        obligations.append(proof); smt_parts.append(smt)
        if not valid:
            issues.append(ProtocolIssue(identifier, "presentation", "presentation lifecycle obligation failed", detail))
    nodes: list[SemanticFlowNode] = [_base_node("initial", "Input", "presentation-engine-state", (), {"images": sorted(images)}, "swapchain/KMS state")]
    previous = "initial"
    node_kind = {"acquire": "Acquire", "render_complete": "Fence", "present": "Present", "scanout": "Scanout", "release": "Release", "reuse": "Acquire", "render_begin": "Dispatch"}
    for ordinal, event in enumerate(events):
        kind = node_kind.get(str(event.get("type")), "Control")
        node_id = f"event.{ordinal}"
        nodes.append(_base_node(node_id, kind, str(event.get("type", "event")), (previous,), dict(event), "swapchain/page-flip/scanout event"))
        previous = node_id
    nodes.append(_base_node("output", "Output", "presented-frame", (previous,), {}, "visible scanout"))
    lifecycle_obligation = obligation("presentation.lifecycle.complete", "lifetime", "every image follows acquire-render-present-scanout-release before reuse", scope="bounded-frame-sequence", proof_method="Z3/event-order verification", native_construct="swapchain/KMS page flip")
    deadline_obligation = obligation("presentation.deadline.declared", "state", "presentation mode and deadline behavior are explicit", scope="presentation-contract", proof_method="manifest validation plus physical timestamp runner", native_construct="vblank/present mode")
    graph = _graph(
        name=str(raw.get("name", "presentation-protocol")), kind="presentation", manifest_path=manifest_path,
        nodes=nodes,
        contracts={
            "images": sorted(images), "events": events, "present_mode": raw.get("present_mode"),
            "deadline_policy": raw.get("deadline_policy"), "connector_binding": connector_binding,
        },
        obligations=(lifecycle_obligation, deadline_obligation),
        effects=(
            SemanticEffect("presentation.acquire", "Acquire", "frame", "swapchain-image", "frame", "acquire-before-render", tuple(node.id for node in nodes if node.kind == "Acquire"), ("presentation.lifecycle.complete",)),
            SemanticEffect("presentation.present", "Present", "frame", "presentation-engine", "visible-frame", "render-before-present", tuple(node.id for node in nodes if node.kind in {"Present", "Scanout", "Release"}), ("presentation.lifecycle.complete", "presentation.deadline.declared")),
        ),
        protocols=(ProtocolTransition("presentation.image", "Presentation", "available", "acquire/render/present/scanout", "available", "release before reuse", ("presentation.lifecycle.complete",), {"present_mode": raw.get("present_mode")}),),
    )
    return graph, obligations, issues, "\n; ---- obligation ----\n".join(smt_parts)


def _transitive_closure(nodes: list[str], edges: set[tuple[str, str]]) -> set[tuple[str, str]]:
    closure = set(edges)
    changed = True
    while changed:
        changed = False
        additions = {(left, right2) for left, right in closure for left2, right2 in closure if right == left2 and (left, right2) not in closure}
        if additions:
            closure.update(additions)
            changed = True
    return closure


def enumerate_dma_routes(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Enumerate simple bounded direct and host-staged routes for topology search."""
    devices = {str(item["id"]): item for item in raw.get("devices", [])}
    links = raw.get("links", [])
    transfer = raw.get("transfer", {})
    source, destination = str(transfer.get("source", "")), str(transfer.get("destination", ""))
    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {item: [] for item in devices}
    for link in links:
        left, right = str(link["from"]), str(link["to"])
        adjacency.setdefault(left, []).append((right, link))
        if bool(link.get("bidirectional", True)):
            adjacency.setdefault(right, []).append((left, link))
    routes: list[list[str]] = []

    def walk(current: str, path: list[str]) -> None:
        if len(path) > min(6, len(devices) + 1):
            return
        if current == destination:
            routes.append(path.copy())
            return
        for next_device, _ in adjacency.get(current, []):
            if next_device not in path:
                walk(next_device, [*path, next_device])

    if source in devices and destination in devices:
        walk(source, [source])
    results = []
    for path in routes:
        latency = 0.0
        bandwidth = float("inf")
        direct = len(path) == 2
        for left, right in zip(path, path[1:]):
            link = next(item for neighbor, item in adjacency[left] if neighbor == right)
            latency += float(link.get("latency_ns", 0.0))
            bandwidth = min(bandwidth, float(link.get("bandwidth_bytes_per_second", 0.0)) or float("inf"))
            direct = direct and bool(link.get("direct", False))
        bytes_count = float(transfer.get("bytes", 0))
        estimated = latency + (bytes_count / bandwidth * 1e9 if bandwidth not in {0.0, float("inf")} else 0.0)
        results.append({"route": path, "direct": direct, "estimated_time_ns": estimated, "route_hash": canonical_hash(path)})
    return sorted(results, key=lambda item: (item["estimated_time_ns"], len(item["route"]), item["route"]))
