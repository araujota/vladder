from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
from typing import Any, Iterable, Mapping

from .language_adapter import canonical_hash


COMPOSITION_TRACE_VERSION = "vladder-composition-native-search-trace-v1"
INTERACTION_GRAPH_VERSION = "vladder-optimization-interaction-graph-v1"
TRAINING_CONTRACT_VERSION = "vladder-search-policy-training-contract-v1"
UTILITY_TIERS = ("U0", "U1", "U2", "U3", "U4")
INTERACTION_RELATIONS = (
    "TOUCHES_SAME_OWNER",
    "PRODUCES_FOR",
    "CONSUMES_FROM",
    "ENABLES",
    "DISABLES",
    "CONFLICTS_WITH",
    "COMMUTES_WITH",
    "SUBSUMES",
    "INVALIDATES",
    "CREATES_CONTRACT",
    "REQUIRES_CONTRACT",
    "REMOVES_MATERIALIZATION",
    "CREATES_MATERIALIZATION",
    "EXTENDS_LIFETIME",
    "SHORTENS_LIFETIME",
    "MOVES_AUTHORITY",
    "SHARES_MEMORY_REGION",
    "ORDER_DEPENDS_ON",
    "CROSS_TU_DEPENDS_ON",
)


def exact_state_delta(
    parent_context: Mapping[str, Any],
    child_context: Mapping[str, Any],
    parent_semantic_state: Mapping[str, Any],
    child_semantic_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic structural and semantic delta available before expansion."""
    parent_graph = _graph(parent_context)
    child_graph = _graph(child_context)
    parent_nodes = _by_identity(parent_graph.get("nodes", ()))
    child_nodes = _by_identity(child_graph.get("nodes", ()))
    parent_edges = _by_identity(parent_graph.get("edges", ()))
    child_edges = _by_identity(child_graph.get("edges", ()))
    added_nodes, removed_nodes, changed_nodes = _mapping_delta(parent_nodes, child_nodes)
    added_edges, removed_edges, changed_edges = _mapping_delta(parent_edges, child_edges)
    parent_obligations = _canonical_set(parent_graph.get("obligations", ()))
    child_obligations = _canonical_set(child_graph.get("obligations", ()))
    parent_semantic = _flatten_semantic(parent_semantic_state)
    child_semantic = _flatten_semantic(child_semantic_state)
    semantic_changes = {
        key: {"before": parent_semantic.get(key), "after": child_semantic.get(key)}
        for key in sorted(set(parent_semantic) | set(child_semantic))
        if parent_semantic.get(key) != child_semantic.get(key)
    }
    node_changes = [*added_nodes, *changed_nodes]
    result = {
        "nodes_added": added_nodes,
        "nodes_removed": removed_nodes,
        "nodes_changed": changed_nodes,
        "edges_added": added_edges,
        "edges_removed": removed_edges,
        "edges_changed": changed_edges,
        "lifetime_changes": _attribute_changes(node_changes, ("lifetime", "validity", "scope")),
        "representation_changes": _representation_changes(node_changes),
        "owner_changes": _attribute_changes(node_changes, ("owner", "ownership", "authority")),
        "contracts_created": sorted(child_obligations - parent_obligations),
        "contracts_invalidated": sorted(parent_obligations - child_obligations),
        "materializations_added": _nodes_of_kind(added_nodes, "material"),
        "materializations_removed": _nodes_of_kind(removed_nodes, "material"),
        "cross_tu_boundaries_affected": _cross_tu_changes(
            added_nodes, removed_nodes, changed_nodes, added_edges, removed_edges, changed_edges
        ),
        "semantic_changes": semantic_changes,
    }
    return {**result, "delta_hash": canonical_hash(result)}


def build_interaction_graph(
    parent_context: Mapping[str, Any],
    history: Iterable[Mapping[str, Any]],
    frontier: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build explicit, source-free transformation interactions known at scoring time."""
    graph = _graph(parent_context)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    ids: set[str] = set()

    def add_node(node_id: str, kind: str, **attributes: Any) -> str:
        selected = _unique(node_id, ids)
        ids.add(selected)
        nodes.append({"id": selected, "kind": kind, "attributes": attributes})
        return selected

    def add_edge(source: str, destination: str, relation: str, **attributes: Any) -> None:
        if relation not in INTERACTION_RELATIONS:
            raise ValueError(f"unknown interaction relation: {relation}")
        edges.append({
            "id": canonical_hash({"s": source, "d": destination, "r": relation, "a": attributes})[:24],
            "source": source,
            "destination": destination,
            "relation": relation,
            "attributes": attributes,
        })

    owner_ids = []
    for owner in _semantic_owners(parent_context):
        owner_ids.append(add_node(f"owner.{_safe(owner)}", "semantic_owner", semantic_id=owner))
    contract_ids = []
    for index, contract in enumerate(graph.get("obligations", ())):
        contract_ids.append(add_node(f"contract.{index}", "contract", contract=_sanitize(contract)))
    representation_ids = []
    materialization_ids = []
    memory_ids: dict[str, str] = {}
    for index, raw in enumerate(graph.get("nodes", ())):
        if not isinstance(raw, Mapping):
            continue
        kind = str(raw.get("kind", "representation"))
        attrs = raw.get("attributes") if isinstance(raw.get("attributes"), Mapping) else {}
        node_id = add_node(
            f"representation.{index}",
            "materialization" if "material" in kind.lower() else "representation",
            semantic_id=str(raw.get("id", index)),
            output_type=str(raw.get("output_type", "unknown")),
        )
        representation_ids.append(node_id)
        if "material" in kind.lower():
            materialization_ids.append(node_id)
        lifetime = attrs.get("lifetime") or attrs.get("scope")
        if lifetime:
            lifetime_id = add_node(f"lifetime.{index}", "lifetime_boundary", value=str(lifetime))
            add_edge(node_id, lifetime_id, "PRODUCES_FOR")
        authority = attrs.get("authority") or attrs.get("ownership")
        if authority:
            authority_id = add_node(f"authority.{index}", "authority_boundary", value=str(authority))
            add_edge(node_id, authority_id, "PRODUCES_FOR")
        memory = str(attrs.get("placement") or attrs.get("memory_region") or "")
        if memory:
            memory_id = memory_ids.get(memory)
            if memory_id is None:
                memory_id = add_node(f"memory.{_safe(memory)}", "memory_region", value=memory)
                memory_ids[memory] = memory_id
            add_edge(node_id, memory_id, "SHARES_MEMORY_REGION")
    if _is_cross_tu(graph):
        add_node("cross-tu.root", "cross_tu_participant", value="root")

    history_ids: list[str] = []
    for index, action in enumerate(history):
        action_id = add_node(
            f"applied.{index}", "applied_transformation", action=_sanitize(action), order=index
        )
        history_ids.append(action_id)
        if index:
            add_edge(history_ids[index - 1], action_id, "ORDER_DEPENDS_ON")

    for option_index, option in enumerate(frontier):
        action = option.get("action") if isinstance(option.get("action"), Mapping) else {}
        action_id = add_node(
            f"proposed.{option_index}",
            "proposed_transformation",
            action=_sanitize(action),
            state_hash=str(option.get("state_hash", "")),
        )
        for owner_id in owner_ids:
            add_edge(action_id, owner_id, "TOUCHES_SAME_OWNER")
        for contract_id in contract_ids:
            add_edge(action_id, contract_id, "REQUIRES_CONTRACT")
        _explicit_action_relations(action, action_id, history_ids, add_edge)
        delta = option.get("state_delta") if isinstance(option.get("state_delta"), Mapping) else {}
        for contract_index, contract_hash in enumerate(delta.get("contracts_created", ())):
            contract_id = add_node(
                f"proposed.{option_index}.contract.{contract_index}",
                "contract",
                contract_hash=str(contract_hash),
                status="created",
            )
            add_edge(action_id, contract_id, "CREATES_CONTRACT")
        for contract_id in contract_ids:
            if delta.get("contracts_invalidated"):
                add_edge(action_id, contract_id, "INVALIDATES", reason="contract_delta")
        for material_index, semantic_id in enumerate(delta.get("materializations_added", ())):
            material_id = add_node(
                f"proposed.{option_index}.materialization.{material_index}",
                "materialization",
                semantic_id=str(semantic_id),
                status="created",
            )
            add_edge(action_id, material_id, "CREATES_MATERIALIZATION")
        if delta.get("lifetime_changes"):
            lifetime_id = add_node(
                f"proposed.{option_index}.lifetime", "lifetime_boundary",
                changes=_sanitize(delta["lifetime_changes"]),
            )
            directions = {str(item.get("after", "")) for item in delta["lifetime_changes"]}
            relation = "EXTENDS_LIFETIME" if any(
                item in {"generation", "connection", "process"} for item in directions
            ) else "SHORTENS_LIFETIME"
            add_edge(action_id, lifetime_id, relation, delta=True)
        if delta.get("owner_changes"):
            authority_id = add_node(
                f"proposed.{option_index}.authority", "authority_boundary",
                changes=_sanitize(delta["owner_changes"]),
            )
            add_edge(action_id, authority_id, "MOVES_AUTHORITY", delta=True)
        _delta_relations(delta, action_id, materialization_ids, add_edge)
        if _is_cross_tu(graph):
            add_edge(action_id, "cross-tu.root", "CROSS_TU_DEPENDS_ON")
        joint = tuple(str(item) for item in action.get("joint_with", action.get("requires_actions", ())))
        if joint or (len(history_ids) >= 2 and _composition_action(action)):
            participants = history_ids[-max(2, len(joint)) :] + [action_id]
            factor_id = add_node(
                f"factor.{option_index}", "interaction_factor", arity=len(participants), relation="ENABLES"
            )
            for participant in participants:
                add_edge(participant, factor_id, "ENABLES")
            add_edge(factor_id, action_id, "PRODUCES_FOR")

    payload = {
        "schema_version": INTERACTION_GRAPH_VERSION,
        "nodes": nodes,
        "edges": edges,
    }
    return {**payload, "graph_hash": canonical_hash(payload)}


def build_composition_trace(
    *,
    root: Mapping[str, Any],
    project_id: str,
    source_frontend: str,
    compiler_target: str,
    hardware_context: Mapping[str, Any],
    lazy_result: Any,
    terminal_results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a native, exhaustive-label-ready trace from one completed search."""
    terminal_by_state = {str(item.get("state_id")): dict(item) for item in terminal_results}
    node_by_id = {item.node_id: item for item in lazy_result.nodes}
    states = []
    transpositions = []
    for item in lazy_result.nodes:
        history = _history_for(item, node_by_id)
        record = {
            "state_id": item.node_id,
            "root_id": str(root["root_id"]),
            "parent_state_id": item.parent_id,
            "canonical_state_hash": item.semantic_state_hash,
            "search_depth": item.depth,
            "applied_transformations": history,
            "ordered_action_history": history,
            "semantic_graph": deepcopy(item.decision_context.get("graph", {})),
            "active_contracts": list(item.decision_context.get("graph", {}).get("obligations", ())),
            "open_contract_requirements": list(item.decision_context.get("graph", {}).get("obligations", ())),
            "affected_semantic_owners": _semantic_owners(item.decision_context),
            "representation_state": _representation_state(item.decision_context),
            "lifetime_state": _dimension_state(item.decision_context, "lifetime"),
            "authority_state": _dimension_state(item.decision_context, "authority"),
            "cross_tu_context": {"present": _is_cross_tu(_graph(item.decision_context))},
            "semantic_state": deepcopy(item.semantic_state),
            "stage": item.stage,
            "family": item.family,
            "terminal": item.terminal,
            "disposition": item.disposition,
            "canonical_of": item.canonical_of,
            "search_cost": dict(item.search_cost),
        }
        states.append(record)
        if item.canonical_of:
            transpositions.append({
                "state_id": item.node_id,
                "equivalent_state_id": item.canonical_of,
                "canonical_state_hash": item.semantic_state_hash,
                "action_sequences": [history, _history_for(node_by_id[item.canonical_of], node_by_id)],
                "authority": "exact_canonical_hash" if item.disposition == "canonical_duplicate" else "verified_equivalence",
            })
    frontiers = []
    for decision in lazy_result.frontier_decisions:
        frontiers.append({
            "frontier_id": decision.decision_id,
            "state_id": decision.parent_node_id,
            "available_actions": [
                {
                    "action_id": canonical_hash({"frontier": decision.decision_id, "state": item["state_hash"]}),
                    "child_state_hash": item["state_hash"],
                    "grammar_family": str(item.get("action", {}).get("family", "unknown")),
                    "transformation_family": str(
                        item.get("action", {}).get("op")
                        or item.get("action", {}).get("rule")
                        or item.get("action", {}).get("parameter")
                        or "unknown"
                    ),
                    "affected_owners": _semantic_owners(item.get("decision_context", {})),
                    "required_contracts": list(item.get("decision_context", {}).get("graph", {}).get("obligations", ())),
                    "created_contracts": list(item.get("state_delta", {}).get("contracts_created", ())),
                    "invalidated_contracts": list(item.get("state_delta", {}).get("contracts_invalidated", ())),
                    "composition_arity": _action_arity(item.get("action", {})),
                    "local_graph_delta": item.get("state_delta", {}),
                    "predicted_state_delta_shape": _delta_shape(item.get("state_delta", {})),
                    "action": item.get("action", {}),
                    "inference_score": item.get("score"),
                    "inference_uncertainty": item.get("uncertainty"),
                }
                for item in decision.frontier
            ],
            "selected_action": decision.chosen_state_hash,
            "frontier_size": len(decision.frontier),
            "parent_state": {
                "canonical_state_hash": decision.parent_state_hash,
                "semantic_state": decision.parent_semantic_state,
                "decision_context": decision.parent_decision_context,
            },
            "search_history": list(decision.history),
            "interaction_graph": decision.interaction_graph,
            "scoring_wall_ms": decision.scoring_wall_ms,
        })
    terminals = [_terminal_record(node_by_id, state_id, result) for state_id, result in terminal_by_state.items()]
    labels = derive_contextual_labels(states, frontiers, terminals)
    root_record = {
        "root_id": str(root["root_id"]),
        "project_id": project_id,
        "canonical_root_hash": str(root["canonical_root_hash"]),
        "source_frontend": source_frontend,
        "compiler_target": compiler_target,
        "semantic_graph": deepcopy(root["semantic_graph"]),
        "contracts": deepcopy(root.get("contracts", {})),
        "cross_tu_scope": deepcopy(root.get("cross_tu_scope", {})),
        "hardware_context": deepcopy(dict(hardware_context)),
    }
    payload = {
        "schema_version": COMPOSITION_TRACE_VERSION,
        "complete": bool(lazy_result.complete),
        "training_contract": _training_contract(
            complete=bool(lazy_result.complete),
            states=states,
            frontiers=frontiers,
            terminals=terminals,
        ),
        "root": root_record,
        "states": states,
        "frontiers": frontiers,
        "transpositions": transpositions,
        "terminals": terminals,
        "labels": labels,
        "summary": {
            "state_count": len(states),
            "frontier_count": len(frontiers),
            "composition_frontier_count": sum(
                _is_composition_frontier(item) for item in frontiers
            ),
            "terminal_count": len(terminals),
            "transposition_count": len(transpositions),
            "retained_terminal_count": sum(item["retained_status"] for item in terminals),
            "material_terminal_count": sum(item["utility_tier"] in {"U3", "U4"} for item in terminals),
        },
    }
    trace = {**payload, "trace_hash": canonical_hash(payload)}
    errors = composition_trace_integrity_errors(trace)
    if errors:
        raise ValueError("invalid composition-native training trace: " + "; ".join(errors))
    return trace


def derive_contextual_labels(
    states: Iterable[Mapping[str, Any]],
    frontiers: Iterable[Mapping[str, Any]],
    terminals: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    state_values = [dict(item) for item in states]
    terminal_by_state = {str(item["state_id"]): dict(item) for item in terminals}
    children: dict[str | None, list[str]] = defaultdict(list)
    state_by_id = {str(item["state_id"]): item for item in state_values}
    for state in state_values:
        children[state.get("parent_state_id")].append(str(state["state_id"]))
    memo: dict[str, dict[str, Any]] = {}

    def visit(state_id: str) -> dict[str, Any]:
        if state_id in memo:
            return memo[state_id]
        terminal = terminal_by_state.get(state_id)
        own_tier = _tier_number(terminal.get("utility_tier", "U0")) if terminal else 0
        child_metrics = [visit(child) for child in children.get(state_id, ()) if child != state_id]
        best_tier = max([own_tier, *(item["tier"] for item in child_metrics)], default=own_tier)
        distances = [item["distance_by_tier"].get(f"U{best_tier}") for item in child_metrics]
        distances = [item for item in distances if item is not None]
        distance = 0 if own_tier == best_tier and own_tier > 0 else 1 + min(distances) if distances else None
        direct_cost = _cost_value(state_by_id[state_id].get("search_cost", {}))
        subtree_cost = direct_cost + sum(item["subtree_cost"] for item in child_metrics)
        utility_counts = {f"U{tier}": 0 for tier in range(5)}
        terminal_class_counts: dict[str, int] = defaultdict(int)
        if terminal:
            utility_counts[str(terminal["utility_tier"])] += 1
            terminal_class_counts[str(terminal.get("terminal_class", "unknown"))] += 1
        for item in child_metrics:
            for tier, count in item["utility_counts"].items():
                utility_counts[tier] += count
            for terminal_class, count in item["terminal_class_counts"].items():
                terminal_class_counts[terminal_class] += count
        distance_by_tier = {}
        for tier in range(1, 5):
            key = f"U{tier}"
            if terminal and _tier_number(terminal["utility_tier"]) >= tier:
                distance_by_tier[key] = 0
            else:
                known = [item["distance_by_tier"].get(key) for item in child_metrics]
                known = [item for item in known if item is not None]
                distance_by_tier[key] = 1 + min(known) if known else None
        result = {
            "tier": best_tier,
            "distance": distance,
            "distance_by_tier": distance_by_tier,
            "subtree_cost": subtree_cost,
            "utility_counts": utility_counts,
            "terminal_class_counts": dict(sorted(terminal_class_counts.items())),
            "contains_retained": bool(utility_counts["U4"]),
            "contains_material": bool(utility_counts["U3"] or utility_counts["U4"]),
            "contains_proof_valid_distinct": bool(
                utility_counts["U2"] or utility_counts["U3"] or utility_counts["U4"]
            ),
        }
        memo[state_id] = result
        return result

    for state_id in state_by_id:
        visit(state_id)
    result = []
    by_hash: dict[str, str] = {}
    for item in state_values:
        state_hash = str(item["canonical_state_hash"])
        existing = state_by_id.get(by_hash.get(state_hash, ""), {})
        is_owner = not item.get("canonical_of") and item.get("disposition") not in {
            "canonical_duplicate", "verified_equivalent",
        }
        existing_is_owner = bool(existing) and not existing.get("canonical_of") and existing.get(
            "disposition"
        ) not in {"canonical_duplicate", "verified_equivalent"}
        if state_hash not in by_hash or (is_owner and not existing_is_owner):
            by_hash[state_hash] = str(item["state_id"])
    for frontier in frontiers:
        action_labels = []
        for action in frontier.get("available_actions", ()):
            state_id = by_hash.get(str(action.get("child_state_hash")))
            metric = memo.get(state_id or "", _empty_metric())
            action_labels.append({
                "action_id": action["action_id"],
                "child_state_id": state_id,
                "best_descendant_tier": f"U{metric['tier']}",
                "contains_retained_descendant": metric["contains_retained"],
                "contains_material_descendant": metric["contains_material"],
                "contains_proof_valid_distinct_descendant": metric["contains_proof_valid_distinct"],
                "distance_to_tiers": metric["distance_by_tier"],
                "cost_to_best_descendant": metric["subtree_cost"],
                "utility_terminal_counts": metric["utility_counts"],
                "redundancy_class": _frontier_redundancy(
                    state_by_id.get(state_id or "", {}), metric,
                ),
            })
        ordered = sorted(action_labels, key=_advantage_key)
        rank = {item["action_id"]: index for index, item in enumerate(ordered)}
        pairs = []
        for left in action_labels:
            for right in action_labels:
                if rank[left["action_id"]] < rank[right["action_id"]]:
                    pairs.append({"preferred": left["action_id"], "over": right["action_id"]})
        result.append({
            "frontier_id": frontier["frontier_id"],
            "action_outcomes": [
                {**item, "advantage_rank": rank[item["action_id"]]} for item in action_labels
            ],
            "pairwise_preferences": pairs,
            "oracle_action_order": [item["action_id"] for item in ordered],
        })
    return result


def inference_view(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Return only state available at each decision before an action is selected.

    A completed trace contains future states, terminal outcomes, exact transpositions, costs, and
    labels. None of those global post-search facts may enter a live ordering/proposal model. Each
    frontier already owns the current parent state, ordered history, sibling actions, and symbolic
    action deltas needed for inference.
    """
    return {
        "schema_version": trace.get("schema_version"),
        "training_contract": deepcopy(trace.get("training_contract", {})),
        "root": deepcopy(trace.get("root", {})),
        "frontiers": [
            {
                key: deepcopy(value)
                for key, value in item.items()
                if key not in {"selected_action", "scoring_wall_ms"}
            }
            for item in trace.get("frontiers", ())
        ],
    }


def composition_trace_integrity_errors(trace: Mapping[str, Any]) -> list[str]:
    """Validate lineage, frontier completeness, labels, costs, and canonical ownership."""
    errors: list[str] = []
    payload = deepcopy(dict(trace))
    trace_hash = payload.pop("trace_hash", None)
    if trace_hash != canonical_hash(payload):
        errors.append("trace_hash does not match the canonical payload")

    states = list(trace.get("states", ()))
    state_by_id = {str(item.get("state_id")): item for item in states}
    if len(state_by_id) != len(states):
        errors.append("state_id values are not unique")
    for state in states:
        state_id = str(state.get("state_id"))
        parent_id = state.get("parent_state_id")
        if parent_id is not None and str(parent_id) not in state_by_id:
            errors.append(f"state {state_id} references an unknown parent")
        canonical_of = state.get("canonical_of")
        if canonical_of is not None:
            owner = state_by_id.get(str(canonical_of))
            if owner is None:
                errors.append(f"state {state_id} references an unknown canonical owner")
            elif owner.get("canonical_state_hash") != state.get("canonical_state_hash"):
                errors.append(f"state {state_id} disagrees with its canonical owner")

    states_by_hash: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for state in states:
        states_by_hash[str(state.get("canonical_state_hash"))].append(state)
    for state_hash, equivalent_states in states_by_hash.items():
        owners = [
            item for item in equivalent_states
            if item.get("canonical_of") is None
            and item.get("disposition") not in {"canonical_duplicate", "verified_equivalent"}
        ]
        if len(owners) != 1:
            errors.append(f"canonical state {state_hash} has {len(owners)} recursive owners")

    frontiers = list(trace.get("frontiers", ()))
    frontier_by_id = {str(item.get("frontier_id")): item for item in frontiers}
    if len(frontier_by_id) != len(frontiers):
        errors.append("frontier_id values are not unique")
    frontier_actions: dict[str, set[str]] = {}
    for frontier_id, frontier in frontier_by_id.items():
        actions = list(frontier.get("available_actions", ()))
        action_ids = [str(item.get("action_id")) for item in actions]
        if frontier.get("frontier_size") != len(actions):
            errors.append(f"frontier {frontier_id} size does not match its sibling actions")
        if len(set(action_ids)) != len(action_ids):
            errors.append(f"frontier {frontier_id} contains duplicate action IDs")
        frontier_actions[frontier_id] = set(action_ids)
        state_id = frontier.get("state_id")
        if state_id is not None and str(state_id) not in state_by_id:
            errors.append(f"frontier {frontier_id} references an unknown parent state")
        child_hashes = {str(item.get("child_state_hash")) for item in actions}
        missing_hashes = child_hashes - set(states_by_hash)
        if missing_hashes and trace.get("complete"):
            errors.append(f"frontier {frontier_id} has actions without generated child states")
        selected = frontier.get("selected_action")
        if selected is not None and str(selected) not in child_hashes:
            errors.append(f"frontier {frontier_id} selected action is not a sibling child state")

    labels = list(trace.get("labels", ()))
    label_by_frontier = {str(item.get("frontier_id")): item for item in labels}
    if len(label_by_frontier) != len(labels) or set(label_by_frontier) != set(frontier_by_id):
        errors.append("labels do not form a one-to-one mapping with frontiers")
    for frontier_id, action_ids in frontier_actions.items():
        label = label_by_frontier.get(frontier_id, {})
        labeled = {str(item.get("action_id")) for item in label.get("action_outcomes", ())}
        oracle = [str(item) for item in label.get("oracle_action_order", ())]
        if labeled != action_ids:
            errors.append(f"frontier {frontier_id} labels do not cover every sibling exactly")
        if len(oracle) != len(set(oracle)) or set(oracle) != action_ids:
            errors.append(f"frontier {frontier_id} oracle order is not a sibling permutation")

    terminals = list(trace.get("terminals", ()))
    for terminal in terminals:
        state = state_by_id.get(str(terminal.get("state_id")))
        if state is None:
            errors.append(f"terminal {terminal.get('terminal_id')} references an unknown state")
        elif state.get("canonical_of") is not None:
            errors.append(f"terminal {terminal.get('terminal_id')} is not attached to a canonical owner")
        elif state.get("canonical_state_hash") != terminal.get("semantic_state_hash"):
            errors.append(f"terminal {terminal.get('terminal_id')} has mismatched semantic identity")

    expected_summary = {
        "state_count": len(states),
        "frontier_count": len(frontiers),
        "composition_frontier_count": sum(_is_composition_frontier(item) for item in frontiers),
        "terminal_count": len(terminals),
        "transposition_count": len(trace.get("transpositions", ())),
        "retained_terminal_count": sum(bool(item.get("retained_status")) for item in terminals),
        "material_terminal_count": sum(item.get("utility_tier") in {"U3", "U4"} for item in terminals),
    }
    for key, expected in expected_summary.items():
        if trace.get("summary", {}).get(key) != expected:
            errors.append(f"summary {key} does not match trace contents")

    expected_contract = _training_contract(
        complete=bool(trace.get("complete")), states=states, frontiers=frontiers, terminals=terminals,
    )
    if trace.get("training_contract") != expected_contract:
        errors.append("training_contract does not match trace readiness")
    return errors


def _training_contract(
    *,
    complete: bool,
    states: Iterable[Mapping[str, Any]],
    frontiers: Iterable[Mapping[str, Any]],
    terminals: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    states = tuple(states)
    frontiers = tuple(frontiers)
    terminals = tuple(terminals)
    state_hashes = {str(item.get("canonical_state_hash")) for item in states}
    frontier_snapshot_complete = bool(frontiers) and all(
        item.get("frontier_size") == len(item.get("available_actions", ()))
        for item in frontiers
    )
    frontier_children_realized = frontier_snapshot_complete and all(
        str(action.get("child_state_hash")) in state_hashes
        for frontier in frontiers
        for action in frontier.get("available_actions", ())
    )
    frontier_complete = bool(frontier_snapshot_complete and frontier_children_realized)
    canonical_complete = bool(states) and all(item.get("canonical_state_hash") for item in states)
    costs = [item.get("search_cost") for item in (*states, *terminals)]
    measured_costs = bool(costs) and all(isinstance(item, Mapping) and bool(item) for item in costs)
    eligible = bool(complete and frontier_complete and canonical_complete and terminals)
    limitations = []
    if not complete:
        limitations.append("search_not_exhaustive")
    if not frontier_complete:
        limitations.append("frontier_context_incomplete")
    if not canonical_complete:
        limitations.append("canonical_identity_incomplete")
    if not terminals:
        limitations.append("terminal_outcomes_unavailable")
    if not measured_costs:
        limitations.append("search_cost_partial")
    return {
        "contract_version": TRAINING_CONTRACT_VERSION,
        "ml_authority": "ordering_and_verified_proposals_only",
        "hard_reduction_authority": "deterministic_or_formally_qualified_only",
        "inference_feature_boundary": "pre_decision_frontier_only",
        "post_search_supervision": "terminal_lineage_and_descendant_utility",
        "frontier_context": "complete" if frontier_complete else "partial",
        "canonical_state_identity": "complete" if canonical_complete else "partial",
        "search_cost_capture": "measured" if measured_costs else "partial",
        "future_policy_training_eligible": eligible,
        "limitations": limitations,
    }


def normalize_terminal_ownership(trace: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    """Attach terminal evidence to the canonical owner of its semantic state.

    Terminal evaluators use the semantic-state identity as their durable key. A native trace can
    contain several action-order nodes with that identity after exact transposition detection, but
    only the canonical owner is executable in replay. This normalization is deterministic and does
    not alter terminal outcomes, costs, or proof evidence.
    """
    payload = deepcopy(dict(trace))
    states = [dict(item) for item in payload.get("states", ())]
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for state in states:
        by_hash[str(state.get("canonical_state_hash"))].append(state)
    changes = 0
    terminals = []
    for raw in payload.get("terminals", ()):
        terminal = dict(raw)
        candidates = by_hash.get(str(terminal.get("semantic_state_hash")), ())
        owner = next(
            (
                item for item in candidates
                if not item.get("canonical_of")
                and item.get("disposition") not in {
                    "canonical_duplicate", "verified_equivalent",
                }
            ),
            candidates[0] if candidates else None,
        )
        if owner is not None and terminal.get("state_id") != owner.get("state_id"):
            terminal["state_id"] = owner["state_id"]
            changes += 1
        terminals.append(terminal)
    if not changes:
        return payload, 0
    payload["terminals"] = terminals
    payload["labels"] = derive_contextual_labels(
        states, payload.get("frontiers", ()), terminals,
    )
    summary = dict(payload.get("summary", {}))
    summary.update({
        "state_count": len(states),
        "frontier_count": len(payload.get("frontiers", ())),
        "composition_frontier_count": sum(
            _is_composition_frontier(item) for item in payload.get("frontiers", ())
        ),
        "terminal_count": len(terminals),
        "transposition_count": len(payload.get("transpositions", ())),
        "retained_terminal_count": sum(bool(item.get("retained_status")) for item in terminals),
        "material_terminal_count": sum(
            item.get("utility_tier") in {"U3", "U4"} for item in terminals
        ),
    })
    payload["summary"] = summary
    payload.pop("trace_hash", None)
    payload["trace_hash"] = canonical_hash(payload)
    return payload, changes


def _terminal_record(node_by_id: Mapping[str, Any], state_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    matching_nodes = [
        item for item in node_by_id.values() if item.semantic_state_hash == state_id
    ]
    node = next(
        (
            item for item in matching_nodes
            if not item.canonical_of
            and item.disposition not in {"canonical_duplicate", "verified_equivalent"}
        ),
        matching_nodes[0] if matching_nodes else None,
    )
    physical = str(result.get("physical_outcome", "proof_unknown"))
    proof = str(result.get("proof_status", "UNAVAILABLE"))
    benchmark = str(result.get("benchmark_status", "not_run"))
    retained = bool(result.get("retained_status") or result.get("promoted"))
    if retained:
        tier = "U4"
    elif benchmark in {"material_win", "win", "PASS"} and bool(result.get("physically_material", True)):
        tier = "U3"
    elif proof == "PASS" and physical == "distinct_realization":
        tier = "U2"
    elif proof == "PASS" and physical == "proof_unknown":
        tier = "U1"
    else:
        tier = "U0"
    return {
        "terminal_id": canonical_hash({"state": state_id, "candidate": result.get("candidate_id")}),
        "state_id": node.node_id if node is not None else state_id,
        "semantic_state_hash": state_id,
        "proof_status": proof,
        "semantic_distinctness": physical not in {"compiler_identical", "duplicate"},
        "compiler_identity": result.get("assembly_identity"),
        "dominance_status": result.get("dominance_status", "not_evaluated"),
        "benchmark_status": benchmark,
        "physical_result": _sanitize(result.get("physical_result", result.get("physical_outcome"))),
        "retained_status": retained,
        "terminal_class": _terminal_class(result),
        "utility_tier": tier,
        "search_cost": deepcopy(result.get("search_cost", {})),
    }


def _terminal_class(result: Mapping[str, Any]) -> str:
    if result.get("retained_status") or result.get("promoted"):
        return "retained"
    benchmark = str(result.get("benchmark_status", ""))
    if benchmark in {"material_win", "win"}:
        return "material_win"
    if benchmark in {"regression", "benchmark_regression"}:
        return "benchmark_regression"
    if benchmark in {"tie", "benchmark_tie"}:
        return "benchmark_tie"
    proof = str(result.get("proof_status", "UNAVAILABLE"))
    physical = str(result.get("physical_outcome", "proof_unknown"))
    if proof == "FAIL":
        return "proof_failed"
    if proof not in {"PASS", "FAIL"}:
        return "proof_unknown"
    if physical == "compiler_identical":
        return "compiler_identical"
    if physical == "duplicate":
        return "semantic_duplicate"
    if physical == "distinct_realization":
        return "proof_valid_distinct"
    if physical == "illegal":
        return "invalid"
    return "proof_unknown"


def _graph(context: Mapping[str, Any]) -> dict[str, Any]:
    value = context.get("graph", {})
    return dict(value) if isinstance(value, Mapping) else {}


def _by_identity(items: Iterable[Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        identity = str(item.get("id") or canonical_hash(item) or index)
        result[identity] = _sanitize(item)
    return result


def _mapping_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[list[Any], list[Any], list[Any]]:
    added = [{"id": key, "after": after[key]} for key in sorted(after.keys() - before.keys())]
    removed = [{"id": key, "before": before[key]} for key in sorted(before.keys() - after.keys())]
    changed = [
        {"id": key, "before": before[key], "after": after[key]}
        for key in sorted(before.keys() & after.keys()) if before[key] != after[key]
    ]
    return added, removed, changed


def _canonical_set(items: Iterable[Any]) -> set[str]:
    return {canonical_hash(_sanitize(item)) for item in items}


def _flatten_semantic(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result = {}
    for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, Mapping):
            result.update(_flatten_semantic(item, path))
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[path] = item
        elif isinstance(item, (list, tuple)):
            result[path] = _sanitize(item)
    return result


def _attribute_changes(changes: Iterable[Mapping[str, Any]], names: tuple[str, ...]) -> list[dict[str, Any]]:
    result = []
    for change in changes:
        before = change.get("before", {}).get("attributes", {}) if isinstance(change.get("before"), Mapping) else {}
        after = change.get("after", {}).get("attributes", {}) if isinstance(change.get("after"), Mapping) else {}
        for name in names:
            if before.get(name) != after.get(name) and (name in before or name in after):
                result.append({"id": change.get("id"), "field": name, "before": before.get(name), "after": after.get(name)})
    return result


def _representation_changes(changes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for change in changes:
        before = change.get("before", {}) if isinstance(change.get("before"), Mapping) else {}
        after = change.get("after", {}) if isinstance(change.get("after"), Mapping) else {}
        for field in ("kind", "operation", "output_type"):
            if before.get(field) != after.get(field) and (field in before or field in after):
                result.append({"id": change.get("id"), "field": field, "before": before.get(field), "after": after.get(field)})
    return result


def _nodes_of_kind(changes: Iterable[Mapping[str, Any]], token: str) -> list[str]:
    result = []
    for change in changes:
        value = change.get("after", change.get("before", {}))
        if token in str(value.get("kind", "")).lower() or token in str(value.get("operation", "")).lower():
            result.append(str(change.get("id")))
    return result


def _cross_tu_changes(*groups: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({str(item.get("id")) for group in groups for item in group if "cross" in json.dumps(item).lower() or "call" in json.dumps(item).lower()})


def _semantic_owners(context: Mapping[str, Any]) -> list[str]:
    values = context.get("focus_node_ids", ())
    if values:
        return sorted({str(item) for item in values})
    graph = _graph(context)
    return sorted({str(item.get("id")) for item in graph.get("nodes", ()) if isinstance(item, Mapping)})[:8]


def _representation_state(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": str(item.get("id")), "kind": str(item.get("kind")), "output_type": str(item.get("output_type"))}
        for item in _graph(context).get("nodes", ()) if isinstance(item, Mapping)
    ]


def _dimension_state(context: Mapping[str, Any], dimension: str) -> list[dict[str, Any]]:
    result = []
    for item in _graph(context).get("nodes", ()):
        if not isinstance(item, Mapping):
            continue
        attrs = item.get("attributes") if isinstance(item.get("attributes"), Mapping) else {}
        value = attrs.get(dimension) or (attrs.get("ownership") if dimension == "authority" else None)
        if value is not None:
            result.append({"id": str(item.get("id")), "value": _sanitize(value)})
    return result


def _is_cross_tu(graph: Mapping[str, Any]) -> bool:
    return any(
        "cross" in str(item).lower() or str(item.get("kind", "")).lower() == "call"
        for item in graph.get("nodes", ()) if isinstance(item, Mapping)
    )


def _history_for(node: Any, node_by_id: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = []
    current = node
    seen = set()
    while current is not None and current.node_id not in seen:
        seen.add(current.node_id)
        path.append(dict(current.action))
        current = node_by_id.get(current.parent_id)
    return list(reversed(path))


def _explicit_action_relations(action, action_id, history_ids, add_edge) -> None:
    relation_fields = {
        "enables": "ENABLES", "disables": "DISABLES", "conflicts_with": "CONFLICTS_WITH",
        "commutes_with": "COMMUTES_WITH", "subsumes": "SUBSUMES", "invalidates": "INVALIDATES",
    }
    for field, relation in relation_fields.items():
        values = action.get(field, ())
        if isinstance(values, str):
            values = (values,)
        for value in values:
            for index, history_id in enumerate(history_ids):
                if str(value) in {str(index), history_id}:
                    add_edge(action_id, history_id, relation, declared=True)


def _delta_relations(delta, action_id, materialization_ids, add_edge) -> None:
    for materialization in materialization_ids:
        if delta.get("materializations_removed"):
            add_edge(action_id, materialization, "REMOVES_MATERIALIZATION")
        if delta.get("materializations_added"):
            add_edge(action_id, materialization, "CREATES_MATERIALIZATION")


def _composition_action(action: Mapping[str, Any]) -> bool:
    text = json.dumps(action, sort_keys=True).lower()
    return any(token in text for token in ("compose", "fusion", "fuse", "lifetime", "retain", "interleave", "schedule", "selected"))


def _action_arity(action: Mapping[str, Any]) -> int:
    return max(1, sum(len(action.get(key, ())) if isinstance(action.get(key), (list, tuple)) else int(key in action) for key in ("primitives", "numeric_parameters", "categorical_parameters")))


def _delta_shape(delta: Mapping[str, Any]) -> dict[str, int]:
    return {key: len(value) for key, value in delta.items() if isinstance(value, (list, dict)) and value}


def _cost_value(cost: Mapping[str, Any]) -> float:
    return float(cost.get("total_wall_ms") or cost.get("evaluation_wall_ms") or cost.get("expansion_wall_ms") or cost.get("node_expansions") or 1.0)


def _tier_number(tier: str) -> int:
    return int(tier[1:]) if tier in UTILITY_TIERS else 0


def _advantage_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    tier = _tier_number(str(item["best_descendant_tier"]))
    distance = item["distance_to_tiers"].get(f"U{tier}") if tier else None
    return (-tier, distance if distance is not None else 10**9, float(item["cost_to_best_descendant"]), item["action_id"])


def _empty_metric() -> dict[str, Any]:
    return {
        "tier": 0,
        "distance_by_tier": {f"U{i}": None for i in range(1, 5)},
        "subtree_cost": 0.0,
        "utility_counts": {f"U{i}": 0 for i in range(5)},
        "terminal_class_counts": {},
        "contains_retained": False,
        "contains_material": False,
        "contains_proof_valid_distinct": False,
    }


def _frontier_redundancy(
    state: Mapping[str, Any], metric: Mapping[str, Any] | None = None,
) -> str:
    disposition = str(state.get("disposition", ""))
    structural = {
        "canonical_duplicate": "canonical-equivalent",
        "verified_equivalent": "commutative-equivalent",
        "dominated": "dominated",
    }.get(disposition)
    if structural:
        return structural
    metric = metric or {}
    if int(metric.get("tier", 0)) > 0:
        return "unique"
    classes = set(metric.get("terminal_class_counts", {}))
    if classes and classes <= {"compiler_identical", "semantic_duplicate"}:
        return "compiler-identical"
    if classes == {"dominated"}:
        return "dominated"
    return "exhausted-dead" if classes or state.get("terminal") else "unique"


def _is_composition_frontier(frontier: Mapping[str, Any]) -> bool:
    return any(
        _composition_action(item.get("action", {}))
        for item in frontier.get("available_actions", ())
    ) or len(frontier.get("search_history", ())) >= 2


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _safe(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)[:80] or "unknown"


def _unique(value: str, existing: set[str]) -> str:
    if value not in existing:
        return value
    index = 2
    while f"{value}.{index}" in existing:
        index += 1
    return f"{value}.{index}"
