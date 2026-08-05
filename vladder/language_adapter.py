from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


LANGUAGE_ADAPTER_PROTOCOL_VERSION = "language-adapter-v1"
SEMANTIC_FLOW_SCHEMA_VERSION = "semantic-flow-v1"

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
class SemanticFlowNode:
    id: str
    kind: str
    operation: str
    inputs: tuple[str, ...]
    output_type: str | None
    attributes: dict[str, Any]
    source_provenance: dict[str, Any]
    semantic_obligations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in SEMANTIC_NODE_KINDS:
            raise ValueError(f"unknown semantic flow node kind: {self.kind}")


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
    graph_hash: str = ""

    def __post_init__(self) -> None:
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("semantic flow node identifiers must be unique")
        for edge in self.edges:
            if edge.source not in node_ids or edge.destination not in node_ids:
                raise ValueError(f"semantic flow edge references an unknown node: {edge.id}")
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
