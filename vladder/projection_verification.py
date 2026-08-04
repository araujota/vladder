from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .projection_graph import ProjectionComplexGraph
from .projection_search import ProjectionPlan


@dataclass(frozen=True)
class ProjectionProof:
    status: str
    method: str
    obligations: tuple[str, ...]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_projection_plan(graph: ProjectionComplexGraph, plan: ProjectionPlan) -> ProjectionProof:
    errors: list[str] = []
    weight_formats = {edge.quantization for edge in graph.edges if edge.role == "weight"}
    if plan.layout == "interleaved_sibling_blocks" and len(weight_formats) != 1:
        errors.append("interleaved sibling layout requires one weight quantization format")
    if plan.shared_preparation and graph.annotations["shared_activation_fanout"] < 2:
        errors.append("shared preparation requires at least two projection consumers")
    if plan.token_tile not in {1, 2, 4, 8, 16}:
        errors.append("unsupported token tile")
    available = int(graph.provenance["regime"]["token_count"])
    if plan.token_tile > available and not any("token_count" in guard for guard in plan.guards):
        errors.append("token tile exceeds regime without fallback guard")
    if float(graph.provenance["semantics"].get("max_abs_error", 0.0)) == 0.0:
        reordered = any("tree" in rule or "reassociate" in rule for rule in plan.rules)
        if reordered:
            errors.append("exact contract rejects reordered accumulation")
    for edge in graph.edges:
        if edge.producer_tile and edge.consumer_tile and edge.producer_tile != edge.consumer_tile:
            errors.append(f"tile mismatch on {edge.id}")
        if edge.alias_set in {"unknown", "external-unknown"}:
            errors.append(f"unresolved alias set on {edge.id}")
    return ProjectionProof(
        "failed" if errors else "proved",
        "projection-structural+contract-refinement",
        ("shape", "quantization", "alias", "tile_compatibility", "dispatch_guards", "numerical_order", "layout_preconditions"),
        {"errors": errors, "guards": list(plan.guards), "weight_formats": sorted(weight_formats), "layout_bijection_required": plan.layout != "native_gguf"},
    )
