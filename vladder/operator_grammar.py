from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .operator_contract import OperatorContract
from .operator_graph import OperatorGraph


@dataclass(frozen=True)
class OperatorRule:
    family: str
    id: str
    data: dict[str, Any]


@dataclass(frozen=True)
class OperatorPlan:
    id: str
    rules: tuple[str, ...]
    effects: tuple[str, ...]
    estimated_cost: float
    estimated_materialized_bytes: int
    estimated_stream_bytes: int
    estimated_stack_bytes: int
    estimated_code_growth_percent: float


@dataclass(frozen=True)
class OperatorSearchResult:
    status: str
    grammar_hash: str
    plans: list[OperatorPlan]
    audit: list[dict[str, Any]]
    explored: int
    beam_width: int
    max_depth: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_operator_grammar(directory: Path) -> tuple[list[OperatorRule], str]:
    rules = []
    canonical = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text())
        family = str(payload["family"])
        canonical.append(payload)
        for raw in payload["rules"]:
            rules.append(OperatorRule(family, str(raw["id"]), dict(raw)))
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return rules, digest


def search_operator_graph(contract: OperatorContract, graph: OperatorGraph, grammar_dir: Path, beam_width: int = 24, max_depth: int = 6) -> OperatorSearchResult:
    rules, grammar_hash = load_operator_grammar(grammar_dir)
    node_kinds = {node.kind for node in graph.nodes}
    layouts = {str(node.attrs.get("layout")) for node in graph.nodes if node.attrs.get("layout")}
    numerical = contract.data["semantics"].get("floating_point", "bitwise")
    numerical_class = numerical.get("class") if isinstance(numerical, dict) else ("bitwise" if numerical in {"exact", "bitwise"} else str(numerical))
    constraints = contract.data["constraints"]
    base_materialized = int(graph.annotations["estimated_materialized_bytes"])
    base_stream = int(graph.annotations["estimated_stream_bytes"])
    baseline = OperatorPlan("baseline", (), (), 1.0, base_materialized, base_stream, 0, 0.0)
    frontier = [baseline]
    all_plans = {baseline.effects: baseline}
    audit: list[dict[str, Any]] = []
    saturated = True
    for depth in range(max_depth):
        expanded: list[OperatorPlan] = []
        for plan in frontier:
            used_families = {_rule_family(rule_id, rules) for rule_id in plan.rules}
            for rule in rules:
                if rule.family in used_families:
                    continue
                reason = _legality_reason(rule, node_kinds, layouts, contract, numerical_class)
                if reason:
                    audit.append({"action": "reject", "plan": plan.id, "rule": rule.id, "reason": reason})
                    continue
                candidate = _extend_plan(plan, rule, base_materialized, base_stream)
                if candidate.estimated_stack_bytes > int(constraints["max_stack_bytes"]):
                    audit.append({"action": "prune", "plan": plan.id, "rule": rule.id, "reason": "max_stack_bytes"})
                    continue
                if candidate.estimated_code_growth_percent > float(constraints["max_code_growth_percent"]):
                    audit.append({"action": "prune", "plan": plan.id, "rule": rule.id, "reason": "max_code_growth_percent"})
                    continue
                key = tuple(sorted(candidate.effects))
                old = all_plans.get(key)
                if old is not None and _dominates(old, candidate):
                    audit.append({"action": "dominated", "plan": candidate.id, "by": old.id})
                    continue
                all_plans[key] = candidate
                expanded.append(candidate)
                audit.append({"action": "expand", "from": plan.id, "to": candidate.id, "rule": rule.id, "family": rule.family, "proof": rule.data.get("proof"), "estimated_cost": candidate.estimated_cost})
        if not expanded:
            break
        expanded.sort(key=lambda p: (p.estimated_cost, p.estimated_materialized_bytes, p.estimated_stack_bytes, p.id))
        if len(expanded) > beam_width:
            saturated = False
            for pruned in expanded[beam_width:]:
                audit.append({"action": "beam_prune", "plan": pruned.id, "beam_width": beam_width})
        frontier = expanded[:beam_width]
    else:
        saturated = False
    plans = sorted(all_plans.values(), key=lambda p: (p.estimated_cost, p.id))
    return OperatorSearchResult("saturated" if saturated else "best_found", grammar_hash, plans, audit, len(plans), beam_width, max_depth)


def transformed_graph_dict(graph: OperatorGraph, plan: OperatorPlan) -> dict[str, Any]:
    data = graph.to_dict()
    data["selected_plan"] = asdict(plan)
    data["annotations"] = dict(data["annotations"])
    data["annotations"]["grammar_derivation"] = list(plan.rules)
    data["annotations"]["estimated_materialized_bytes"] = plan.estimated_materialized_bytes
    if "eliminate_private_materialization" in plan.effects:
        materialized = {node["id"] for node in data["nodes"] if node["kind"] == "Materialize"}
        data["nodes"] = [node for node in data["nodes"] if node["id"] not in materialized]
        rewritten = [edge for edge in data["edges"] if edge["src"] not in materialized and edge["dst"] not in materialized]
        for node_id in materialized:
            incoming = [edge for edge in data["edges"] if edge["dst"] == node_id]
            outgoing = [edge for edge in data["edges"] if edge["src"] == node_id]
            for before in incoming:
                for after in outgoing:
                    edge = dict(after)
                    edge["src"] = before["src"]
                    edge["memory_region"] = "register"
                    edge["lifetime"] = "fused_region"
                    rewritten.append(edge)
        data["edges"] = rewritten
    return data


def _legality_reason(rule: OperatorRule, node_kinds: set[str], layouts: set[str], contract: OperatorContract, numerical_class: str) -> str | None:
    required = set(rule.data.get("requires_nodes", []))
    if not required.issubset(node_kinds):
        return "required node classes absent"
    required_layouts = set(rule.data.get("requires_any_layout", []))
    if required_layouts and not required_layouts.intersection(layouts):
        return "required layout absent"
    if rule.data.get("requires_specialization") and not contract.data.get("specializations"):
        return "no declared specialization"
    allowed_numerical = rule.data.get("numerical_classes")
    if allowed_numerical and numerical_class not in allowed_numerical:
        return f"numerical class {numerical_class} disallows rule"
    if rule.data.get("effect") == "eliminate_private_materialization":
        observed = {str(node.attrs.get("output")) for node in graph_nodes_placeholder(contract) if node.kind == "Emit"}
        if "temporary" in observed:
            return "materialization is externally observed"
    return None


def graph_nodes_placeholder(contract: OperatorContract) -> list[Any]:
    # Contract outputs are sufficient for the observer check; this adapter keeps
    # the legality function independent from source-level names.
    class Node:
        def __init__(self, output: str):
            self.kind = "Emit"
            self.attrs = {"output": output}
    return [Node(name) for name in contract.data["outputs"]]


def _extend_plan(plan: OperatorPlan, rule: OperatorRule, base_materialized: int, base_stream: int) -> OperatorPlan:
    cost = rule.data.get("cost", {})
    materialized = plan.estimated_materialized_bytes
    stream = plan.estimated_stream_bytes
    if "materialized_bytes_factor" in cost:
        materialized = int(base_materialized * float(cost["materialized_bytes_factor"]))
    if "stream_bytes_factor" in cost:
        stream = int(stream * float(cost["stream_bytes_factor"]))
    multiplier = 1.0
    for key, value in cost.items():
        if key.endswith("_factor") and key not in {"materialized_bytes_factor", "stream_bytes_factor"}:
            multiplier *= float(value)
    stack = max(plan.estimated_stack_bytes, int(cost.get("stack_bytes", 0)))
    growth = plan.estimated_code_growth_percent + float(cost.get("code_growth_percent", 0))
    rules = (*plan.rules, rule.id)
    effects = (*plan.effects, str(rule.data["effect"]))
    identifier = hashlib.sha256("|".join(rules).encode()).hexdigest()[:12]
    traffic_ratio = (materialized + stream + 1) / (base_materialized + base_stream + 1)
    return OperatorPlan(f"plan-{identifier}", rules, effects, plan.estimated_cost * multiplier * traffic_ratio, materialized, stream, stack, growth)


def _dominates(left: OperatorPlan, right: OperatorPlan) -> bool:
    return left.estimated_cost <= right.estimated_cost and left.estimated_materialized_bytes <= right.estimated_materialized_bytes and left.estimated_stack_bytes <= right.estimated_stack_bytes and left.estimated_code_growth_percent <= right.estimated_code_growth_percent


def _rule_family(rule_id: str, rules: list[OperatorRule]) -> str:
    return next(rule.family for rule in rules if rule.id == rule_id)
