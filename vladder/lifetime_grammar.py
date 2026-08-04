from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from typing import Any

from .lifetime_attribution import LifetimeAttribution
from .lifetime_graph import LifetimeFlowGraph, LifetimeInformation


GRAMMAR_VERSION = "lifetime-v1"
RULES = (
    "repeated-derivation-elimination",
    "serialization-body-reuse",
    "immutable-mutable-projection-split",
    "intermediate-realization-elimination",
    "placement-resident-state",
)


@dataclass(frozen=True)
class LifetimeCandidate:
    candidate_id: str
    information_id: str
    family: str
    mode: str
    original_scope: str
    candidate_scope: str
    original_placement: str
    candidate_placement: str
    construction_policy: str
    invalidators: tuple[str, ...]
    non_invalidators: tuple[str, ...]
    expected_realization_count: int
    baseline_estimated_cost_ns: float
    candidate_estimated_cost_ns: float
    estimated_improvement_percent: float
    retained_bytes: int
    transfer_bytes_avoided: int
    fallback: str
    proof_obligations: tuple[str, ...]
    lower_level_families: tuple[str, ...]
    legality: str
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_lifetime_candidates(
    graph: LifetimeFlowGraph,
    attribution: dict[str, LifetimeAttribution],
) -> tuple[LifetimeCandidate, ...]:
    candidates: list[LifetimeCandidate] = []
    for item in graph.information:
        measured = attribution[item.id]
        if "serialized_body" in item.traits and measured.realization_redundancy_ratio > 1.0:
            candidates.append(_candidate(graph, item, measured, "serialization-body-reuse", "retain_body_per_record"))
        elif "derived" in item.traits and measured.realization_redundancy_ratio > 1.0:
            candidates.append(_candidate(graph, item, measured, "repeated-derivation-elimination", "retain_per_valid_scope"))

        if "mixed_mutability" in item.traits and set(item.mutation_dependencies) != set(item.mutations):
            candidates.append(_candidate(graph, item, measured, "immutable-mutable-projection-split", "split_stable_projection"))

        if "unobserved_intermediate" in item.traits:
            candidates.append(_candidate(graph, item, measured, "intermediate-realization-elimination", "direct_consumer"))
        elif measured.retention_waste_ratio >= 0.5:
            candidates.append(_candidate(graph, item, measured, "intermediate-realization-elimination", "retire_after_final_use"))

        if measured.transfer_redundancy_ratio > 1.0 and item.candidate_placements:
            target = next((placement for placement in item.candidate_placements if placement != item.current.placement), None)
            if target:
                candidates.append(_candidate(graph, item, measured, "placement-resident-state", "retain_at_consumer", target))
    return tuple(sorted(candidates, key=lambda candidate: (candidate.information_id, candidate.family, candidate.candidate_id)))


def _candidate(
    graph: LifetimeFlowGraph,
    item: LifetimeInformation,
    measured: LifetimeAttribution,
    family: str,
    mode: str,
    placement: str | None = None,
) -> LifetimeCandidate:
    candidate_scope = _candidate_scope(graph, item, family, mode)
    if mode == "direct_consumer" and placement is None:
        placement = next(
            (candidate for candidate in item.candidate_placements if candidate != item.current.placement),
            item.current.placement,
        )
    candidate_placement = placement or item.current.placement
    if mode == "direct_consumer":
        expected_count = 0
        construction_policy = "direct producer-to-consumer"
        retained_bytes = 0
    elif mode == "retire_after_final_use":
        expected_count = measured.construction_count
        construction_policy = "current construction with retirement at final use"
        retained_bytes = 0
    else:
        expected_count = measured.minimum_required_realizations
        construction_policy = "once per candidate scope and source version"
        retained_bytes = item.byte_size
    baseline_cost = _baseline_cost(item, measured)
    candidate_cost = _candidate_cost(item, measured, family, mode, expected_count, retained_bytes)
    improvement = 100.0 * (baseline_cost - candidate_cost) / baseline_cost if baseline_cost else 0.0
    transfer_avoided = 0
    if family == "placement-resident-state":
        unique = int(measured.bytes_transferred / measured.transfer_redundancy_ratio) if measured.transfer_redundancy_ratio else 0
        transfer_avoided = max(0, measured.bytes_transferred - unique)
    proof_obligations = [
        "derivation correctness", "consumer equivalence", "lifetime containment",
        "invalidation completeness", "publication atomicity", "retirement safety", "fallback equivalence",
    ]
    if family == "placement-resident-state":
        proof_obligations.append("placement ordering and visibility")
    if mode == "direct_consumer":
        proof_obligations.append("no independent observer")
    legal, diagnostics = lifetime_candidate_legality(graph, item, candidate_scope, candidate_placement, family, mode)
    payload = {
        "grammar": GRAMMAR_VERSION,
        "graph": graph.graph_hash,
        "information": item.id,
        "family": family,
        "mode": mode,
        "scope": candidate_scope,
        "placement": candidate_placement,
        "invalidators": item.invalidators,
    }
    candidate_id = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    lower_level = _lower_level_handoff(family, mode)
    return LifetimeCandidate(
        candidate_id, item.id, family, mode, item.current.scope, candidate_scope,
        item.current.placement, candidate_placement, construction_policy,
        item.invalidators, item.non_invalidators, expected_count, baseline_cost, candidate_cost,
        improvement, retained_bytes, transfer_avoided, item.fallback,
        tuple(proof_obligations), lower_level, "legal" if legal else "rejected", diagnostics,
    )


def _candidate_scope(
    graph: LifetimeFlowGraph,
    item: LifetimeInformation,
    family: str,
    mode: str,
) -> str:
    if mode == "direct_consumer":
        return item.consumers[0].scope
    if mode == "retire_after_final_use":
        compatible = [scope for scope in item.candidate_scopes if graph.scopes.contains(item.current.scope, scope)]
        return compatible[0] if compatible else item.current.scope
    if family == "immutable-mutable-projection-split":
        return _broadest(graph, item.candidate_scopes)
    return _broadest(graph, item.candidate_scopes)


def _broadest(graph: LifetimeFlowGraph, scopes: tuple[str, ...]) -> str:
    for scope in scopes:
        if all(graph.scopes.contains(scope, other) for other in scopes):
            return scope
    return scopes[0]


def lifetime_candidate_legality(
    graph: LifetimeFlowGraph,
    item: LifetimeInformation,
    candidate_scope: str,
    candidate_placement: str,
    family: str,
    mode: str,
) -> tuple[bool, tuple[str, ...]]:
    diagnostics: list[str] = []
    if candidate_scope not in graph.scopes.scopes:
        diagnostics.append("candidate scope is undeclared")
    for consumer in item.consumers:
        if mode != "direct_consumer" and not graph.scopes.contains(candidate_scope, consumer.scope):
            diagnostics.append(f"candidate scope does not contain consumer scope: {consumer.id}")
    if family in {"repeated-derivation-elimination", "serialization-body-reuse", "immutable-mutable-projection-split", "placement-resident-state"}:
        if not graph.scopes.contains(candidate_scope, item.current.scope):
            diagnostics.append("lifetime extension scope does not contain the current scope")
    if mode == "retire_after_final_use" and not graph.scopes.contains(item.current.scope, candidate_scope):
        diagnostics.append("shortened scope is not contained by current scope")
    if not item.fallback:
        diagnostics.append("candidate has no fallback")
    if item.current.consistency not in {"immutable", "single_threaded", "generation_atomic", "single_writer_multi_reader"}:
        diagnostics.append("protocol-adapter-required: unsupported consistency model")
    if family == "placement-resident-state" and candidate_placement == item.current.placement:
        diagnostics.append("placement candidate does not change placement")
    if mode == "direct_consumer" and any(consumer.independent_observer for consumer in item.consumers):
        diagnostics.append("intermediate has an independent observer")
    if not set(item.invalidators) <= set(item.mutations):
        diagnostics.append("candidate invalidator is not a declared mutation")
    return not diagnostics, tuple(diagnostics)


def _baseline_cost(item: LifetimeInformation, measured: LifetimeAttribution) -> float:
    return (
        measured.construction_count * item.costs.construction_ns
        + measured.consumer_count * item.costs.access_ns
        + measured.invalidation_count * item.costs.invalidation_ns
        + measured.transfer_count * item.costs.transfer_ns
    )


def _candidate_cost(
    item: LifetimeInformation,
    measured: LifetimeAttribution,
    family: str,
    mode: str,
    count: int,
    retained_bytes: int,
) -> float:
    if mode == "direct_consumer":
        construction = 0.0
    else:
        construction = count * item.costs.construction_ns
    access = measured.consumer_count * item.costs.access_ns
    invalidation = len(item.invalidators) * item.costs.invalidation_ns if count < measured.construction_count else measured.invalidation_count * item.costs.invalidation_ns
    retention = retained_bytes * item.costs.retention_byte_ns
    transfers = measured.transfer_count * item.costs.transfer_ns
    if family == "placement-resident-state" and measured.transfer_redundancy_ratio > 1.0:
        transfers /= measured.transfer_redundancy_ratio
    return construction + access + invalidation + retention + transfers


def _lower_level_handoff(family: str, mode: str) -> tuple[str, ...]:
    if family == "serialization-body-reuse":
        return ("expression-algebra", "memory-alias", "loop-schedule")
    if family == "intermediate-realization-elimination":
        return ("materialization-fusion", "memory-alias")
    if family == "placement-resident-state":
        return ("memory-alias", "concurrency-memory-order", "hardware-codegen")
    if family == "immutable-mutable-projection-split":
        return ("layout-representation", "state-window", "memory-alias")
    return ("state-window", "memory-alias")


def with_candidate_invalidators(candidate: LifetimeCandidate, invalidators: tuple[str, ...]) -> LifetimeCandidate:
    """Test and adapter hook for checking an explicitly proposed invalidation protocol."""
    return replace(candidate, invalidators=invalidators)
