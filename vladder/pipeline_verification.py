from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .pipeline_graph import PipelineGraph
from .pipeline_search import PipelinePlan


@dataclass(frozen=True)
class PipelineProof:
    status: str
    method: str
    obligations: tuple[str, ...]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_pipeline_plan(graph: PipelineGraph, plan: PipelinePlan) -> PipelineProof:
    errors: list[str] = []
    by_id = {edge.id: edge for edge in graph.edges}
    for edge_id in plan.streamed_edges:
        edge = by_id.get(edge_id)
        if edge is None:
            errors.append(f"unknown streamed edge {edge_id}")
            continue
        if edge.materialization != "materialized":
            errors.append(f"edge {edge_id} was not a materialized temporary")
        if len(edge.observers) != 1 or edge.observers[0] not in {edge.dst, "internal"}:
            errors.append(f"edge {edge_id} has an external or multiple observer")
        if edge.alias_set in {"unknown", "external"}:
            errors.append(f"edge {edge_id} alias set does not authorize fusion")
        if edge.ownership != "pipeline":
            errors.append(f"edge {edge_id} storage identity is not pipeline-owned")
    child_gaps = [node.id for node in graph.nodes if node.attrs.get("proof_status", "proved") not in {"proved", "bounded"}]
    if child_gaps:
        errors.append("unsupported child proof status: " + ", ".join(child_gaps))
    budget = graph.provenance["semantics"].get("max_pipeline_abs_error", 0.0)
    composed = sum(float(node.attrs.get("max_abs_error", 0.0)) for node in graph.nodes if node.id in plan.affected_nodes)
    if composed > float(budget):
        errors.append(f"composed error {composed} exceeds pipeline budget {budget}")
    return PipelineProof(
        "failed" if errors else "proved", "hierarchical-structural+composed-contract",
        ("external_observers", "shape", "alias", "lifetime", "ownership", "child_proofs", "numerical_composition"),
        {"errors": errors, "streamed_edges": list(plan.streamed_edges), "child_proof_gaps": child_gaps,
         "composed_max_abs_error": composed, "max_pipeline_abs_error": budget,
         "cache_claim_class": "performance_hypothesis_only"},
    )


def attribution_report(graph: PipelineGraph, plan: PipelinePlan, regional_speedup: float | None = None) -> dict[str, Any]:
    weights = {node.id: node.profile_weight for node in graph.nodes}
    measured = graph.annotations["profile_weights_measured"] and all(value is not None for value in weights.values())
    total = sum(value or 0.0 for value in weights.values())
    affected = sum(weights[node] or 0.0 for node in plan.affected_nodes)
    coverage = affected / total if measured and total > 0 else None
    amdahl = None
    if coverage is not None and regional_speedup is not None and regional_speedup > 0:
        amdahl = 1.0 / ((1.0 - coverage) + coverage / regional_speedup)
    return {
        "profile_weights_measured": measured,
        "affected_nodes": list(plan.affected_nodes),
        "affected_decode_fraction": coverage,
        "research_milestone_25pct": bool(coverage is not None and coverage >= 0.25),
        "regional_speedup": regional_speedup,
        "amdahl_max_end_to_end_speedup": amdahl,
        "claimable": measured,
    }


def infer_affected_fraction(regional_speedup: float, end_to_end_speedup: float) -> float:
    if regional_speedup <= 1.0 or end_to_end_speedup <= 0.0:
        raise ValueError("speedups must be positive and regional speedup must exceed one")
    fraction = (1.0 - 1.0 / end_to_end_speedup) / (1.0 - 1.0 / regional_speedup)
    return max(0.0, min(1.0, fraction))
