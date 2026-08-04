from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any

from .projection_graph import ProjectionComplexGraph


FAMILIES = {"weight_layout", "activation", "traversal", "accumulator", "materialization", "reuse", "dispatch"}


@dataclass(frozen=True)
class ProjectionCost:
    weight_bytes: int
    activation_prepare_bytes: int
    temporary_bytes: int
    estimated_cycles: float
    synchronization: float
    scratch_bytes: int
    code_size: float


@dataclass(frozen=True)
class ProjectionPlan:
    id: str
    rules: tuple[str, ...]
    families: tuple[str, ...]
    guards: tuple[str, ...]
    token_tile: int
    sequence_tile: int
    shared_preparation: bool
    layout: str
    child_status: str
    cost: ProjectionCost
    score: float


@dataclass(frozen=True)
class ProjectionSearchResult:
    status: str
    grammar_hash: str
    explored: int
    plans: tuple[ProjectionPlan, ...]
    audit: tuple[dict[str, Any], ...]
    beam_width: int
    max_depth: int
    child_budget: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def search_projection_graph(graph: ProjectionComplexGraph, grammar_dir: Path, beam_width: int = 32, max_depth: int = 7, child_budget: int = 64) -> ProjectionSearchResult:
    rules, grammar_hash = _load(grammar_dir)
    if {rule["family"] for rule in rules} != FAMILIES:
        raise ValueError("projection grammar must contain exactly seven V5 families")
    base_cost = _base_cost(graph)
    baseline = ProjectionPlan("baseline", (), (), (), 1, 1, False, "native_gguf", "saturated", base_cost, _score(base_cost))
    plans: dict[tuple[str, ...], ProjectionPlan] = {(): baseline}
    frontier = [baseline]
    audit: list[dict[str, Any]] = []
    saturated = True
    for _ in range(max_depth):
        expanded: list[ProjectionPlan] = []
        for plan in frontier:
            used = set(plan.families)
            for rule in rules:
                if rule["family"] in used:
                    audit.append({"parent": plan.id, "rule": rule["id"], "status": "rejected", "reason": "one choice per family"})
                    continue
                legal, reason = _legal(graph, plan, rule)
                if not legal:
                    audit.append({"parent": plan.id, "rule": rule["id"], "status": "rejected", "reason": reason})
                    continue
                candidate = _apply(plan, rule, child_budget)
                key = candidate.rules
                if key not in plans or candidate.score < plans[key].score:
                    plans[key] = candidate
                    expanded.append(candidate)
                    audit.append({"parent": plan.id, "rule": rule["id"], "status": "admitted", "candidate": candidate.id})
        if not expanded:
            break
        nondominated = _pareto(expanded)
        if len(nondominated) > beam_width:
            saturated = False
        frontier = sorted(nondominated, key=lambda item: (item.score, item.id))[:beam_width]
    ordered = tuple(sorted(plans.values(), key=lambda item: (item.score, item.id)))
    status = "saturated_region" if saturated and all(plan.child_status == "saturated" for plan in ordered) else "best_verified_found"
    return ProjectionSearchResult(status, grammar_hash, len(plans), ordered, tuple(audit), beam_width, max_depth, child_budget)


def _load(directory: Path) -> tuple[list[dict[str, Any]], str]:
    payloads = [json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))]
    rules = [{**rule, "family": payload["family"]} for payload in payloads for rule in payload["rules"]]
    digest = hashlib.sha256(json.dumps(payloads, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return rules, digest


def _base_cost(graph: ProjectionComplexGraph) -> ProjectionCost:
    cost = graph.annotations["cost"]
    weight = int(cost["weight_bytes_read"])
    activation = int(cost["activation_bytes_read"])
    temporary = int(cost["temporary_bytes_written_read"])
    macs = int(cost["useful_macs"])
    return ProjectionCost(weight, activation * max(1, graph.annotations["projection_count"]), temporary, macs / 16.0 + weight / 16.0, float(cost["synchronization_count"]), activation, 1.0)


def _legal(graph: ProjectionComplexGraph, plan: ProjectionPlan, rule: dict[str, Any]) -> tuple[bool, str]:
    if rule.get("requires_shared_input") and graph.annotations["shared_activation_fanout"] < 2:
        return False, "complex has no shared-input projection fanout"
    tile = int(rule.get("token_tile", plan.token_tile))
    available = int(graph.provenance["regime"]["token_count"])
    if tile > available and not rule.get("guard"):
        return False, "token tile exceeds unguarded regime"
    if rule.get("changes_accumulation_order") and float(graph.provenance["semantics"].get("max_abs_error", 0.0)) == 0.0:
        return False, "zero-error contract forbids accumulation reordering"
    if rule.get("layout") == "interleaved_sibling_blocks":
        formats = {edge.quantization for edge in graph.edges if edge.role == "weight"}
        if len(formats) != 1:
            return False, "sibling interleave requires equal quantization formats"
    return True, ""


def _apply(plan: ProjectionPlan, rule: dict[str, Any], child_budget: int) -> ProjectionPlan:
    cost = replace(
        plan.cost,
        weight_bytes=max(0, int(plan.cost.weight_bytes * float(rule.get("weight_factor", 1.0)))),
        activation_prepare_bytes=max(0, int(plan.cost.activation_prepare_bytes * float(rule.get("activation_factor", 1.0)))),
        temporary_bytes=max(0, int(plan.cost.temporary_bytes * float(rule.get("temporary_factor", 1.0)))),
        estimated_cycles=plan.cost.estimated_cycles * float(rule.get("cycle_factor", 1.0)),
        synchronization=plan.cost.synchronization * float(rule.get("sync_factor", 1.0)),
        scratch_bytes=plan.cost.scratch_bytes + int(rule.get("scratch_bytes", 0)),
        code_size=plan.cost.code_size * float(rule.get("code_factor", 1.0)),
    )
    rules = (*plan.rules, str(rule["id"]))
    identifier = hashlib.sha256("|".join(rules).encode()).hexdigest()[:12]
    child_status = "best_verified_found" if int(rule.get("child_cost", 0)) > child_budget else plan.child_status
    guard = tuple(sorted(set((*plan.guards, *([str(rule["guard"])] if rule.get("guard") else [])))))
    return ProjectionPlan(
        f"projection-{identifier}", rules, (*plan.families, str(rule["family"])), guard,
        int(rule.get("token_tile", plan.token_tile)), int(rule.get("sequence_tile", plan.sequence_tile)),
        plan.shared_preparation or bool(rule.get("shared_preparation")), str(rule.get("layout", plan.layout)),
        child_status, cost, _score(cost),
    )


def _score(cost: ProjectionCost) -> float:
    return cost.estimated_cycles + cost.weight_bytes / 8.0 + cost.activation_prepare_bytes / 16.0 + cost.temporary_bytes / 16.0 + 1000.0 * cost.synchronization + cost.scratch_bytes / 32.0 + 100.0 * cost.code_size


def _pareto(plans: list[ProjectionPlan]) -> list[ProjectionPlan]:
    result = []
    for plan in plans:
        values = tuple(asdict(plan.cost).values())
        dominated = False
        for other in plans:
            if other is plan:
                continue
            comparison = tuple(asdict(other.cost).values())
            if all(a <= b for a, b in zip(comparison, values)) and any(a < b for a, b in zip(comparison, values)):
                dominated = True
                break
        if not dominated:
            result.append(plan)
    return result
