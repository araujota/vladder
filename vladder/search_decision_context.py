from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Iterable, Mapping


DECISION_CONTEXT_VERSION = "pre-decision-state-v2"


def build_decision_context(
    root_graph: Mapping[str, Any],
    *,
    semantic_state: Mapping[str, Any],
    action: Mapping[str, Any],
    ancestor_actions: Iterable[Mapping[str, Any]] = (),
    depth: int,
    stage: str,
    terminal: bool,
    projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a source-free graph of the state visible before a lazy decision.

    Terminal evidence is deliberately absent. The graph contains only the semantic root,
    a grammar-provided region projection, and actions already selected on the path.
    """
    selected_projection = dict(projection or {})
    graph = deepcopy(selected_projection.get("graph") or dict(root_graph))
    nodes = [dict(item) for item in graph.get("nodes", ()) if isinstance(item, Mapping)]
    edges = [dict(item) for item in graph.get("edges", ()) if isinstance(item, Mapping)]
    graph["nodes"] = nodes
    graph["edges"] = edges
    graph.setdefault("obligations", [])
    graph.setdefault("effects", [])
    graph.setdefault("protocols", [])
    graph.setdefault("claims", [])

    existing_ids = {str(item.get("id")) for item in nodes}
    focus_ids = [
        str(item) for item in selected_projection.get("focus_node_ids", ())
        if str(item) in existing_ids
    ]
    path = [dict(item) for item in ancestor_actions]
    if not path or path[-1] != dict(action):
        path.append(dict(action))
    previous: str | None = None
    for index, selected_action in enumerate(path):
        node_id = _unique_id(existing_ids, f"decision.action.{index}")
        existing_ids.add(node_id)
        kind, operation = _action_semantics(selected_action)
        attributes = _action_attributes(selected_action)
        nodes.append({
            "id": node_id,
            "kind": kind,
            "operation": operation,
            "output_type": _action_output_type(selected_action),
            "inputs": [previous] if previous is not None else [],
            "attributes": attributes,
            "semantic_obligations": [],
            "source_provenance": {
                "adapter": DECISION_CONTEXT_VERSION,
                "language": "language-neutral",
            },
        })
        if previous is not None:
            edges.append(_edge(previous, node_id, "ordering", "program-order"))
        previous = node_id
    if previous is not None:
        for focus in focus_ids:
            edges.append(_edge(focus, previous, "flow", "program-order"))
        focus_ids.append(previous)

    selected_count = _mapping_size(semantic_state.get("selection"))
    if selected_count == 0:
        selected_count = _sequence_size(semantic_state.get("selected_functions"))
    remaining_count = _sequence_size(semantic_state.get("remaining_regions"))
    if remaining_count == 0:
        remaining_count = _sequence_size(semantic_state.get("remaining_dimensions"))
    quality = str(selected_projection.get("quality") or "partial_state")
    if quality not in {"region_projected", "partial_state", "root_only"}:
        quality = "partial_state"
    canonical_state_hash = semantic_state.get("canonical_state_hash") or hashlib.sha256(
        json.dumps(
            {
                "graph": graph,
                "semantic_state": dict(semantic_state),
                "action_path": path,
                "stage": stage,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    return {
        "context_version": DECISION_CONTEXT_VERSION,
        "quality": quality,
        "graph": graph,
        "focus_node_ids": list(dict.fromkeys(focus_ids)),
        "state_features": {
            "depth": depth,
            "selected_count": selected_count,
            "remaining_count": remaining_count,
            "action_count": len(path),
            "region_count": int(selected_projection.get("region_count", 0)),
            "terminal": terminal,
            "stage": stage,
        },
        "semantic_delta": _semantic_delta(action),
        "canonical_state_hash": canonical_state_hash,
    }


def selected_build_projection(
    report: Mapping[str, Any],
    *,
    current_region: str | None,
) -> dict[str, Any]:
    """Project Clang subregion closure into the language-neutral decision graph."""
    closure_graph = report.get("region_closure", {}).get("semantic_graph")
    if not isinstance(closure_graph, Mapping):
        return {"quality": "root_only", "graph": {}, "focus_node_ids": [], "region_count": 0}
    graph = deepcopy(dict(closure_graph))
    nodes = [dict(item) for item in graph.get("nodes", ()) if isinstance(item, Mapping)]
    edges = [dict(item) for item in graph.get("edges", ()) if isinstance(item, Mapping)]
    graph["nodes"] = nodes
    graph["edges"] = edges
    existing_ids = {str(item.get("id")) for item in nodes}
    anchor = "region" if "region" in existing_ids else (next(iter(existing_ids), None))
    raw_subregions = report.get("subregions", ())
    if isinstance(raw_subregions, Mapping):
        raw_subregions = raw_subregions.get("regions", ())
    subregions = tuple(item for item in raw_subregions if isinstance(item, Mapping))
    focus: list[str] = []
    for index, region in enumerate(subregions):
        node_id = _unique_id(existing_ids, f"decision.region.{index}")
        existing_ids.add(node_id)
        region_kind, operation = _region_semantics(str(region.get("kind") or ""))
        source_range = region.get("source_range")
        source_size = 0
        if isinstance(source_range, (list, tuple)) and len(source_range) == 2:
            source_size = max(0, int(source_range[1]) - int(source_range[0]))
        boundary = region.get("boundary") if isinstance(region.get("boundary"), Mapping) else {}
        attributes = {
            "size": source_size,
            "count": len(boundary.get("referenced_identifiers", ())),
            "depth": len(region.get("escaping_control", ())),
            "ownership": "ephemeral",
            "lifetime": "function",
            "exactness": "exact",
        }
        nodes.append({
            "id": node_id,
            "kind": region_kind,
            "operation": operation,
            "output_type": "region-state",
            "inputs": [anchor] if anchor else [],
            "attributes": attributes,
            "semantic_obligations": [],
            "source_provenance": {
                "adapter": DECISION_CONTEXT_VERSION,
                "language": "language-neutral",
            },
        })
        if anchor:
            edges.append(_edge(anchor, node_id, "control", "program-order"))
        if str(region.get("id")) == current_region:
            focus.append(node_id)
        _append_region_structure(nodes, edges, existing_ids, node_id, region)
    return {
        "quality": "region_projected" if subregions else "root_only",
        "graph": graph,
        "focus_node_ids": focus,
        "region_count": len(subregions),
    }


def _append_region_structure(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    existing_ids: set[str],
    region_id: str,
    region: Mapping[str, Any],
) -> None:
    boundary = region.get("boundary") if isinstance(region.get("boundary"), Mapping) else {}
    live_in_count = len(boundary.get("candidate_live_ins", ()))
    if live_in_count:
        _append_structural_node(
            nodes, edges, existing_ids, region_id, "Input", "input", "live-in-set",
            count=live_in_count,
        )
    call_count = len(region.get("calls", ())) + len(region.get("unmodeled_source_calls", ()))
    if call_count:
        _append_structural_node(
            nodes, edges, existing_ids, region_id, "Call", "call", "helper-set",
            count=call_count,
        )
    if region.get("escaping_control"):
        _append_structural_node(
            nodes, edges, existing_ids, region_id, "ExitMerge", "return", "control-exit-set",
            count=len(region.get("escaping_control", ())),
        )
    container = region.get("container_closure") if isinstance(region.get("container_closure"), Mapping) else {}
    if container.get("capacity_guard"):
        _append_structural_node(
            nodes, edges, existing_ids, region_id, "CapacityGuard", "guard", "capacity-contract",
            count=1,
        )
    hazard_count = len(region.get("hard_hazards", ()))
    if hazard_count:
        _append_structural_node(
            nodes, edges, existing_ids, region_id, "UnsupportedOperation", "barrier", "hazard-set",
            count=hazard_count,
        )


def _append_structural_node(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    existing_ids: set[str],
    region_id: str,
    kind: str,
    operation: str,
    output_type: str,
    *,
    count: int,
) -> None:
    node_id = _unique_id(existing_ids, f"{region_id}.{operation}")
    existing_ids.add(node_id)
    nodes.append({
        "id": node_id,
        "kind": kind,
        "operation": operation,
        "output_type": output_type,
        "inputs": [region_id],
        "attributes": {"count": count, "lifetime": "function"},
        "semantic_obligations": [],
        "source_provenance": {"adapter": DECISION_CONTEXT_VERSION, "language": "language-neutral"},
    })
    edges.append(_edge(region_id, node_id, "dependency", "program-order"))


def _semantic_delta(action: Mapping[str, Any]) -> dict[str, Any]:
    selected_parameter = str(action.get("parameter") or "")
    result: dict[str, Any] = {
        "delta_kind": _delta_kind(action),
        "factor": action.get("factor", action.get("value") if selected_parameter == "factor" else None),
        "width": action.get("width", action.get("value") if selected_parameter == "width" else None),
        "tile": action.get("tile", action.get("value") if selected_parameter == "tile" else None),
        "scope": action.get("scope"),
        "placement": action.get("placement"),
    }
    return {key: value for key, value in result.items() if value is not None}


def _action_semantics(action: Mapping[str, Any]) -> tuple[str, str]:
    family = str(action.get("family") or "")
    op = str(action.get("op") or action.get("rule") or "")
    text = f"{family} {op}".lower()
    if any(item in text for item in ("unroll", "vector", "interleave", "schedule")):
        return "Loop", "loop"
    if "compact" in text:
        return "Compact", "compact"
    if any(item in text for item in ("codec", "encode", "pack")):
        return "Codec", "encode"
    if any(item in text for item in ("lifetime", "retain", "reuse", "cache")):
        return "LifetimeBoundary", "reuse"
    if any(item in text for item in ("cross-tu", "definition", "call")):
        return "Call", "call"
    if any(item in text for item in ("protocol", "barrier", "fence")):
        return "Barrier", "barrier"
    if "reduce" in text or "popcount" in text:
        return "Reduce", "reduce"
    if "baseline" in text:
        return "Control", "dispatch"
    return "Map", "map"


def _region_semantics(kind: str) -> tuple[str, str]:
    if "For" in kind or "While" in kind:
        return "Loop", "loop"
    if "If" in kind or "Switch" in kind or "Conditional" in kind:
        return "Guard", "guard"
    return "Map", "map"


def _action_attributes(action: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "factor": action.get("factor"),
        "width": action.get("width"),
        "tile": action.get("tile"),
        "scope": action.get("scope"),
        "placement": action.get("placement"),
        "exactness": "exact",
        "lifetime": "function",
    }
    return {key: value for key, value in result.items() if value is not None}


def _action_output_type(action: Mapping[str, Any]) -> str:
    if action.get("factor") is not None or action.get("width") is not None:
        return "schedule-state"
    return "realization-state"


def _delta_kind(action: Mapping[str, Any]) -> str:
    kind, operation = _action_semantics(action)
    return f"{kind.lower()}_{operation}"


def _edge(source: str, destination: str, relation: str, ordering: str) -> dict[str, Any]:
    return {
        "id": f"{source}->{destination}:{relation}",
        "source": source,
        "destination": destination,
        "value_type": "decision-state",
        "ownership": "ephemeral",
        "alias_set": "decision-state",
        "lifetime": "function",
        "ordering": ordering,
        "relation": relation,
        "memory_region": "register",
        "validity_scope": "bounded-call",
    }


def _unique_id(existing: set[str], requested: str) -> str:
    if requested not in existing:
        return requested
    index = 1
    while f"{requested}.{index}" in existing:
        index += 1
    return f"{requested}.{index}"


def _mapping_size(value: Any) -> int:
    return len(value) if isinstance(value, Mapping) else 0


def _sequence_size(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple, set, frozenset)) else 0
