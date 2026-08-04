from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml


SEMANTIC_NODE_KINDS = {
    "AuthoritativeState", "DerivedInformation", "Invariant", "Mutation",
    "InvalidationEvent", "Observation", "ContractGuard",
}
REALIZATION_NODE_KINDS = {
    "EphemeralValue", "MaterializedBuffer", "PersistentIndex", "SerializedBody",
    "DecodedState", "CachedValidation", "GPUResidentState", "CPUResidentState",
    "TransportRepresentation", "SharedImmutableView", "VersionedRealization",
}
LIFECYCLE_NODE_KINDS = {
    "Construct", "Publish", "Acquire", "Reuse", "Refresh", "Invalidate", "Retire",
    "Destroy", "FallbackRecompute",
}
CONTROL_NODE_KINDS = {
    "LifetimeGuard", "GenerationBoundary", "TransactionBoundary", "FrameBoundary",
    "RecordBoundary", "FragmentBoundary", "ConnectionBoundary",
}
NODE_KINDS = SEMANTIC_NODE_KINDS | REALIZATION_NODE_KINDS | LIFECYCLE_NODE_KINDS | CONTROL_NODE_KINDS


@dataclass(frozen=True)
class ScopeRelation:
    child: str
    parent: str


@dataclass(frozen=True)
class LifetimeScopeGraph:
    scopes: tuple[str, ...]
    containment: tuple[ScopeRelation, ...]

    def contains(self, outer: str, inner: str) -> bool:
        if outer == inner:
            return outer in self.scopes
        parents: dict[str, set[str]] = {scope: set() for scope in self.scopes}
        for relation in self.containment:
            parents[relation.child].add(relation.parent)
        pending = [inner]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if outer in parents.get(current, set()):
                return True
            pending.extend(parents.get(current, ()))
        return False

    def validate(self) -> None:
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError("lifetime scopes must be unique")
        declared = set(self.scopes)
        for relation in self.containment:
            if relation.child not in declared or relation.parent not in declared:
                raise ValueError(f"scope relation references undeclared scope: {relation}")
            if relation.child == relation.parent:
                raise ValueError(f"scope cannot contain itself: {relation.child}")
        for scope in self.scopes:
            if self._has_cycle(scope, scope, set()):
                raise ValueError(f"lifetime scope containment contains a cycle at {scope}")

    def _has_cycle(self, origin: str, current: str, seen: set[str]) -> bool:
        parents = [item.parent for item in self.containment if item.child == current]
        for parent in parents:
            if parent == origin:
                return True
            if parent not in seen and self._has_cycle(origin, parent, seen | {parent}):
                return True
        return False


@dataclass(frozen=True)
class RealizationPolicy:
    scope: str
    placement: str
    construction: str
    consistency: str
    publication: str


@dataclass(frozen=True)
class LifetimeConsumer:
    id: str
    scope: str
    independent_observer: bool


@dataclass(frozen=True)
class LifetimeCost:
    construction_ns: float
    access_ns: float
    retention_byte_ns: float
    invalidation_ns: float
    transfer_ns: float


@dataclass(frozen=True)
class LifetimeInformation:
    id: str
    source: tuple[str, ...]
    representation: str
    realization_kind: str
    owner: str
    readers: tuple[str, ...]
    writers: tuple[str, ...]
    validity_start: str
    invalidation_frontier: str
    final_use_frontier: str
    current: RealizationPolicy
    candidate_scopes: tuple[str, ...]
    candidate_placements: tuple[str, ...]
    consumers: tuple[LifetimeConsumer, ...]
    mutations: tuple[str, ...]
    invalidators: tuple[str, ...]
    non_invalidators: tuple[str, ...]
    mutation_dependencies: tuple[str, ...]
    alias_set: str
    byte_size: int
    fallback: str
    proof_class: str
    traits: tuple[str, ...]
    costs: LifetimeCost
    implementation: dict[str, Any]
    expected_family: str | None
    benchmark_case: str | None


@dataclass(frozen=True)
class LifetimeNode:
    id: str
    kind: str
    information_id: str
    attributes: dict[str, Any]
    provenance: str
    semantic_obligation: str


@dataclass(frozen=True)
class LifetimeEdge:
    id: str
    src: str
    dst: str
    semantic_source_identity: str
    representation_type: str
    owner: str
    readers: tuple[str, ...]
    writers: tuple[str, ...]
    validity_start: str
    invalidation_frontier: str
    final_use_frontier: str
    current_realization_scope: str
    candidate_realization_scopes: tuple[str, ...]
    mutation_dependency_set: tuple[str, ...]
    alias_set: str
    publication_protocol: str
    consistency_model: str
    physical_placement: str
    byte_size: int
    construction_cost_ns: float
    access_count: int
    observed_reuse_count: int
    transfer_count: int
    proof_class: str
    fallback_path: str


@dataclass(frozen=True)
class LifetimeFlowGraph:
    schema_version: str
    name: str
    domain: str
    manifest_hash: str
    graph_hash: str
    scopes: LifetimeScopeGraph
    information: tuple[LifetimeInformation, ...]
    nodes: tuple[LifetimeNode, ...]
    edges: tuple[LifetimeEdge, ...]
    contract: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def item(self, information_id: str) -> LifetimeInformation:
        for item in self.information:
            if item.id == information_id:
                return item
        raise KeyError(f"unknown lifetime information item: {information_id}")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _tuple_strings(value: Any, name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "non-empty " if nonempty else ""
        raise ValueError(f"{name} must be a {qualifier}list")
    return tuple(str(item) for item in value)


def _policy(raw: Any, name: str, scopes: LifetimeScopeGraph) -> RealizationPolicy:
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be a mapping")
    required = {"scope", "placement", "construction", "consistency", "publication"}
    missing = required - set(raw)
    if missing:
        raise ValueError(f"{name} missing: {', '.join(sorted(missing))}")
    scope = str(raw["scope"])
    if scope not in scopes.scopes:
        raise ValueError(f"{name} references unknown scope: {scope}")
    return RealizationPolicy(*(str(raw[key]) for key in ("scope", "placement", "construction", "consistency", "publication")))


def _parse_information(raw: Any, scopes: LifetimeScopeGraph) -> LifetimeInformation:
    if not isinstance(raw, dict):
        raise ValueError("information item must be a mapping")
    required = {
        "id", "source", "representation", "realization_kind", "owner", "readers", "writers",
        "validity_start", "invalidation_frontier", "final_use_frontier", "current",
        "candidate_scopes", "candidate_placements", "consumers", "mutations", "invalidators",
        "non_invalidators", "mutation_dependencies", "alias_set", "byte_size", "fallback",
        "proof_class", "traits", "costs", "implementation",
    }
    missing = required - set(raw)
    if missing:
        raise ValueError(f"information item {raw.get('id', '<unknown>')} missing: {', '.join(sorted(missing))}")
    realization_kind = str(raw["realization_kind"])
    if realization_kind not in REALIZATION_NODE_KINDS:
        raise ValueError(f"unsupported realization kind: {realization_kind}")
    consumers_raw = raw["consumers"]
    if not isinstance(consumers_raw, list) or not consumers_raw:
        raise ValueError(f"information item {raw['id']} requires consumers")
    consumers = tuple(
        LifetimeConsumer(str(item["id"]), str(item["scope"]), bool(item.get("independent_observer", False)))
        for item in consumers_raw
    )
    candidate_scopes = _tuple_strings(raw["candidate_scopes"], "candidate_scopes", nonempty=True)
    used_scopes = set(candidate_scopes) | {consumer.scope for consumer in consumers}
    unknown_scopes = sorted(used_scopes - set(scopes.scopes))
    if unknown_scopes:
        raise ValueError(f"information item {raw['id']} uses unknown scopes: {unknown_scopes}")
    mutations = _tuple_strings(raw["mutations"], "mutations")
    invalidators = _tuple_strings(raw["invalidators"], "invalidators")
    non_invalidators = _tuple_strings(raw["non_invalidators"], "non_invalidators")
    if set(invalidators) & set(non_invalidators):
        raise ValueError(f"information item {raw['id']} has overlapping invalidators and non-invalidators")
    if set(invalidators) | set(non_invalidators) != set(mutations):
        raise ValueError(f"information item {raw['id']} must classify every mutation")
    dependencies = _tuple_strings(raw["mutation_dependencies"], "mutation_dependencies")
    if not set(dependencies) <= set(mutations):
        raise ValueError(f"information item {raw['id']} has undeclared mutation dependencies")
    costs_raw = raw["costs"]
    if not isinstance(costs_raw, dict):
        raise ValueError(f"information item {raw['id']} costs must be a mapping")
    costs = LifetimeCost(*(float(costs_raw.get(key, 0.0)) for key in (
        "construction_ns", "access_ns", "retention_byte_ns", "invalidation_ns", "transfer_ns"
    )))
    byte_size = int(raw["byte_size"])
    if byte_size < 0:
        raise ValueError("byte_size cannot be negative")
    fallback = str(raw["fallback"])
    if not fallback:
        raise ValueError(f"information item {raw['id']} requires a fallback")
    return LifetimeInformation(
        id=str(raw["id"]),
        source=_tuple_strings(raw["source"], "source", nonempty=True),
        representation=str(raw["representation"]),
        realization_kind=realization_kind,
        owner=str(raw["owner"]),
        readers=_tuple_strings(raw["readers"], "readers", nonempty=True),
        writers=_tuple_strings(raw["writers"], "writers", nonempty=True),
        validity_start=str(raw["validity_start"]),
        invalidation_frontier=str(raw["invalidation_frontier"]),
        final_use_frontier=str(raw["final_use_frontier"]),
        current=_policy(raw["current"], "current", scopes),
        candidate_scopes=candidate_scopes,
        candidate_placements=_tuple_strings(raw["candidate_placements"], "candidate_placements", nonempty=True),
        consumers=consumers,
        mutations=mutations,
        invalidators=invalidators,
        non_invalidators=non_invalidators,
        mutation_dependencies=dependencies,
        alias_set=str(raw["alias_set"]),
        byte_size=byte_size,
        fallback=fallback,
        proof_class=str(raw["proof_class"]),
        traits=_tuple_strings(raw["traits"], "traits"),
        costs=costs,
        implementation=dict(raw["implementation"]),
        expected_family=str(raw["expected_family"]) if raw.get("expected_family") else None,
        benchmark_case=str(raw["benchmark_case"]) if raw.get("benchmark_case") else None,
    )


def load_lifetime_flow_graph(path: Path | str) -> LifetimeFlowGraph:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("lifetime manifest root must be a mapping")
    required = {"schema_version", "name", "domain", "scopes", "contract", "information_items"}
    missing = required - set(raw)
    if missing:
        raise ValueError("lifetime manifest missing: " + ", ".join(sorted(missing)))
    if raw["schema_version"] != "vladder-lifetime-manifest-v1":
        raise ValueError("unsupported lifetime manifest schema")
    scopes_raw = raw["scopes"]
    if not isinstance(scopes_raw, dict):
        raise ValueError("scopes must be a mapping")
    names = _tuple_strings(scopes_raw.get("names"), "scopes.names", nonempty=True)
    relations_raw = scopes_raw.get("containment")
    if not isinstance(relations_raw, list):
        raise ValueError("scopes.containment must be a list")
    relations = tuple(ScopeRelation(str(item[0]), str(item[1])) for item in relations_raw)
    scopes = LifetimeScopeGraph(names, relations)
    scopes.validate()
    information = tuple(_parse_information(item, scopes) for item in raw["information_items"])
    ids = [item.id for item in information]
    if len(set(ids)) != len(ids):
        raise ValueError("information item ids must be unique")
    nodes, edges = _build_graph(information)
    manifest_payload = json.loads(json.dumps(raw, sort_keys=True))
    manifest_hash = _canonical_hash(manifest_payload)
    graph_payload = {
        "scopes": asdict(scopes),
        "information": [asdict(item) for item in information],
        "nodes": [asdict(node) for node in nodes],
        "edges": [asdict(edge) for edge in edges],
        "contract": raw["contract"],
    }
    return LifetimeFlowGraph(
        "vladder-lifetime-flow-graph-v1",
        str(raw["name"]),
        str(raw["domain"]),
        manifest_hash,
        _canonical_hash(graph_payload),
        scopes,
        information,
        nodes,
        edges,
        dict(raw["contract"]),
        {"manifest": str(path.resolve()), "schema": str(raw["schema_version"])},
    )


def _build_graph(information: Iterable[LifetimeInformation]) -> tuple[tuple[LifetimeNode, ...], tuple[LifetimeEdge, ...]]:
    nodes: list[LifetimeNode] = []
    edges: list[LifetimeEdge] = []
    for item in information:
        prefix = item.id
        source_id = f"{prefix}:authority"
        derived_id = f"{prefix}:derived"
        construct_id = f"{prefix}:construct"
        realization_id = f"{prefix}:realization"
        publish_id = f"{prefix}:publish"
        nodes.extend((
            LifetimeNode(source_id, "AuthoritativeState", prefix, {"sources": list(item.source)}, "manifest.source", "authoritative semantic identity"),
            LifetimeNode(derived_id, "DerivedInformation", prefix, {"representation": item.representation}, "manifest.representation", "derivation correctness"),
            LifetimeNode(construct_id, "Construct", prefix, {"scope": item.current.scope}, "manifest.current.construction", "construct once per policy scope"),
            LifetimeNode(realization_id, item.realization_kind, prefix, {"placement": item.current.placement, "bytes": item.byte_size}, "manifest.current", "realization equals derived information"),
            LifetimeNode(publish_id, "Publish", prefix, {"protocol": item.current.publication}, "manifest.current.publication", "readers observe complete realization"),
        ))
        chain = ((source_id, derived_id), (derived_id, construct_id), (construct_id, realization_id), (realization_id, publish_id))
        for index, (src, dst) in enumerate(chain):
            edges.append(_edge(item, f"{prefix}:edge:{index}", src, dst))
        for mutation in item.mutations:
            mutation_id = f"{prefix}:mutation:{mutation}"
            kind = "InvalidationEvent" if mutation in item.invalidators else "Mutation"
            nodes.append(LifetimeNode(mutation_id, kind, prefix, {"mutation": mutation}, "manifest.mutations", "invalidation classification complete"))
            edges.append(_edge(item, f"{mutation_id}:edge", mutation_id, realization_id))
        for consumer in item.consumers:
            observation_id = f"{prefix}:observation:{consumer.id}"
            nodes.append(LifetimeNode(observation_id, "Observation", prefix, {"scope": consumer.scope, "independent": consumer.independent_observer}, "manifest.consumers", "consumer equivalence"))
            edges.append(_edge(item, f"{observation_id}:edge", publish_id, observation_id))
        retire_id = f"{prefix}:retire"
        fallback_id = f"{prefix}:fallback"
        nodes.extend((
            LifetimeNode(retire_id, "Retire", prefix, {"frontier": item.final_use_frontier}, "manifest.final_use_frontier", "no read after retirement"),
            LifetimeNode(fallback_id, "FallbackRecompute", prefix, {"path": item.fallback}, "manifest.fallback", "fallback preserves baseline semantics"),
        ))
        edges.append(_edge(item, f"{retire_id}:edge", publish_id, retire_id))
        edges.append(_edge(item, f"{fallback_id}:edge", fallback_id, publish_id))
    return tuple(nodes), tuple(edges)


def _edge(item: LifetimeInformation, edge_id: str, src: str, dst: str) -> LifetimeEdge:
    return LifetimeEdge(
        edge_id, src, dst, "+".join(item.source), item.representation, item.owner,
        item.readers, item.writers, item.validity_start, item.invalidation_frontier,
        item.final_use_frontier, item.current.scope, item.candidate_scopes,
        item.mutation_dependencies, item.alias_set, item.current.publication,
        item.current.consistency, item.current.placement, item.byte_size,
        item.costs.construction_ns, 0, 0, 0, item.proof_class, item.fallback,
    )


def emit_lifetime_dot(graph: LifetimeFlowGraph) -> str:
    lines = ["digraph LifetimeFlowGraph {", "  rankdir=LR;"]
    for node in graph.nodes:
        label = f"{node.information_id}\\n{node.kind}"
        lines.append(f'  "{node.id}" [label="{label}"];')
    for edge in graph.edges:
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{edge.current_realization_scope}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"
