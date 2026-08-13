from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field, replace
import gc
import hashlib
import itertools
import json
import threading
import time
import tracemalloc
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from .lazy_search import (
    ExpansionDecision,
    LazyGrammar,
    LazySearchResult,
    LazyState,
    LazyTraceNode,
    StableFrontierPolicy,
)


CANONICAL_SEARCH_VERSION = "canonical-state-search-v1"
CANONICAL_STATE_SCHEMA_VERSION = "vladder-canonical-state-dag-v1"
CANONICAL_STATE_ID_VERSION = "canonical-semantic-state-v2"


_PRESERVED_SEMANTIC_KEYS = frozenset({
    "alias", "alias_set", "atomic", "authority", "consistency", "contracts",
    "element_type", "externally_visible", "hardware_constraints", "lifetime", "memory_order",
    "memory_space", "observable", "owner", "ownership", "precision", "protocol", "sync",
    "synchronization", "type", "volatile",
})
_DEFAULT_VOLATILE_KEYS = frozenset({
    "captured_at", "elapsed_ms", "generated_at", "process_id", "run_id", "timestamp",
    "wall_clock", "wall_ms",
})


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (set, frozenset)):
        values = [_stable_value(item) for item in value]
        return sorted(values, key=lambda item: _json_bytes(item))
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, float):
        if value != value:
            return {"$float": "nan"}
        if value == float("inf"):
            return {"$float": "+inf"}
        if value == float("-inf"):
            return {"$float": "-inf"}
        if value == 0.0:
            return 0.0
    return value


@dataclass(frozen=True)
class CanonicalizationPolicy:
    volatile_keys: frozenset[str] = _DEFAULT_VOLATILE_KEYS
    nonobservable_ids: tuple[str, ...] = ()
    enable_alpha: bool = True
    enable_symmetry: bool = True
    maximum_symmetry_permutations: int = 4096


@dataclass(frozen=True)
class CanonicalEnvelope:
    digest: str
    canonical_bytes: bytes
    raw_digest: str
    observable_digest: str
    contract_digest: str
    component_hashes: tuple[tuple[str, str], ...]
    alpha_renames: int = 0
    symmetry_permutations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_schema_version": CANONICAL_STATE_ID_VERSION,
            "digest": self.digest,
            "raw_digest": self.raw_digest,
            "observable_digest": self.observable_digest,
            "contract_digest": self.contract_digest,
            "component_hashes": dict(self.component_hashes),
            "canonical_size_bytes": len(self.canonical_bytes),
            "alpha_renames": self.alpha_renames,
            "symmetry_permutations": self.symmetry_permutations,
        }


class Canonicalizer:
    """Typed canonical serialization with explicit, conservative identity erasure.

    Mapping and set order is never semantic. Sequence order remains semantic unless the sequence is
    a graph node/edge collection. Identity normalization is opt-in through ``_nonobservable_ids`` or
    per-node ``symmetry_class`` plus ``identity_observable: false``.
    """

    def __init__(self, policy: CanonicalizationPolicy | None = None) -> None:
        self.policy = policy or CanonicalizationPolicy()

    def envelope(self, state: LazyState) -> CanonicalEnvelope:
        raw = {
            "stage": state.stage,
            "terminal": state.terminal,
            "semantic_state": _stable_value(dict(state.semantic_state)),
        }
        explicit_ids = set(self.policy.nonobservable_ids)
        state_ids = state.semantic_state.get("_nonobservable_ids", ())
        if isinstance(state_ids, (list, tuple, set, frozenset)):
            explicit_ids.update(str(item) for item in state_ids)
        normalized, alpha_count, symmetry_count = self._normalize(raw, explicit_ids)
        canonical_bytes = _json_bytes(normalized)
        observables = self._semantic_projection(normalized, "observables")
        contracts = self._semantic_projection(normalized, "contracts")
        semantic = normalized.get("semantic_state", {}) if isinstance(normalized, Mapping) else {}
        component_hashes = tuple(
            (str(key), _digest(_json_bytes(value)))
            for key, value in sorted(semantic.items())
            if not str(key).startswith("_")
        ) if isinstance(semantic, Mapping) else ()
        return CanonicalEnvelope(
            _digest(canonical_bytes),
            canonical_bytes,
            _digest(_json_bytes(raw)),
            _digest(_json_bytes(observables)),
            _digest(_json_bytes(contracts)),
            component_hashes,
            alpha_count,
            symmetry_count,
        )

    def _normalize(self, value: Any, explicit_ids: set[str]) -> tuple[Any, int, int]:
        identities = tuple(sorted(explicit_ids)) if self.policy.enable_alpha else ()
        permutations = _factorial_bounded(len(identities), self.policy.maximum_symmetry_permutations)
        assignments: Iterable[tuple[str, ...]]
        if identities and permutations <= self.policy.maximum_symmetry_permutations:
            assignments = itertools.permutations(tuple(f"@alpha:{index}" for index in range(len(identities))))
        else:
            assignments = (tuple(f"@alpha:{index}" for index in range(len(identities))),)
        best: bytes | None = None
        best_value: Any = None
        best_alpha_count = 0
        best_symmetry_count = 0
        for assignment in assignments:
            alpha_map = dict(zip(identities, assignment, strict=True))
            alpha_count = 0

            def walk(item: Any) -> Any:
                nonlocal alpha_count
                if isinstance(item, str) and item in alpha_map:
                    alpha_count += 1
                    return alpha_map[item]
                if isinstance(item, Mapping):
                    filtered = {
                        str(key): child
                        for key, child in item.items()
                        if str(key) not in self.policy.volatile_keys and str(key) != "_nonobservable_ids"
                    }
                    if "nodes" in filtered and "edges" in filtered:
                        graph, symmetry_count = self._normalize_graph(filtered, walk)
                        graph["_canonical_symmetry_permutations"] = symmetry_count
                        return graph
                    return {key: walk(child) for key, child in sorted(filtered.items())}
                if isinstance(item, (set, frozenset)):
                    return sorted((walk(child) for child in item), key=_json_bytes)
                if isinstance(item, tuple):
                    return [walk(child) for child in item]
                if isinstance(item, list):
                    return [walk(child) for child in item]
                return _stable_value(item)

            normalized = walk(value)
            symmetry_count = self._remove_symmetry_counters(normalized)
            encoded = _json_bytes(normalized)
            if best is None or encoded < best:
                best = encoded
                best_value = normalized
                best_alpha_count = alpha_count
                best_symmetry_count = symmetry_count
        return best_value, best_alpha_count, best_symmetry_count

    @staticmethod
    def _remove_symmetry_counters(value: Any) -> int:
        total = 0
        if isinstance(value, dict):
            total += int(value.pop("_canonical_symmetry_permutations", 0))
            for child in value.values():
                total += Canonicalizer._remove_symmetry_counters(child)
        elif isinstance(value, list):
            for child in value:
                total += Canonicalizer._remove_symmetry_counters(child)
        return total

    def _normalize_graph(
        self,
        graph: Mapping[str, Any],
        walk: Callable[[Any], Any],
    ) -> tuple[dict[str, Any], int]:
        raw_nodes = [dict(item) for item in graph.get("nodes", ()) if isinstance(item, Mapping)]
        raw_edges = [dict(item) for item in graph.get("edges", ()) if isinstance(item, Mapping)]
        fixed_nodes: list[dict[str, Any]] = []
        classes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in raw_nodes:
            symmetry_class = node.get("symmetry_class")
            interchangeable = (
                self.policy.enable_symmetry
                and symmetry_class is not None
                and node.get("identity_observable") is False
            )
            if interchangeable:
                classes[str(symmetry_class)].append(node)
            else:
                fixed_nodes.append(node)
        permutation_count = 1
        for nodes in classes.values():
            permutation_count *= _factorial_bounded(len(nodes), self.policy.maximum_symmetry_permutations)
        if not classes or permutation_count > self.policy.maximum_symmetry_permutations:
            nodes = sorted((walk(node) for node in raw_nodes), key=_json_bytes)
            edges = sorted((walk(edge) for edge in raw_edges), key=_json_bytes)
            rest = {key: walk(value) for key, value in graph.items() if key not in {"nodes", "edges"}}
            return {**rest, "nodes": nodes, "edges": edges}, 0

        class_permutations = []
        for name, nodes in sorted(classes.items()):
            class_permutations.append((name, tuple(itertools.permutations(nodes))))
        best: bytes | None = None
        best_graph: dict[str, Any] | None = None
        explored = 0
        for choices in itertools.product(*(item[1] for item in class_permutations)):
            mapping: dict[str, str] = {}
            renamed_nodes = [dict(node) for node in fixed_nodes]
            for (class_name, _), permutation in zip(class_permutations, choices, strict=True):
                for index, node in enumerate(permutation):
                    old_id = str(node.get("id"))
                    new_id = f"@sym:{class_name}:{index}"
                    mapping[old_id] = new_id
                    renamed = dict(node)
                    renamed["id"] = new_id
                    renamed_nodes.append(renamed)
            renamed_edges = [_replace_graph_ids(edge, mapping) for edge in raw_edges]
            rest = {key: walk(value) for key, value in graph.items() if key not in {"nodes", "edges"}}
            candidate = {
                **rest,
                "nodes": sorted((walk(node) for node in renamed_nodes), key=_json_bytes),
                "edges": sorted((walk(edge) for edge in renamed_edges), key=_json_bytes),
            }
            encoded = _json_bytes(candidate)
            explored += 1
            if best is None or encoded < best:
                best = encoded
                best_graph = candidate
        assert best_graph is not None
        return best_graph, explored

    @staticmethod
    def _semantic_projection(value: Any, key: str) -> Any:
        if not isinstance(value, Mapping):
            return {}
        semantic = value.get("semantic_state", {})
        if not isinstance(semantic, Mapping):
            return {}
        if key in semantic:
            return semantic[key]
        if key == "contracts":
            return {
                field: semantic[field]
                for field in sorted(semantic)
                if field in _PRESERVED_SEMANTIC_KEYS or "contract" in field
            }
        return {
            field: semantic[field]
            for field in sorted(semantic)
            if field in _PRESERVED_SEMANTIC_KEYS or field.startswith("observable")
        }


def _factorial_bounded(value: int, bound: int) -> int:
    result = 1
    for current in range(2, value + 1):
        result *= current
        if result > bound:
            return result
    return result


def _replace_graph_ids(value: Any, mapping: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, Mapping):
        return {str(key): _replace_graph_ids(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_graph_ids(item, mapping) for item in value]
    if isinstance(value, tuple):
        return [_replace_graph_ids(item, mapping) for item in value]
    return value


@dataclass(frozen=True)
class CanonicalSearchEdge:
    edge_id: str
    parent_state_id: str | None
    child_state_id: str
    action: dict[str, Any]
    depth: int
    disposition: str = "new_state"


@dataclass
class CanonicalStateRecord:
    state_id: str
    envelope: CanonicalEnvelope
    state: LazyState
    first_discovery_path: tuple[dict[str, Any], ...]
    parent_edges: list[str] = field(default_factory=list)
    depth_minimum: int = 0
    depth_maximum: int = 0
    enabled_actions: tuple[str, ...] = ()
    proof_status: str = "not_evaluated"
    compiler_status: str = "not_evaluated"
    terminal_status: str = "nonterminal"
    descendant_status: str = "unknown"
    exploration_status: str = "queued"
    summaries: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "canonical": self.envelope.to_dict(),
            "family": self.state.family,
            "stage": self.state.stage,
            "terminal": self.state.terminal,
            "semantic_state": dict(self.state.semantic_state),
            "first_discovery_path": list(self.first_discovery_path),
            "parent_edges": sorted(self.parent_edges),
            "depth_minimum": self.depth_minimum,
            "depth_maximum": self.depth_maximum,
            "enabled_actions": list(self.enabled_actions),
            "proof_status": self.proof_status,
            "compiler_status": self.compiler_status,
            "terminal_status": self.terminal_status,
            "descendant_status": self.descendant_status,
            "exploration_status": self.exploration_status,
            "summaries": self.summaries,
        }


class TranspositionTable:
    """Digest-indexed table where canonical bytes remain authoritative."""

    def __init__(self, canonicalizer: Canonicalizer | None = None) -> None:
        self.canonicalizer = canonicalizer or Canonicalizer()
        self._buckets: dict[str, list[CanonicalStateRecord]] = defaultdict(list)
        self.records: dict[str, CanonicalStateRecord] = {}
        self.hash_collisions = 0
        self._lock = threading.RLock()

    def intern(
        self,
        state: LazyState,
        *,
        depth: int,
        path: tuple[dict[str, Any], ...],
        edge_id: str,
    ) -> tuple[CanonicalStateRecord, bool, str]:
        envelope = self.canonicalizer.envelope(state)
        with self._lock:
            for record in self._buckets[envelope.digest]:
                if (
                    record.envelope.canonical_bytes == envelope.canonical_bytes
                    and record.envelope.observable_digest == envelope.observable_digest
                    and record.envelope.contract_digest == envelope.contract_digest
                ):
                    if edge_id not in record.parent_edges:
                        record.parent_edges.append(edge_id)
                    record.depth_minimum = min(record.depth_minimum, depth)
                    record.depth_maximum = max(record.depth_maximum, depth)
                    candidate_path = tuple(path)
                    if _json_bytes(candidate_path) < _json_bytes(record.first_discovery_path):
                        record.first_discovery_path = candidate_path
                    mechanism = "exact_transposition"
                    if record.envelope.raw_digest != envelope.raw_digest:
                        if envelope.symmetry_permutations:
                            mechanism = "symmetry"
                        elif envelope.alpha_renames:
                            mechanism = "alpha_equivalence"
                    return record, False, mechanism
                self.hash_collisions += 1
            # The secondary byte digest makes forced primary-hash collisions deterministic across
            # worker registration order. Canonical bytes, not either digest, remain authoritative.
            byte_digest = _digest(envelope.canonical_bytes)
            state_id = f"{CANONICAL_STATE_ID_VERSION}:{envelope.digest}:{byte_digest[:16]}"
            record = CanonicalStateRecord(
                state_id,
                envelope,
                state,
                tuple(path),
                [edge_id],
                depth,
                depth,
                terminal_status="terminal" if state.terminal else "nonterminal",
            )
            self._buckets[envelope.digest].append(record)
            self.records[state_id] = record
            return record, True, "new_state"

    def restore(self, record: CanonicalStateRecord) -> None:
        """Restore one checkpointed record after clean canonical rematerialization."""

        clean = self.canonicalizer.envelope(record.state)
        if clean.canonical_bytes != record.envelope.canonical_bytes:
            raise ValueError("checkpoint canonical state differs from clean rematerialization")
        expected_id = (
            f"{CANONICAL_STATE_ID_VERSION}:{clean.digest}:"
            f"{_digest(clean.canonical_bytes)[:16]}"
        )
        if record.state_id != expected_id:
            raise ValueError("checkpoint canonical state identity is incompatible")
        with self._lock:
            self._buckets[clean.digest].append(record)
            self.records[record.state_id] = record


@dataclass(frozen=True)
class ActionFootprint:
    action_key: str
    reads: frozenset[str] = frozenset()
    writes: frozenset[str] = frozenset()
    owners: frozenset[str] = frozenset()
    aliases: frozenset[str] = frozenset()
    lifetimes: frozenset[str] = frozenset()
    representations: frozenset[str] = frozenset()
    contracts_read: frozenset[str] = frozenset()
    contracts_write: frozenset[str] = frozenset()
    authorities: frozenset[str] = frozenset()
    memory_spaces: frozenset[str] = frozenset()
    representations_read: frozenset[str] = frozenset()
    representations_written: frozenset[str] = frozenset()
    lifetimes_read: frozenset[str] = frozenset()
    lifetimes_modified: frozenset[str] = frozenset()
    authority_read: frozenset[str] = frozenset()
    authority_modified: frozenset[str] = frozenset()
    synchronization_effects: frozenset[str] = frozenset()
    external_observable_effects: frozenset[str] = frozenset()
    requires: frozenset[str] = frozenset()
    conflicts: frozenset[str] = frozenset()
    complete: bool = False

    @classmethod
    def from_action(cls, action: Mapping[str, Any]) -> "ActionFootprint":
        raw = action.get("footprint", {})
        if not isinstance(raw, Mapping):
            raw = {}
        action_key = str(action.get("action_key") or action.get("id") or _json_action_key(action))

        def values(name: str) -> frozenset[str]:
            value = raw.get(name, action.get(name, ()))
            if isinstance(value, str):
                return frozenset((value,))
            if isinstance(value, (list, tuple, set, frozenset)):
                return frozenset(str(item) for item in value)
            return frozenset()

        representations_read = values("representations_read")
        representations_written = values("representations_written")
        lifetimes_read = values("lifetimes_read")
        lifetimes_modified = values("lifetimes_modified")
        authority_read = values("authority_read")
        authority_modified = values("authority_modified")
        return cls(
            action_key,
            values("reads"), values("writes"), values("owners"), values("aliases"),
            values("lifetimes"), values("representations"), values("contracts_read"),
            values("contracts_write"), values("authorities"), values("memory_spaces"),
            representations_read, representations_written, lifetimes_read, lifetimes_modified,
            authority_read, authority_modified, values("synchronization_effects"),
            values("external_observable_effects"), values("requires"), values("conflicts"),
            bool(raw.get("complete", action.get("footprint_complete", False))),
        )


def _json_action_key(action: Mapping[str, Any]) -> str:
    public = {str(key): value for key, value in action.items() if key != "footprint"}
    return _digest(_json_bytes(_stable_value(public)))


@dataclass(frozen=True)
class IndependenceEvidence:
    independent: bool
    reason: str
    static_screen_passed: bool = False
    dynamic_orders_equal: bool = False
    left_then_right: str | None = None
    right_then_left: str | None = None


class ActionApplicator(Protocol):
    def apply_action(
        self, state: LazyState | None, action: Mapping[str, Any], root_context: Mapping[str, Any]
    ) -> LazyState | None: ...


class IndependenceVerifier:
    def __init__(self, canonicalizer: Canonicalizer | None = None) -> None:
        self.canonicalizer = canonicalizer or Canonicalizer()
        self._cache: dict[tuple[str, str, str], IndependenceEvidence] = {}

    @staticmethod
    def static_screen(left: ActionFootprint, right: ActionFootprint) -> tuple[bool, str]:
        if not left.complete or not right.complete:
            return False, "unknown footprint is dependent"
        if left.action_key in right.conflicts or right.action_key in left.conflicts:
            return False, "declared action conflict"
        if left.writes & (right.reads | right.writes) or right.writes & (left.reads | left.writes):
            return False, "read/write dependency"
        if left.aliases & right.aliases:
            return False, "shared alias region"
        if left.contracts_write & (right.contracts_read | right.contracts_write):
            return False, "left contract dependency"
        if right.contracts_write & (left.contracts_read | left.contracts_write):
            return False, "right contract dependency"
        if left.representations_written & (
            right.representations_read | right.representations_written
        ) or right.representations_written & (
            left.representations_read | left.representations_written
        ):
            return False, "representation dependency"
        if left.lifetimes_modified & (
            right.lifetimes_read | right.lifetimes_modified
        ) or right.lifetimes_modified & (
            left.lifetimes_read | left.lifetimes_modified
        ):
            return False, "lifetime dependency"
        if left.authority_modified & (
            right.authority_read | right.authority_modified
        ) or right.authority_modified & (
            left.authority_read | left.authority_modified
        ):
            return False, "authority dependency"
        if left.synchronization_effects or right.synchronization_effects:
            return False, "synchronization effects require explicit ordering"
        if left.external_observable_effects or right.external_observable_effects:
            return False, "external observable effects require explicit ordering"
        if left.authorities & right.authorities or left.lifetimes & right.lifetimes:
            return False, "shared authority or lifetime state"
        if left.memory_spaces & right.memory_spaces and not left.owners.isdisjoint(right.owners):
            return False, "shared physical placement"
        if left.owners and right.owners and not left.owners.isdisjoint(right.owners):
            return False, "shared semantic owner"
        return True, "conservative footprints are disjoint"

    def verify(
        self,
        grammar: LazyGrammar,
        state: LazyState | None,
        left_action: Mapping[str, Any],
        right_action: Mapping[str, Any],
        root_context: Mapping[str, Any],
    ) -> IndependenceEvidence:
        state_hash = "root" if state is None else self.canonicalizer.envelope(state).digest
        left = ActionFootprint.from_action(left_action)
        right = ActionFootprint.from_action(right_action)
        key = (state_hash, left.action_key, right.action_key)
        reverse_key = (state_hash, right.action_key, left.action_key)
        if key in self._cache:
            return self._cache[key]
        passed, reason = self.static_screen(left, right)
        if not passed:
            evidence = IndependenceEvidence(False, reason)
            self._cache[key] = self._cache[reverse_key] = evidence
            return evidence
        apply = getattr(grammar, "apply_action", None)
        if not callable(apply):
            evidence = IndependenceEvidence(False, "grammar has no exact action applicator", True)
            self._cache[key] = self._cache[reverse_key] = evidence
            return evidence
        left_state = apply(state, left_action, root_context)
        right_state = apply(state, right_action, root_context)
        left_right = apply(left_state, right_action, root_context) if left_state is not None else None
        right_left = apply(right_state, left_action, root_context) if right_state is not None else None
        if left_right is None or right_left is None:
            evidence = IndependenceEvidence(False, "both action orders are not legal", True)
        else:
            left_hash = self.canonicalizer.envelope(left_right).digest
            right_hash = self.canonicalizer.envelope(right_left).digest
            equal = (
                left_hash == right_hash
                and self.canonicalizer.envelope(left_right).canonical_bytes
                == self.canonicalizer.envelope(right_left).canonical_bytes
            )
            evidence = IndependenceEvidence(
                equal,
                "state-scoped AB/BA canonical equality" if equal else "AB/BA states differ",
                True,
                equal,
                left_hash,
                right_hash,
            )
        self._cache[key] = self._cache[reverse_key] = evidence
        return evidence


@dataclass(frozen=True)
class ReductionMetrics:
    raw_generated_states: int = 0
    unique_canonical_states: int = 0
    exact_transpositions: int = 0
    alpha_equivalent_collapses: int = 0
    symmetry_collapses: int = 0
    por_avoided_transitions: int = 0
    dependency_avoided_transitions: int = 0
    dominance_collapses: int = 0
    macro_collapses: int = 0
    egraph_equivalences: int = 0
    candidate_constructions: int = 0
    proof_calls: int = 0
    compiler_calls: int = 0
    search_wall_ms: float = 0.0
    canonicalization_wall_ms: float = 0.0
    maximum_frontier_size: int = 0
    hash_collisions: int = 0
    peak_memory_bytes: int = 0
    quotient_dag_edges: int = 0
    quotient_dag_edge_node_ratio: float = 0.0
    benchmark_calls: int = 0
    terminal_evaluation_wall_ms: float = 0.0
    por_wall_ms: float = 0.0
    dependency_wall_ms: float = 0.0
    action_footprint_complete: int = 0
    action_footprint_partial: int = 0
    action_footprint_missing: int = 0
    analysis_cache_hits: int = 0
    analysis_cache_misses: int = 0
    memory_cache_evictions: int = 0
    memory_ceiling_stops: int = 0


@dataclass(frozen=True)
class CanonicalSearchResult:
    schema_version: str
    engine_version: str
    mode: str
    por_strategy: str
    complete: bool
    states: tuple[CanonicalStateRecord, ...]
    edges: tuple[CanonicalSearchEdge, ...]
    terminal_state_ids: tuple[str, ...]
    terminal_canonical_hashes: tuple[str, ...]
    metrics: ReductionMetrics
    independence_evidence: tuple[IndependenceEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "mode": self.mode,
            "por_strategy": self.por_strategy,
            "complete": self.complete,
            "states": [state.to_dict() for state in self.states],
            "edges": [asdict(edge) for edge in self.edges],
            "terminal_state_ids": list(self.terminal_state_ids),
            "terminal_canonical_hashes": list(self.terminal_canonical_hashes),
            "metrics": asdict(self.metrics),
            "independence_evidence": [asdict(item) for item in self.independence_evidence],
        }


@dataclass(frozen=True)
class _WorkItem:
    state_id: str
    path: tuple[dict[str, Any], ...]
    path_states: tuple[LazyState | None, ...]


class CanonicalSearchEngine:
    """Complete search over unique canonical states with optionally qualified exact reductions."""

    def __init__(self, canonicalizer: Canonicalizer | None = None) -> None:
        self.canonicalizer = canonicalizer or Canonicalizer()

    def run(
        self,
        grammar: LazyGrammar,
        root_context: Mapping[str, Any],
        *,
        mode: str = "exhaustive_canonical",
        frontier_policy: Any | None = None,
        node_budget: int = 1_000_000,
        enable_por: bool | None = None,
        por_strategy: str = "dynamic",
        terminal_evaluator: Callable[[LazyState], Mapping[str, Any]] | None = None,
        por_decider: Callable[[LazyState, Sequence[Mapping[str, Any]], int, Mapping[str, Any]], bool] | None = None,
        action_observer: Callable[[LazyState, Mapping[str, Any]], None] | None = None,
        analysis_cache: Any | None = None,
        work_budget: int | None = None,
        time_budget_seconds: float | None = None,
        memory_ceiling_bytes: int | None = None,
        resume_from: CanonicalSearchResult | None = None,
    ) -> CanonicalSearchResult:
        if mode not in {"exhaustive_canonical", "exhaustive_reduced", "guided_reduced", "fast"}:
            raise ValueError(f"unsupported canonical search mode: {mode}")
        if node_budget < 1:
            raise ValueError("node budget must be positive")
        if por_strategy not in {"dynamic", "sleep_set"}:
            raise ValueError("POR strategy must be dynamic or sleep_set")
        if work_budget is not None and work_budget < 1:
            raise ValueError("work budget must be positive")
        if time_budget_seconds is not None and time_budget_seconds <= 0:
            raise ValueError("time budget must be positive")
        if memory_ceiling_bytes is not None and memory_ceiling_bytes < 1:
            raise ValueError("memory ceiling must be positive")
        por = mode in {"exhaustive_reduced", "guided_reduced", "fast"} if enable_por is None else enable_por
        policy = frontier_policy or StableFrontierPolicy()
        table = TranspositionTable(self.canonicalizer)
        independence = IndependenceVerifier(self.canonicalizer)
        evidence: dict[tuple[str | None, str | None], IndependenceEvidence] = {}
        edges: list[CanonicalSearchEdge] = []
        queue: deque[_WorkItem] = deque()
        terminal_ids: set[str] = set()
        counts: Counter[str] = Counter()
        canonicalization_wall_ms = 0.0
        previous_search_wall_ms = 0.0
        started = time.perf_counter()
        complete = True
        tracing_was_active = tracemalloc.is_tracing()
        if not tracing_was_active:
            tracemalloc.start()
        memory_start, _ = tracemalloc.get_traced_memory()

        def add_state(
            state: LazyState,
            parent_id: str | None,
            depth: int,
            path: tuple[dict[str, Any], ...],
            path_states: tuple[LazyState | None, ...],
        ) -> None:
            nonlocal canonicalization_wall_ms
            edge_id = _digest(_json_bytes({
                "parent": parent_id,
                "action": _stable_value(dict(state.action)),
                "depth": depth,
                "ordinal": len(edges),
            }))
            canonical_started = time.perf_counter()
            record, created, mechanism = table.intern(
                state, depth=depth, path=path, edge_id=edge_id,
            )
            canonicalization_wall_ms += (time.perf_counter() - canonical_started) * 1000.0
            disposition = "new_state" if created else mechanism
            edges.append(CanonicalSearchEdge(edge_id, parent_id, record.state_id, dict(state.action), depth, disposition))
            if created:
                counts["unique_canonical_states"] += 1
                queue.append(_WorkItem(record.state_id, path, path_states))
            else:
                counts[mechanism] += 1

        if resume_from is not None:
            if resume_from.schema_version != CANONICAL_STATE_SCHEMA_VERSION:
                raise ValueError("checkpoint canonical DAG schema is incompatible")
            if resume_from.engine_version != CANONICAL_SEARCH_VERSION:
                raise ValueError("checkpoint canonical search engine is incompatible")
            for original in resume_from.states:
                restored = replace(
                    original,
                    parent_edges=list(original.parent_edges),
                    summaries=dict(original.summaries),
                )
                table.restore(restored)
            edges.extend(resume_from.edges)
            terminal_ids.update(resume_from.terminal_state_ids)
            previous = resume_from.metrics
            counts.update({
                "raw_generated_states": previous.raw_generated_states,
                "unique_canonical_states": previous.unique_canonical_states,
                "exact_transposition": previous.exact_transpositions,
                "alpha_equivalence": previous.alpha_equivalent_collapses,
                "symmetry": previous.symmetry_collapses,
                "por_avoided_transitions": previous.por_avoided_transitions,
                "dependency_avoided_transitions": previous.dependency_avoided_transitions,
                "candidate_constructions": previous.candidate_constructions,
                "proof_calls": previous.proof_calls,
                "compiler_calls": previous.compiler_calls,
                "benchmark_calls": previous.benchmark_calls,
                "action_footprint_complete": previous.action_footprint_complete,
                "action_footprint_partial": previous.action_footprint_partial,
                "action_footprint_missing": previous.action_footprint_missing,
                "memory_cache_evictions": previous.memory_cache_evictions,
                "memory_ceiling_stops": previous.memory_ceiling_stops,
                "terminal_evaluation_wall_us": int(previous.terminal_evaluation_wall_ms * 1000.0),
                "por_wall_us": int(previous.por_wall_ms * 1000.0),
                "dependency_wall_us": int(previous.dependency_wall_ms * 1000.0),
            })
            canonicalization_wall_ms = previous.canonicalization_wall_ms
            previous_search_wall_ms = previous.search_wall_ms
            for record in table.records.values():
                if record.exploration_status == "queued":
                    path_states = _replay_path_states(grammar, root_context, record.first_discovery_path)
                    queue.append(_WorkItem(record.state_id, record.first_discovery_path, path_states))
        else:
            initial = tuple(grammar.initial_states(root_context))
            counts["raw_generated_states"] += len(initial)
            counts["candidate_constructions"] += len(initial)
            for state in initial:
                add_state(state, None, 0, (dict(state.action),), (None,))

        while queue:
            counts["maximum_frontier_size"] = max(counts["maximum_frontier_size"], len(queue))
            if counts["unique_canonical_states"] > node_budget:
                complete = False
                break
            if work_budget is not None and counts["candidate_constructions"] >= work_budget:
                complete = False
                break
            if time_budget_seconds is not None and time.perf_counter() - started >= time_budget_seconds:
                complete = False
                break
            if memory_ceiling_bytes is not None:
                memory_current, _ = tracemalloc.get_traced_memory()
                if memory_current - memory_start > memory_ceiling_bytes:
                    for cached_record in table.records.values():
                        if cached_record.summaries:
                            cached_record.summaries.clear()
                            counts["memory_cache_evictions"] += 1
                    if analysis_cache is not None and hasattr(analysis_cache, "clear_recomputable"):
                        analysis_cache.clear_recomputable()
                    gc.collect()
                    memory_current, _ = tracemalloc.get_traced_memory()
                    if memory_current - memory_start > memory_ceiling_bytes:
                        # Identity records remain resident. Stopping incomplete is fail-open: no
                        # state is declared absent and the run can be checkpointed/resumed.
                        counts["memory_ceiling_stops"] += 1
                        complete = False
                        break
            work = queue.popleft()
            record = table.records[work.state_id]
            state = record.state
            if record.exploration_status == "expanded":
                continue
            if state.terminal:
                record.exploration_status = "terminal"
                terminal_ids.add(record.state_id)
                if terminal_evaluator is not None:
                    terminal_started = time.perf_counter()
                    terminal_evidence = dict(terminal_evaluator(state))
                    counts["terminal_evaluation_wall_us"] += int(
                        (time.perf_counter() - terminal_started) * 1_000_000
                    )
                    record.proof_status = str(terminal_evidence.get("proof_status", "not_evaluated"))
                    record.compiler_status = str(terminal_evidence.get("compiler_status", "not_evaluated"))
                    counts["proof_calls"] += int(terminal_evidence.get("proof_calls", 0))
                    counts["compiler_calls"] += int(terminal_evidence.get("compiler_calls", 0))
                    counts["benchmark_calls"] += int(terminal_evidence.get("benchmark_calls", 0))
                continue
            enabled_actions = getattr(grammar, "enabled_actions", None)
            apply_action = getattr(grammar, "apply_action", None)
            action_native = callable(enabled_actions) and callable(apply_action)
            raw_actions: tuple[Mapping[str, Any], ...]
            preconstructed: dict[str, list[LazyState]] = defaultdict(list)
            if action_native:
                raw_actions = tuple(dict(action) for action in enabled_actions(state, root_context))
            else:
                children = tuple(grammar.expand(state, root_context))
                raw_actions = tuple(dict(child.action) for child in children)
                for child in children:
                    preconstructed[_json_action_key(child.action)].append(child)
                counts["candidate_constructions"] += len(children)
            counts["raw_generated_states"] += len(raw_actions)
            for action in raw_actions:
                footprint = ActionFootprint.from_action(action)
                if footprint.complete:
                    counts["action_footprint_complete"] += 1
                elif action.get("footprint"):
                    counts["action_footprint_partial"] += 1
                else:
                    counts["action_footprint_missing"] += 1
                if action_observer is not None:
                    action_observer(state, action)
            record.enabled_actions = tuple(sorted(ActionFootprint.from_action(action).action_key for action in raw_actions))
            state_por = por and (
                por_decider(state, raw_actions, record.depth_minimum, root_context)
                if por_decider is not None else True
            )
            viable_actions: list[Mapping[str, Any]] = []
            for action in raw_actions:
                dependency_started = time.perf_counter()
                dependency_blocked = self._dependency_blocked(action, work.path)
                counts["dependency_wall_us"] += int(
                    (time.perf_counter() - dependency_started) * 1_000_000
                )
                if dependency_blocked:
                    counts["dependency_avoided_transitions"] += 1
                    continue
                if state_por and work.path and len(work.path_states) >= 1:
                    previous_action = work.path[-1]
                    if _json_action_key(action) < _json_action_key(previous_action):
                        previous_state = work.path_states[-1]
                        por_started = time.perf_counter()
                        item = independence.verify(
                            grammar, previous_state, previous_action, action, root_context,
                        )
                        counts["por_wall_us"] += int(
                            (time.perf_counter() - por_started) * 1_000_000
                        )
                        evidence[(item.left_then_right, item.right_then_left)] = item
                        if item.independent:
                            counts["por_avoided_transitions"] += 1
                            continue
                viable_actions.append(action)
            realized: list[LazyState] = []
            for action in viable_actions:
                if action_native:
                    child = apply_action(state, action, root_context)
                    if child is None:
                        continue
                    counts["candidate_constructions"] += 1
                else:
                    bucket = preconstructed[_json_action_key(action)]
                    if not bucket:
                        continue
                    child = bucket.pop(0)
                realized.append(child)
            children = tuple(realized)
            if analysis_cache is not None and hasattr(analysis_cache, "get_or_compute"):
                record.summaries = analysis_cache.get_or_compute(
                    record.state_id,
                    "semantic_summaries",
                    lambda: self._summaries(state, children),
                )
            else:
                record.summaries = self._summaries(state, children)
            scored = policy.score(
                state,
                children,
                depth=record.depth_minimum + 1,
                history=work.path,
                root_context=root_context,
            )
            if len(scored) != len(children):
                raise ValueError("frontier policy must return one score per canonical child")
            ranked = sorted(zip(children, scored, strict=True), key=lambda item: -float(item[1].score))
            for child, _ in ranked:
                child_path = (*work.path, dict(child.action))
                child_states = (*work.path_states, state)
                add_state(child, record.state_id, record.depth_minimum + 1, child_path, child_states)
            record.exploration_status = "expanded"

        terminal_records = sorted((table.records[item] for item in terminal_ids), key=lambda item: item.state_id)
        _, memory_peak = tracemalloc.get_traced_memory()
        if not tracing_was_active:
            tracemalloc.stop()
        metrics = ReductionMetrics(
            raw_generated_states=counts["raw_generated_states"],
            unique_canonical_states=counts["unique_canonical_states"],
            exact_transpositions=counts["exact_transposition"],
            alpha_equivalent_collapses=counts["alpha_equivalence"],
            symmetry_collapses=counts["symmetry"],
            por_avoided_transitions=counts["por_avoided_transitions"],
            dependency_avoided_transitions=counts["dependency_avoided_transitions"],
            candidate_constructions=counts["candidate_constructions"],
            proof_calls=counts["proof_calls"],
            compiler_calls=counts["compiler_calls"],
            search_wall_ms=previous_search_wall_ms + (time.perf_counter() - started) * 1000.0,
            canonicalization_wall_ms=canonicalization_wall_ms,
            maximum_frontier_size=counts["maximum_frontier_size"],
            hash_collisions=table.hash_collisions,
            peak_memory_bytes=max(0, memory_peak - memory_start),
            quotient_dag_edges=len(edges),
            quotient_dag_edge_node_ratio=len(edges) / max(1, len(table.records)),
            benchmark_calls=counts["benchmark_calls"],
            terminal_evaluation_wall_ms=counts["terminal_evaluation_wall_us"] / 1000.0,
            por_wall_ms=counts["por_wall_us"] / 1000.0,
            dependency_wall_ms=counts["dependency_wall_us"] / 1000.0,
            action_footprint_complete=counts["action_footprint_complete"],
            action_footprint_partial=counts["action_footprint_partial"],
            action_footprint_missing=counts["action_footprint_missing"],
            analysis_cache_hits=int(getattr(analysis_cache, "hits", 0)),
            analysis_cache_misses=int(getattr(analysis_cache, "misses", 0)),
            memory_cache_evictions=counts["memory_cache_evictions"],
            memory_ceiling_stops=counts["memory_ceiling_stops"],
        )
        return CanonicalSearchResult(
            CANONICAL_STATE_SCHEMA_VERSION,
            CANONICAL_SEARCH_VERSION,
            mode,
            por_strategy if por else "none",
            complete,
            tuple(sorted(table.records.values(), key=lambda item: item.state_id)),
            tuple(edges),
            tuple(item.state_id for item in terminal_records),
            tuple(item.envelope.digest for item in terminal_records),
            metrics,
            tuple(evidence.values()),
        )

    @staticmethod
    def _dependency_blocked(action: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> bool:
        footprint = ActionFootprint.from_action(action)
        if not footprint.requires and not footprint.conflicts:
            return False
        applied = {ActionFootprint.from_action(item).action_key for item in history}
        if not footprint.requires.issubset(applied):
            return True
        return bool(footprint.conflicts & applied)

    @staticmethod
    def _summaries(state: LazyState, children: Sequence[LazyState]) -> dict[str, Any]:
        semantic = state.semantic_state
        return {
            "alias_summary": _stable_value(semantic.get("aliases", semantic.get("alias_set", ()))),
            "ownership_summary": _stable_value(semantic.get("ownership", semantic.get("owners", ()))),
            "lifetime_summary": _stable_value(semantic.get("lifetime", semantic.get("lifetimes", ()))),
            "contract_closure": _stable_value(semantic.get("contracts", semantic.get("active_contracts", ()))),
            "applicable_grammar_families": sorted({child.family for child in children}),
            "cross_tu_summary": _stable_value(semantic.get("cross_tu_context", {})),
        }


def _replay_path_states(
    grammar: LazyGrammar,
    root_context: Mapping[str, Any],
    path: Sequence[Mapping[str, Any]],
) -> tuple[LazyState | None, ...]:
    """Rebuild POR path context for an action-native checkpoint.

    Resume is deliberately unavailable for opaque expand-only grammars because reconstructing the
    exact path through heuristic child matching would weaken the identity contract.
    """

    if not path:
        raise ValueError("checkpoint path is empty")
    apply = getattr(grammar, "apply_action", None)
    if not callable(apply):
        raise ValueError("checkpoint resume requires an action-native grammar")
    initial = tuple(grammar.initial_states(root_context))
    first = next(
        (state for state in initial if dict(state.action) == dict(path[0])),
        None,
    )
    if first is None:
        raise ValueError("checkpoint initial action no longer exists")
    path_states: list[LazyState | None] = [None]
    current = first
    for action in path[1:]:
        path_states.append(current)
        next_state = apply(current, action, root_context)
        if next_state is None:
            raise ValueError("checkpoint action path is no longer legal")
        current = next_state
    return tuple(path_states)


@dataclass(frozen=True)
class SequenceSearchResult:
    """Qualification-only exhaustive transformation-sequence baseline."""

    complete: bool
    generated_states: int
    candidate_constructions: int
    expansions: int
    terminal_paths: int
    terminal_canonical_hashes: tuple[str, ...]
    search_wall_ms: float
    proof_calls: int = 0
    compiler_calls: int = 0


def exhaustive_sequence_search(
    grammar: LazyGrammar,
    root_context: Mapping[str, Any],
    *,
    canonicalizer: Canonicalizer | None = None,
    node_budget: int = 1_000_000,
    terminal_evaluator: Callable[[LazyState], Mapping[str, Any]] | None = None,
) -> SequenceSearchResult:
    """Enumerate paths without a transposition table for bounded correctness qualification only."""

    canonicalizer = canonicalizer or Canonicalizer()
    queue = deque(tuple(grammar.initial_states(root_context)))
    generated = len(queue)
    constructed = len(queue)
    expansions = 0
    terminals = 0
    proof_calls = 0
    compiler_calls = 0
    terminal_hashes: set[str] = set()
    complete = True
    started = time.perf_counter()
    while queue:
        if generated > node_budget:
            complete = False
            break
        state = queue.popleft()
        if state.deterministic_status in {"impossible", "dominated"}:
            continue
        if state.terminal:
            terminals += 1
            terminal_hashes.add(canonicalizer.envelope(state).digest)
            if terminal_evaluator is not None:
                evidence = terminal_evaluator(state)
                proof_calls += int(evidence.get("proof_calls", 0))
                compiler_calls += int(evidence.get("compiler_calls", 0))
            continue
        children = tuple(grammar.expand(state, root_context))
        generated += len(children)
        constructed += len(children)
        expansions += 1
        queue.extend(children)
    return SequenceSearchResult(
        complete,
        generated,
        constructed,
        expansions,
        terminals,
        tuple(sorted(terminal_hashes)),
        (time.perf_counter() - started) * 1000.0,
        proof_calls,
        compiler_calls,
    )


def canonical_result_to_lazy(result: CanonicalSearchResult) -> LazySearchResult:
    """Compatibility projection for existing proof, compiler, and trace consumers."""

    edge_by_id = {edge.edge_id: edge for edge in result.edges}
    outgoing: Counter[str | None] = Counter(edge.parent_state_id for edge in result.edges)
    nodes: list[LazyTraceNode] = []
    ordered_records = sorted(result.states, key=lambda item: (item.depth_minimum, item.state_id))
    terminal_ids = set(result.terminal_state_ids)
    for record in ordered_records:
        first_edge = edge_by_id[record.parent_edges[0]] if record.parent_edges else None
        parent_id = first_edge.parent_state_id if first_edge else None
        disposition = (
            "terminal" if record.state_id in terminal_ids else
            "deferred" if record.state.terminal else
            "expanded"
        )
        nodes.append(LazyTraceNode(
            record.state_id,
            parent_id,
            record.depth_minimum,
            record.state.family,
            record.state.stage,
            dict(record.state.action),
            record.envelope.digest,
            record.state.terminal,
            disposition,
            ExpansionDecision.EXPAND.value,
            "canonical semantic-state DAG",
            1.0,
            True,
            None,
            outgoing[record.state_id],
            {},
            dict(record.state.semantic_state),
            {"node_expansions": int(not record.state.terminal)},
        ))
    for edge in result.edges:
        if edge.disposition == "new_state":
            continue
        child = next(record for record in result.states if record.state_id == edge.child_state_id)
        nodes.append(LazyTraceNode(
            edge.edge_id,
            edge.parent_state_id,
            edge.depth,
            child.state.family,
            child.state.stage,
            dict(edge.action),
            child.envelope.digest,
            child.state.terminal,
            "canonical_duplicate",
            ExpansionDecision.PRUNE.value,
            edge.disposition,
            1.0,
            True,
            child.state_id,
            0,
            {},
            dict(child.state.semantic_state),
            {"node_expansions": 0},
        ))
    terminals = tuple(
        replace(record.state, identity=record.envelope.digest)
        for record in result.states if record.state_id in terminal_ids
    )
    return LazySearchResult(
        "lazy-executable-search-v7-canonical-projection",
        result.mode,
        result.complete,
        tuple(nodes),
        terminals,
        sum(not record.state.terminal for record in result.states),
        0,
        0,
        result.metrics.dependency_avoided_transitions,
        (
            result.metrics.exact_transpositions
            + result.metrics.alpha_equivalent_collapses
            + result.metrics.symmetry_collapses
        ),
        (),
        0,
        0,
        result.metrics.maximum_frontier_size,
    )


def compare_terminal_sets(
    baseline: CanonicalSearchResult, candidate: CanonicalSearchResult,
) -> dict[str, Any]:
    expected = set(baseline.terminal_canonical_hashes)
    actual = set(candidate.terminal_canonical_hashes)
    return {
        "status": "PASS" if expected == actual else "FAIL",
        "expected_count": len(expected),
        "actual_count": len(actual),
        "missing": sorted(expected - actual),
        "unexpected": sorted(actual - expected),
        "preservation_ratio": 1.0 if not expected else len(expected & actual) / len(expected),
    }


def reduction_waterfall(result: CanonicalSearchResult) -> dict[str, Any]:
    metrics = result.metrics
    raw = max(1, metrics.raw_generated_states)
    rows = []
    remaining = metrics.raw_generated_states
    for mechanism, count in (
        ("canonical_transposition", metrics.exact_transpositions),
        ("alpha_equivalence", metrics.alpha_equivalent_collapses),
        ("symmetry", metrics.symmetry_collapses),
        ("dependency_schedule", metrics.dependency_avoided_transitions),
        ("partial_order_reduction", metrics.por_avoided_transitions),
        ("dominance", metrics.dominance_collapses),
        ("macro", metrics.macro_collapses),
    ):
        remaining = max(0, remaining - count)
        rows.append({
            "mechanism": mechanism,
            "removed": count,
            "remaining": remaining,
            "remaining_percent_of_raw": 100.0 * remaining / raw,
        })
    return {
        "schema_version": "vladder-canonical-reduction-waterfall-v1",
        "raw_search_work": metrics.raw_generated_states,
        "steps": rows,
        "final_unique_states": metrics.unique_canonical_states,
    }


@dataclass(frozen=True)
class LayeredStateHash:
    """Merkle-style component hashes for bounded incremental invalidation."""

    components: tuple[tuple[str, str], ...]
    full_hash: str

    @classmethod
    def build(cls, semantic_state: Mapping[str, Any]) -> "LayeredStateHash":
        components = tuple(
            (str(key), _digest(_json_bytes(_stable_value(value))))
            for key, value in sorted(semantic_state.items(), key=lambda item: str(item[0]))
        )
        return cls(components, _digest(_json_bytes(components)))

    def update(
        self,
        semantic_state: Mapping[str, Any],
        *,
        changed: Mapping[str, Any] | None = None,
        removed: Iterable[str] = (),
    ) -> "LayeredStateHash":
        hashes = dict(self.components)
        for key in removed:
            hashes.pop(str(key), None)
        for key, value in (changed or {}).items():
            hashes[str(key)] = _digest(_json_bytes(_stable_value(value)))
        result = LayeredStateHash(tuple(sorted(hashes.items())), _digest(_json_bytes(tuple(sorted(hashes.items())))))
        clean = LayeredStateHash.build(semantic_state)
        if result != clean:
            raise ValueError("incremental state hash differs from clean rematerialization")
        return result

    def update_or_rematerialize(
        self,
        semantic_state: Mapping[str, Any],
        *,
        changed: Mapping[str, Any] | None = None,
        removed: Iterable[str] = (),
    ) -> tuple["LayeredStateHash", bool, str | None]:
        """Use a verified incremental update or fail closed to a clean state hash.

        The boolean is true only when disagreement forced clean rematerialization.  Callers must
        retain the incident string as reduction evidence; a corrupt incremental value is never
        returned.
        """

        try:
            return self.update(semantic_state, changed=changed, removed=removed), False, None
        except ValueError as exc:
            return self.build(semantic_state), True, str(exc)


def typed_wl_labels(graph: Mapping[str, Any], *, rounds: int | None = None) -> dict[str, str]:
    """Typed Weisfeiler-Lehman refinement for canonical-labeling experiments.

    It is a partition refinement, not by itself an authority for merging states.
    """

    nodes = {str(item.get("id")): dict(item) for item in graph.get("nodes", ()) if isinstance(item, Mapping)}
    incoming: dict[str, list[tuple[str, str]]] = defaultdict(list)
    outgoing: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in graph.get("edges", ()):
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("source", edge.get("from", "")))
        target = str(edge.get("target", edge.get("to", "")))
        kind = str(edge.get("kind", edge.get("type", "edge")))
        outgoing[source].append((kind, target))
        incoming[target].append((kind, source))
    labels = {
        node_id: _digest(_json_bytes({
            key: _stable_value(value)
            for key, value in node.items()
            if key != "id"
        }))
        for node_id, node in nodes.items()
    }
    limit = rounds if rounds is not None else max(1, len(nodes))
    for _ in range(limit):
        refined = {
            node_id: _digest(_json_bytes({
                "self": labels[node_id],
                "in": sorted((kind, labels.get(peer, "external")) for kind, peer in incoming[node_id]),
                "out": sorted((kind, labels.get(peer, "external")) for kind, peer in outgoing[node_id]),
            }))
            for node_id in nodes
        }
        if refined == labels:
            break
        labels = refined
    return labels


@dataclass(frozen=True)
class GrammarDependencyGraph:
    action_keys: tuple[str, ...]
    requires_edges: tuple[tuple[str, str], ...]
    conflict_edges: tuple[tuple[str, str], ...]

    @classmethod
    def build(cls, actions: Iterable[Mapping[str, Any]]) -> "GrammarDependencyGraph":
        footprints = tuple(ActionFootprint.from_action(action) for action in actions)
        keys = {item.action_key for item in footprints}
        requires = sorted(
            (required, item.action_key)
            for item in footprints
            for required in item.requires
            if required in keys
        )
        conflicts = sorted({
            tuple(sorted((item.action_key, conflict)))
            for item in footprints
            for conflict in item.conflicts
            if conflict in keys
        })
        return cls(tuple(sorted(keys)), tuple(requires), tuple(conflicts))

    def topological_order(self) -> tuple[str, ...] | None:
        incoming: dict[str, set[str]] = {key: set() for key in self.action_keys}
        outgoing: dict[str, set[str]] = {key: set() for key in self.action_keys}
        for source, target in self.requires_edges:
            outgoing[source].add(target)
            incoming[target].add(source)
        ready = deque(sorted(key for key, dependencies in incoming.items() if not dependencies))
        order: list[str] = []
        while ready:
            current = ready.popleft()
            order.append(current)
            for target in sorted(outgoing[current]):
                incoming[target].discard(current)
                if not incoming[target]:
                    ready.append(target)
        return tuple(order) if len(order) == len(self.action_keys) else None


@dataclass(frozen=True)
class OptimizationSignature:
    """Coarse future-opportunity key that proposes checks but never merges states."""

    digest: str
    semantic_observables: Any
    enabled_grammar_families: tuple[str, ...]
    owner_representation_relations: Any
    lifetime_constraints: Any
    authority_constraints: Any
    contracts: Any
    alias_constraints: Any
    hardware_constraints: Any

    @classmethod
    def from_record(cls, record: CanonicalStateRecord) -> "OptimizationSignature":
        semantic = record.state.semantic_state
        payload = {
            "semantic_observables": _stable_value(semantic.get("observables", semantic.get("observable", {}))),
            "enabled_grammar_families": tuple(record.summaries.get("applicable_grammar_families", ())),
            "owner_representation_relations": _stable_value({
                "owners": semantic.get("owners", semantic.get("ownership", ())),
                "representations": semantic.get("representations", semantic.get("representation_state", ())),
            }),
            "lifetime_constraints": _stable_value(semantic.get("lifetimes", semantic.get("lifetime_state", ()))),
            "authority_constraints": _stable_value(semantic.get("authority", semantic.get("authority_state", ()))),
            "contracts": _stable_value(semantic.get("contracts", semantic.get("active_contracts", ()))),
            "alias_constraints": _stable_value(semantic.get("aliases", semantic.get("alias_set", ()))),
            "hardware_constraints": _stable_value(semantic.get("hardware_constraints", ())),
        }
        return cls(_digest(_json_bytes(payload)), **payload)


def optimization_equivalence_proposals(
    records: Iterable[CanonicalStateRecord],
) -> tuple[tuple[str, str, str], ...]:
    """Return coarse-signature pairs for an exact checker; this function has no merge authority."""

    groups: dict[str, list[str]] = defaultdict(list)
    for record in records:
        groups[OptimizationSignature.from_record(record).digest].append(record.state_id)
    return tuple(
        (left, right, digest)
        for digest, state_ids in sorted(groups.items())
        for left, right in itertools.combinations(sorted(state_ids), 2)
    )
