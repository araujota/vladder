from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any

from .pipeline_graph import PipelineEdge, PipelineGraph, estimate_information_movement


@dataclass(frozen=True)
class PipelineRule:
    family: str
    id: str
    effect: str
    data: dict[str, Any]


@dataclass(frozen=True)
class PipelineCost:
    compute: float
    critical_path: float
    register_bytes: int
    l1_bytes: int
    l2_bytes: int
    llc_bytes: int
    dram_bytes: int
    synchronization: float
    code_size: float
    scratch_bytes: int


@dataclass(frozen=True)
class PipelinePlan:
    id: str
    rules: tuple[str, ...]
    effects: tuple[str, ...]
    streamed_edges: tuple[str, ...]
    affected_nodes: tuple[str, ...]
    child_budget: int
    child_saturation: str
    cost: PipelineCost
    score: float


@dataclass(frozen=True)
class PipelineSearchResult:
    status: str
    grammar_hash: str
    plans: tuple[PipelinePlan, ...]
    audit: tuple[dict[str, Any], ...]
    explored: int
    beam_width: int
    max_depth: int
    child_budget: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_pipeline_grammar(directory: Path) -> tuple[list[PipelineRule], str]:
    rules: list[PipelineRule] = []
    canonical = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text())
        canonical.append(payload)
        family = str(payload["family"])
        for raw in payload["rules"]:
            rules.append(PipelineRule(family, str(raw["id"]), str(raw["effect"]), dict(raw)))
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return rules, digest


def search_pipeline_graph(graph: PipelineGraph, grammar_dir: Path, beam_width: int = 24, max_depth: int = 5, child_budget: int = 64) -> PipelineSearchResult:
    rules, grammar_hash = load_pipeline_grammar(grammar_dir)
    families = {rule.family for rule in rules}
    expected = {"fusion", "materialization", "traversal", "layout", "state", "reduction", "scratch"}
    if families != expected:
        raise ValueError(f"pipeline grammar families differ: {sorted(families)}")
    baseline = PipelinePlan("baseline", (), (), (), (), child_budget, "saturated", _base_cost(graph), _score(_base_cost(graph)))
    all_plans: dict[tuple[str, ...], PipelinePlan] = {(): baseline}
    frontier = [baseline]
    audit: list[dict[str, Any]] = []
    saturated = True
    for _depth in range(max_depth):
        expanded: list[PipelinePlan] = []
        for plan in frontier:
            used_families = {_family(rule_id, rules) for rule_id in plan.rules}
            for rule in rules:
                if rule.family in used_families:
                    continue
                target, reason = _target_edge(graph, plan, rule)
                if reason:
                    audit.append({"action": "reject", "plan": plan.id, "rule": rule.id, "reason": reason})
                    continue
                candidate = _extend(graph, plan, rule, target)
                if candidate.cost.scratch_bytes > int(graph.provenance["constraints"].get("max_scratch_bytes", 1 << 30)):
                    audit.append({"action": "prune", "plan": plan.id, "rule": rule.id, "reason": "max_scratch_bytes"})
                    continue
                key = tuple(sorted(candidate.effects))
                old = all_plans.get(key)
                if old is not None and _dominates(old.cost, candidate.cost):
                    audit.append({"action": "dominated", "plan": candidate.id, "by": old.id})
                    continue
                all_plans[key] = candidate
                expanded.append(candidate)
                audit.append({
                    "action": "expand", "from": plan.id, "to": candidate.id, "rule": rule.id,
                    "family": rule.family, "proof": rule.data.get("proof"), "target_edge": target.id if target else None,
                    "parent_budget": beam_width, "child_budget": child_budget, "score": candidate.score,
                })
        if not expanded:
            break
        expanded.sort(key=lambda item: (item.score, item.cost.dram_bytes, item.cost.scratch_bytes, item.id))
        if len(expanded) > beam_width:
            saturated = False
            audit.extend({"action": "beam_prune", "plan": item.id, "beam_width": beam_width} for item in expanded[beam_width:])
        frontier = expanded[:beam_width]
    else:
        saturated = False
    plans = tuple(sorted(all_plans.values(), key=lambda item: (item.score, item.id)))
    return PipelineSearchResult("saturated" if saturated else "best_found", grammar_hash, plans, tuple(audit), len(plans), beam_width, max_depth, child_budget)


def transformed_pipeline_dict(graph: PipelineGraph, plan: PipelinePlan) -> dict[str, Any]:
    data = graph.to_dict()
    data["selected_plan"] = asdict(plan)
    for edge in data["edges"]:
        if edge["id"] in plan.streamed_edges:
            edge["materialization"] = "streamed"
            edge["cache_target"] = "register"
            edge["lifetime"] = "fused_region"
    data["annotations"] = dict(data["annotations"])
    data["annotations"]["grammar_derivation"] = list(plan.rules)
    data["annotations"]["information_movement_after"] = asdict(plan.cost)
    return data


def _base_cost(graph: PipelineGraph) -> PipelineCost:
    movement = graph.annotations["information_movement"]["modeled_transfer_bytes"]
    return PipelineCost(
        compute=sum(node.profile_weight or 1.0 for node in graph.nodes),
        critical_path=float(graph.annotations["critical_path_weight"]),
        register_bytes=int(movement["register"]), l1_bytes=int(movement["l1"]),
        l2_bytes=int(movement["l2"]), llc_bytes=int(movement["llc"]), dram_bytes=int(movement["dram"]),
        synchronization=sum(1.0 for edge in graph.edges if edge.ordering in {"barrier", "synchronization"}),
        code_size=1.0, scratch_bytes=sum(edge.logical_bytes for edge in graph.edges if edge.materialization == "materialized"),
    )


def _target_edge(graph: PipelineGraph, plan: PipelinePlan, rule: PipelineRule) -> tuple[PipelineEdge | None, str | None]:
    if rule.effect in {"stream_private_temporary", "tile_and_fuse", "share_scratch_lifetime"}:
        for edge in graph.edges:
            if edge.id in plan.streamed_edges or edge.materialization != "materialized":
                continue
            if len(edge.observers) != 1 or edge.observers[0] not in {edge.dst, "internal"}:
                continue
            if edge.alias_set in {"unknown", "external"}:
                continue
            return edge, None
        return None, "no private materialized edge satisfies observer and alias legality"
    if rule.effect == "change_layout" and not any(edge.layout in set(rule.data.get("from_layouts", [])) for edge in graph.edges):
        return None, "required layout absent"
    if rule.effect in {"online_reduction", "hierarchical_reduction"}:
        if not any(node.operator in {"attention", "softmax", "reduction"} for node in graph.nodes):
            return None, "reduction operator absent"
        semantics = graph.provenance["semantics"]
        if float(semantics.get("max_pipeline_abs_error", 0.0)) <= 0.0:
            return None, "reduction topology changes floating-point order under an exact pipeline budget"
    if rule.effect in {"incremental_state", "derived_state"} and not any(edge.materialization == "state" for edge in graph.edges):
        return None, "state edge absent"
    if rule.effect == "promote_scratch" and not any(edge.materialization == "materialized" for edge in graph.edges):
        return None, "no materialized scratch candidate"
    return None, None


def _extend(graph: PipelineGraph, plan: PipelinePlan, rule: PipelineRule, target: PipelineEdge | None) -> PipelinePlan:
    cost = plan.cost
    streamed = plan.streamed_edges
    affected = set(plan.affected_nodes)
    effect_key = rule.effect + (f":{target.id}" if target else "")
    if target and rule.effect in {"stream_private_temporary", "tile_and_fuse", "share_scratch_lifetime"}:
        streamed = (*streamed, target.id)
        affected.update((target.src, target.dst))
        edges = tuple(replace(edge, materialization="streamed", cache_target="register") if edge.id in streamed else edge for edge in graph.edges)
        movement = estimate_information_movement(edges)["modeled_transfer_bytes"]
        cost = replace(cost,
            register_bytes=int(movement["register"]), l1_bytes=int(movement["l1"]), l2_bytes=int(movement["l2"]),
            llc_bytes=int(movement["llc"]), dram_bytes=int(movement["dram"]),
            scratch_bytes=max(0, cost.scratch_bytes - target.logical_bytes),
            compute=cost.compute * float(rule.data.get("compute_factor", 1.0)),
            critical_path=cost.critical_path * float(rule.data.get("critical_path_factor", 1.0)),
            code_size=cost.code_size * float(rule.data.get("code_size_factor", 1.0)),
        )
    else:
        if rule.effect in {"online_reduction", "hierarchical_reduction"}:
            affected.update(node.id for node in graph.nodes if node.operator in {"attention", "softmax", "reduction"})
        elif rule.effect == "change_layout":
            layouts = set(rule.data.get("from_layouts", []))
            affected.update(edge.src for edge in graph.edges if edge.layout in layouts)
            affected.update(edge.dst for edge in graph.edges if edge.layout in layouts)
        elif rule.effect in {"incremental_state", "derived_state"}:
            affected.update(edge.src for edge in graph.edges if edge.materialization == "state")
            affected.update(edge.dst for edge in graph.edges if edge.materialization == "state")
        elif rule.effect in {"promote_scratch", "rematerialize"}:
            affected.update(edge.src for edge in graph.edges if edge.materialization == "materialized")
            affected.update(edge.dst for edge in graph.edges if edge.materialization == "materialized")
        cost = replace(cost,
            compute=cost.compute * float(rule.data.get("compute_factor", 1.0)),
            critical_path=cost.critical_path * float(rule.data.get("critical_path_factor", 1.0)),
            synchronization=cost.synchronization * float(rule.data.get("synchronization_factor", 1.0)),
            code_size=cost.code_size * float(rule.data.get("code_size_factor", 1.0)),
            scratch_bytes=cost.scratch_bytes + int(rule.data.get("scratch_bytes", 0)),
        )
    rules = (*plan.rules, rule.id)
    effects = (*plan.effects, effect_key)
    identifier = hashlib.sha256("|".join(effects).encode()).hexdigest()[:12]
    child_saturation = "best_found" if int(rule.data.get("child_cost", 0)) > plan.child_budget else plan.child_saturation
    return PipelinePlan(f"pipeline-{identifier}", rules, effects, tuple(sorted(set(streamed))), tuple(sorted(affected)), plan.child_budget, child_saturation, cost, _score(cost))


def _score(cost: PipelineCost) -> float:
    return (
        cost.compute + 0.6 * cost.critical_path + cost.register_bytes / 1e8 + cost.l1_bytes / 4e7 +
        cost.l2_bytes / 2e7 + cost.llc_bytes / 1e7 + cost.dram_bytes / 5e6 +
        0.2 * cost.synchronization + 0.05 * cost.code_size + cost.scratch_bytes / 1e7
    )


def _dominates(left: PipelineCost, right: PipelineCost) -> bool:
    return all(a <= b for a, b in zip(asdict(left).values(), asdict(right).values()))


def _family(rule_id: str, rules: list[PipelineRule]) -> str:
    return next(rule.family for rule in rules if rule.id == rule_id)
