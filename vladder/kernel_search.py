from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any

from .kernel_graph import KernelGraph
from .sksf_attribution import AttributionStudy, GrammarAdmission, evaluate_grammar_admission


@dataclass(frozen=True)
class KernelCost:
    estimated_cycles: float
    dependency_depth: float
    register_pressure: float
    code_size: float
    cache_bytes: float
    synchronization: float


@dataclass(frozen=True)
class KernelCandidate:
    id: str
    rules: tuple[str, ...]
    families: tuple[str, ...]
    guards: tuple[str, ...]
    cost: KernelCost
    status: str
    bounded_optimality: str


@dataclass(frozen=True)
class KernelSearchResult:
    grammar_hash: str
    admissions: tuple[GrammarAdmission, ...]
    candidates: tuple[KernelCandidate, ...]
    audit: tuple[dict[str, Any], ...]
    explored: int
    classification: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def search_kernel_graph(
    graph: KernelGraph,
    grammar_dir: Path,
    studies: dict[str, AttributionStudy],
    *,
    beam_width: int = 32,
    max_depth: int = 6,
    allow_exploratory: bool = False,
) -> KernelSearchResult:
    payloads = [json.loads(path.read_text()) for path in sorted(grammar_dir.glob("*.json"))]
    if not payloads:
        raise ValueError("kernel grammar is empty")
    grammar_hash = hashlib.sha256(json.dumps(payloads, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    admissions = tuple(evaluate_grammar_admission(str(item["family"]), dict(item["attribution"]), studies) for item in payloads)
    admission_by_family = {item.family: item for item in admissions}
    rules = [dict(rule, family=item["family"]) for item in payloads for rule in item.get("rules", [])]
    base = _base_candidate(graph)
    all_candidates: dict[tuple[str, ...], KernelCandidate] = {(): base}
    frontier = [base]
    audit: list[dict[str, Any]] = []
    saturated = True
    for _ in range(max_depth):
        expanded: list[KernelCandidate] = []
        for parent in frontier:
            for rule in rules:
                admission = admission_by_family[str(rule["family"])]
                if admission.state == "rejected" or (admission.state == "exploratory" and not allow_exploratory):
                    audit.append({"parent": parent.id, "rule": rule["id"], "status": "rejected", "reason": admission.reason})
                    continue
                if rule["family"] in parent.families:
                    audit.append({"parent": parent.id, "rule": rule["id"], "status": "rejected", "reason": "one rule per grammar family"})
                    continue
                legal, reason = _legal(graph, rule)
                if not legal:
                    audit.append({"parent": parent.id, "rule": rule["id"], "status": "rejected", "reason": reason})
                    continue
                candidate = _apply(parent, rule, admission.state)
                all_candidates[candidate.rules] = candidate
                expanded.append(candidate)
                audit.append({"parent": parent.id, "rule": rule["id"], "status": "generated", "candidate": candidate.id, "admission": admission.state})
        if not expanded:
            break
        pareto = _pareto(expanded)
        if len(pareto) > beam_width:
            saturated = False
        frontier = sorted(pareto, key=lambda item: (_score(item.cost), item.id))[:beam_width]
    candidates = tuple(sorted(all_candidates.values(), key=lambda item: (_score(item.cost), item.id)))
    classification = "saturated_local_region" if saturated else "best_verified_found"
    return KernelSearchResult(grammar_hash, admissions, candidates, tuple(audit), len(candidates), classification)


def _base_candidate(graph: KernelGraph) -> KernelCandidate:
    bytes_moved = float(graph.annotations["logical_bytes"])
    source = graph.annotations["source_cost"]
    macs = float(source.get("useful_macs", 0))
    cost = KernelCost(macs / 16.0 + bytes_moved / 32.0, max(1.0, len(graph.nodes) / 2.0), 1.0, 1.0, bytes_moved, float(source.get("synchronization_count", 0)))
    return KernelCandidate("baseline", (), (), (), cost, "structurally_verified", "baseline")


def _legal(graph: KernelGraph, rule: dict[str, Any]) -> tuple[bool, str]:
    required = set(str(value) for value in rule.get("requires_nodes", []))
    available = {node.kind for node in graph.nodes}
    if not required <= available:
        return False, "missing node kinds: " + ", ".join(sorted(required - available))
    if int(rule.get("token_tile", 1)) > 1:
        if not any(node.kind == "Dispatch" for node in graph.nodes) or not rule.get("guard"):
            return False, "token tiling requires guarded dispatch"
    if rule.get("changes_accumulation_order") and any(edge.numerical_contract == "exact" for edge in graph.edges):
        return False, "exact numerical contract forbids accumulation reordering"
    return True, ""


def _apply(parent: KernelCandidate, rule: dict[str, Any], admission: str) -> KernelCandidate:
    cost = replace(
        parent.cost,
        estimated_cycles=parent.cost.estimated_cycles * float(rule.get("cycle_factor", 1.0)),
        dependency_depth=parent.cost.dependency_depth * float(rule.get("depth_factor", 1.0)),
        register_pressure=parent.cost.register_pressure * float(rule.get("register_factor", 1.0)),
        code_size=parent.cost.code_size * float(rule.get("code_factor", 1.0)),
        cache_bytes=parent.cost.cache_bytes * float(rule.get("cache_factor", 1.0)),
        synchronization=parent.cost.synchronization * float(rule.get("sync_factor", 1.0)),
    )
    rules = (*parent.rules, str(rule["id"]))
    digest = hashlib.sha256("|".join(rules).encode()).hexdigest()[:12]
    return KernelCandidate(
        f"kernel-{digest}", rules, (*parent.families, str(rule["family"])),
        tuple(sorted(set((*parent.guards, *([str(rule["guard"])] if rule.get("guard") else []))))), cost,
        "exploratory_static" if admission == "exploratory" else "structurally_verified",
        "best_verified_found",
    )


def _score(cost: KernelCost) -> float:
    return cost.estimated_cycles + 20.0 * cost.dependency_depth + 100.0 * cost.register_pressure + 100.0 * cost.code_size + cost.cache_bytes / 32.0 + 1000.0 * cost.synchronization


def _pareto(candidates: list[KernelCandidate]) -> list[KernelCandidate]:
    result: list[KernelCandidate] = []
    for candidate in candidates:
        values = tuple(asdict(candidate.cost).values())
        if any(
            other is not candidate
            and all(a <= b for a, b in zip(tuple(asdict(other.cost).values()), values))
            and any(a < b for a, b in zip(tuple(asdict(other.cost).values()), values))
            for other in candidates
        ):
            continue
        result.append(candidate)
    return result
