from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


LANGUAGE_ADAPTER_PROTOCOL_VERSION = "language-adapter-v2"
SEMANTIC_FLOW_SCHEMA_VERSION = "semantic-flow-v2"

OBLIGATION_CATEGORIES = frozenset({
    "aliasing", "bounds", "cleanup", "concurrency", "dispatch", "exception",
    "external-effect", "lifetime", "memory", "numeric", "ownership", "placement",
    "representation", "safety", "shape", "state", "target", "validation",
})
EFFECT_KINDS = frozenset({
    "MemoryRead", "MemoryWrite", "Allocate", "Deallocate", "Cleanup",
    "ExceptionalExit", "Synchronize", "Atomic", "Dispatch", "ExternalCall",
    "Publish", "Invalidate", "Transfer", "Nondeterminism",
})
PROTOCOL_KINDS = frozenset({
    "Ownership", "Lifetime", "Cleanup", "Publication", "Invalidation", "Dispatch",
    "Exception", "Concurrency",
})
CLAIM_STATUSES = frozenset({"proved", "required", "assumed", "excluded", "unverified"})

# These concepts describe information realization, not source-language syntax. Adapters attach
# language obligations as provenance instead of minting parallel Rust/Go/C++ graph vocabularies.
SEMANTIC_NODE_KINDS = frozenset({
    "Input",
    "Output",
    "Constant",
    "Borrow",
    "Load",
    "Store",
    "Address",
    "Compare",
    "Select",
    "Map",
    "Reduce",
    "StateRead",
    "StateWrite",
    "Control",
    "Call",
    "Panic",
    "Materialize",
    "Transfer",
    "LifetimeBoundary",
    # Physical realization vocabulary shared by every language adapter.
    "Loop",
    "Guard",
    "Broadcast",
    "LaneMap",
    "Pack",
    "Unpack",
    "Bitwise",
    "Mask",
    "MaskExtract",
    "PopulationCount",
    "HorizontalReduce",
    "TableLookup",
    "Tail",
    "Dispatch",
    "Fuse",
    "View",
    "ComplexityBound",
    # Bounded variable-output and stateful dataflow vocabulary.
    "CapacityGuard",
    "PrefixScan",
    "Compact",
    "Scatter",
    "Extent",
    "Codec",
    "EndianConvert",
    "Project",
    "Histogram",
    "Commit",
    "Rollback",
    "Tile",
    "Quantize",
    "QualityMetric",
    # Bounded ABI and CFG closure vocabulary. These describe compiled information
    # channels rather than C/C++ syntax.
    "AggregatePack",
    "AggregateUnpack",
    "ExitMerge",
    "HelperSummary",
    "OwnershipGuard",
    "Append",
})


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class LanguageCapability:
    ready: bool
    actual: bool
    detail: str
    artifact: str | None = None


@dataclass(frozen=True)
class SemanticObligation:
    id: str
    category: str
    statement: str
    scope: str
    proof_method: str
    language_binding: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.id or self.category not in OBLIGATION_CATEGORIES:
            raise ValueError(f"invalid semantic obligation: {self.id or '<missing>'}/{self.category}")
        if not self.statement or not self.scope or not self.proof_method:
            raise ValueError(f"semantic obligation {self.id} is incomplete")


@dataclass(frozen=True)
class SemanticEffect:
    id: str
    kind: str
    phase: str
    resource: str
    observability: str
    ordering: str
    node_ids: tuple[str, ...] = ()
    obligation_ids: tuple[str, ...] = ()
    attributes: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.id or self.kind not in EFFECT_KINDS:
            raise ValueError(f"invalid semantic effect: {self.id or '<missing>'}/{self.kind}")
        if not self.phase or not self.observability or not self.ordering:
            raise ValueError(f"semantic effect {self.id} is incomplete")
        if self.attributes is None:
            object.__setattr__(self, "attributes", {})


@dataclass(frozen=True)
class ProtocolTransition:
    id: str
    protocol: str
    source_state: str
    event: str
    target_state: str
    guard: str
    obligation_ids: tuple[str, ...] = ()
    language_binding: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.id or self.protocol not in PROTOCOL_KINDS:
            raise ValueError(f"invalid protocol transition: {self.id or '<missing>'}/{self.protocol}")
        if not self.source_state or not self.event or not self.target_state or not self.guard:
            raise ValueError(f"protocol transition {self.id} is incomplete")
        if self.language_binding is None:
            object.__setattr__(self, "language_binding", {})


@dataclass(frozen=True)
class SemanticClaim:
    id: str
    status: str
    statement: str
    scope: str

    def __post_init__(self) -> None:
        if not self.id or self.status not in CLAIM_STATUSES or not self.statement or not self.scope:
            raise ValueError(f"invalid semantic claim: {self.id or '<missing>'}")


def obligation(
    identifier: str,
    category: str,
    statement: str,
    *,
    scope: str = "region",
    proof_method: str = "required",
    language: str | None = None,
    native_construct: str | None = None,
    facts: dict[str, Any] | None = None,
) -> SemanticObligation:
    binding = dict(facts or {})
    if language is not None:
        binding["language"] = language
    if native_construct is not None:
        binding["native_construct"] = native_construct
    return SemanticObligation(identifier, category, statement, scope, proof_method, binding)


def _legacy_obligation(statement: str) -> SemanticObligation:
    lowered = statement.lower()
    category = "validation"
    for token, mapped in (
        ("bound", "bounds"), ("overflow", "numeric"), ("panic", "exception"),
        ("borrow", "ownership"), ("mutation", "state"), ("alias", "aliasing"),
        ("target", "target"), ("observer", "representation"), ("lifetime", "lifetime"),
    ):
        if token in lowered:
            category = mapped
            break
    identifier = "legacy." + hashlib.sha256(statement.encode()).hexdigest()[:16]
    return obligation(identifier, category, statement, proof_method="compatibility-normalized")


@dataclass(frozen=True)
class SemanticFlowNode:
    id: str
    kind: str
    operation: str
    inputs: tuple[str, ...]
    output_type: str | None
    attributes: dict[str, Any]
    source_provenance: dict[str, Any]
    semantic_obligations: tuple[SemanticObligation, ...]

    def __post_init__(self) -> None:
        if self.kind not in SEMANTIC_NODE_KINDS:
            raise ValueError(f"unknown semantic flow node kind: {self.kind}")
        normalized = tuple(
            _legacy_obligation(item) if isinstance(item, str) else item
            for item in self.semantic_obligations
        )
        if any(not isinstance(item, SemanticObligation) for item in normalized):
            raise TypeError(f"node {self.id} contains a non-obligation semantic record")
        object.__setattr__(self, "semantic_obligations", normalized)


@dataclass(frozen=True)
class SemanticFlowEdge:
    id: str
    source: str
    destination: str
    value_type: str
    ownership: str
    alias_set: str
    lifetime: str
    ordering: str
    logical_shape: tuple[int | str, ...] = ()
    physical_shape: tuple[int | str, ...] = ()
    lane_width_bits: int | None = None
    vector_width_bits: int | None = None
    realization: str = "semantic"
    memory_region: str = "unspecified"
    validity_scope: str = "region"


@dataclass(frozen=True)
class SemanticFlowGraph:
    name: str
    source_language: str
    compiler_identity: str
    semantic_ir: str
    function_identity: str
    nodes: tuple[SemanticFlowNode, ...]
    edges: tuple[SemanticFlowEdge, ...]
    contracts: dict[str, Any]
    excluded_claims: tuple[str, ...]
    obligations: tuple[SemanticObligation, ...] = ()
    effects: tuple[SemanticEffect, ...] = ()
    protocols: tuple[ProtocolTransition, ...] = ()
    claims: tuple[SemanticClaim, ...] = ()
    graph_hash: str = ""

    def __post_init__(self) -> None:
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("semantic flow node identifiers must be unique")
        for edge in self.edges:
            if edge.source not in node_ids or edge.destination not in node_ids:
                raise ValueError(f"semantic flow edge references an unknown node: {edge.id}")
        node_obligations = tuple(item for node in self.nodes for item in node.semantic_obligations)
        all_obligations = (*self.obligations, *node_obligations)
        obligation_by_id: dict[str, SemanticObligation] = {}
        for item in all_obligations:
            existing = obligation_by_id.get(item.id)
            if existing is not None and existing != item:
                raise ValueError(f"semantic obligation identifier has conflicting definitions: {item.id}")
            obligation_by_id[item.id] = item
        effect_ids: set[str] = set()
        for effect in self.effects:
            if effect.id in effect_ids:
                raise ValueError(f"duplicate semantic effect identifier: {effect.id}")
            effect_ids.add(effect.id)
            missing_nodes = set(effect.node_ids) - node_ids
            missing_obligations = set(effect.obligation_ids) - set(obligation_by_id)
            if missing_nodes or missing_obligations:
                raise ValueError(f"semantic effect {effect.id} has unresolved references")
        protocol_ids: set[str] = set()
        for transition in self.protocols:
            if transition.id in protocol_ids:
                raise ValueError(f"duplicate protocol transition identifier: {transition.id}")
            protocol_ids.add(transition.id)
            if set(transition.obligation_ids) - set(obligation_by_id):
                raise ValueError(f"protocol transition {transition.id} has unresolved obligations")
        if not self.claims and self.excluded_claims:
            object.__setattr__(self, "claims", tuple(
                SemanticClaim(f"excluded.{index}", "excluded", statement, "graph")
                for index, statement in enumerate(self.excluded_claims)
            ))
        expected = canonical_hash(self._hash_payload())
        if self.graph_hash and self.graph_hash != expected:
            raise ValueError("semantic flow graph hash does not match its payload")
        if not self.graph_hash:
            object.__setattr__(self, "graph_hash", expected)

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SEMANTIC_FLOW_SCHEMA_VERSION,
            "name": self.name,
            "source_language": self.source_language,
            "compiler_identity": self.compiler_identity,
            "semantic_ir": self.semantic_ir,
            "function_identity": self.function_identity,
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
            "contracts": self.contracts,
            "excluded_claims": self.excluded_claims,
            "obligations": [asdict(item) for item in self.obligations],
            "effects": [asdict(item) for item in self.effects],
            "protocols": [asdict(item) for item in self.protocols],
            "claims": [asdict(item) for item in self.claims],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "graph_hash": self.graph_hash}


@dataclass(frozen=True)
class LanguageRegionEvidence:
    adapter_protocol: str
    adapter_name: str
    source_language: str
    support_version: str
    function: str
    status: str
    capabilities: dict[str, LanguageCapability]
    semantic_graph: SemanticFlowGraph | None
    build_identity: dict[str, Any]
    blockers: tuple[dict[str, Any], ...]
    artifacts: dict[str, str]
    claim_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_protocol": self.adapter_protocol,
            "adapter_name": self.adapter_name,
            "source_language": self.source_language,
            "support_version": self.support_version,
            "function": self.function,
            "status": self.status,
            "capabilities": {key: asdict(value) for key, value in sorted(self.capabilities.items())},
            "semantic_graph": self.semantic_graph.to_dict() if self.semantic_graph else None,
            "build_identity": self.build_identity,
            "blockers": list(self.blockers),
            "artifacts": self.artifacts,
            "claim_boundary": self.claim_boundary,
        }


@runtime_checkable
class LanguageAdapter(Protocol):
    name: str
    source_language: str
    support_version: str

    def inspect(self, request: Any) -> LanguageRegionEvidence:
        """Capture one concrete semantic region without changing production source."""

    def synthesize(self, request: Any) -> dict[str, Any]:
        """Emit native-language candidates and proof obligations without applying them."""

    def optimize(self, request: Any) -> dict[str, Any]:
        """Verify and physically rank candidates under the request contract."""


class LanguageAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, LanguageAdapter] = {}

    def register(self, adapter: LanguageAdapter) -> None:
        if not isinstance(adapter, LanguageAdapter):
            raise TypeError("adapter does not implement the LanguageAdapter protocol")
        if adapter.source_language in self._adapters:
            raise ValueError(f"language adapter already registered: {adapter.source_language}")
        self._adapters[adapter.source_language] = adapter

    def get(self, language: str) -> LanguageAdapter:
        try:
            return self._adapters[language]
        except KeyError as error:
            raise KeyError(f"no language adapter registered for {language}") from error

    def support_matrix(self) -> dict[str, Any]:
        return {
            "schema_version": LANGUAGE_ADAPTER_PROTOCOL_VERSION,
            "adapters": [
                {
                    "name": adapter.name,
                    "source_language": adapter.source_language,
                    "support_version": adapter.support_version,
                }
                for adapter in sorted(self._adapters.values(), key=lambda item: item.source_language)
            ],
        }
