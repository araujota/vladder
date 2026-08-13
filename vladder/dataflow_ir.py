from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .language_adapter import (
    ProtocolTransition,
    SemanticClaim,
    SemanticEffect,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    obligation,
)


DATAFLOW_GRAPH_SCHEMA = "vladder-bounded-dataflow-graph-v1"
DATAFLOW_FAMILIES = frozenset({
    "predicate-stable-compaction",
    "fixed-width-codec",
    "stateful-delta-transducer",
    "aos-fused-multi-reduction",
    "quantized-block-4x4",
})
OUTPUT_MODES = frozenset({"index-only", "value-only", "index-value"})
CAPACITY_POLICIES = frozenset({
    "fail-unchanged",
    "fail-input-extent-unchanged",
    "truncate",
})
QUALITY_CLASSES = frozenset({"exact-encoded", "exact-decoded", "bounded-quality"})


@dataclass(frozen=True)
class BoundedDataflowContract:
    family: str
    # None denotes a runtime-sized borrowed range. Proofs then use structural loop/block
    # induction rather than claiming a source-level maximum that is not present.
    max_elements: int | None = 256
    element_bits: int = 64
    output_mode: str = "index-value"
    stable: bool = True
    capacity_policy: str = "fail-unchanged"
    field_widths: tuple[int, ...] = (16, 16, 32)
    byte_order: str = "little"
    record_trivially_copyable: bool = True
    no_growth: bool = True
    noexcept: bool = True
    aliasing: str = "disjoint"
    quality_class: str = "exact-encoded"
    quality_limit: int = 0
    target_isa: tuple[str, ...] = ("scalar", "avx2", "avx512f")

    def __post_init__(self) -> None:
        if self.family not in DATAFLOW_FAMILIES:
            raise ValueError(f"unsupported bounded dataflow family: {self.family}")
        if self.max_elements is not None and (self.max_elements <= 0 or self.max_elements > 4096):
            raise ValueError("max_elements must be in [1, 4096]")
        if self.element_bits not in {8, 16, 32, 64}:
            raise ValueError("element_bits must be 8, 16, 32, or 64")
        if self.output_mode not in OUTPUT_MODES:
            raise ValueError(f"unsupported output mode: {self.output_mode}")
        if self.capacity_policy not in CAPACITY_POLICIES:
            raise ValueError(f"unsupported capacity policy: {self.capacity_policy}")
        if self.byte_order not in {"little", "big"}:
            raise ValueError("byte_order must be little or big")
        if not self.field_widths or sum(self.field_widths) > 64 or any(width <= 0 for width in self.field_widths):
            raise ValueError("codec field widths must be positive and fit in 64 bits")
        if self.family == "fixed-width-codec" and (
            len(self.field_widths) != 3
            or self.field_widths[0] > 16
            or self.field_widths[1] > 16
            or self.field_widths[2] > 32
        ):
            raise ValueError("v1 codec fields must fit the u16/u16/u32 executable boundary")
        if self.quality_class not in QUALITY_CLASSES or self.quality_limit < 0:
            raise ValueError("invalid quality contract")
        if self.family == "predicate-stable-compaction" and not self.stable:
            raise ValueError("v1 promotes stable compaction only; unstable order needs a separate observable contract")
        if self.family in {"predicate-stable-compaction", "stateful-delta-transducer"}:
            if not self.record_trivially_copyable or not self.no_growth or not self.noexcept:
                raise ValueError("bounded output closure requires trivial records, no growth, and noexcept execution")
        if self.family == "stateful-delta-transducer" and self.capacity_policy == "truncate":
            raise ValueError("stateful delta truncation requires a separate partial-commit contract")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BoundedDataflowContract":
        values = dict(payload)
        values.pop("extent_semantics", None)
        if "field_widths" in values:
            values["field_widths"] = tuple(int(item) for item in values["field_widths"])
        if "target_isa" in values:
            values["target_isa"] = tuple(str(item) for item in values["target_isa"])
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "field_widths": list(self.field_widths),
            "target_isa": list(self.target_isa),
            "extent_semantics": "runtime-sized" if self.max_elements is None else "declared-maximum",
        }


@dataclass(frozen=True)
class BoundedDataflowGraph:
    family: str
    realization: str
    semantic_graph: SemanticFlowGraph
    graph_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DATAFLOW_GRAPH_SCHEMA,
            "family": self.family,
            "realization": self.realization,
            "semantic_graph": self.semantic_graph.to_dict(),
            "graph_hash": self.graph_hash,
        }


def _obligation(identifier: str, category: str, statement: str, construct: str):
    return obligation(
        f"dataflow.{identifier}",
        category,
        statement,
        scope="bounded-dataflow-region",
        proof_method="bounded-dataflow-v1-proof-registry",
        native_construct=construct,
    )


def _node(
    identifier: str,
    kind: str,
    operation: str,
    inputs: tuple[str, ...],
    output_type: str | None,
    realization: str,
    obligations: tuple[tuple[str, str, str], ...] = (),
    **attributes: Any,
) -> SemanticFlowNode:
    return SemanticFlowNode(
        identifier,
        kind,
        operation,
        inputs,
        output_type,
        {"realization": realization, **attributes},
        {"adapter": "bounded-dataflow-v1", "semantic_source": operation},
        tuple(_obligation(name, category, statement, operation) for name, category, statement in obligations),
    )


def _edge(source: str, destination: str, ordinal: int, value_type: str, realization: str) -> SemanticFlowEdge:
    memory = "caller-output" if destination in {"compact", "scatter", "codec", "state.write", "output"} else "register"
    return SemanticFlowEdge(
        f"{source}->{destination}:{ordinal}",
        source,
        destination,
        value_type,
        "borrowed" if source.startswith("input") else "ephemeral",
        "bounded-dataflow",
        "region",
        "program-order",
        ("n",),
        (),
        realization=realization,
        memory_region=memory,
        validity_scope="bounded-call",
    )


def _common_inputs(contract: BoundedDataflowContract, realization: str) -> list[SemanticFlowNode]:
    return [
        _node("input.current", "Input", "borrowed-contiguous-current", (), f"span<u{contract.element_bits}>", realization),
        _node("input.baseline", "Input", "borrowed-contiguous-baseline", (), f"span<u{contract.element_bits}>", realization),
        _node(
            "input.output",
            "Input",
            "caller-owned-bounded-output",
            (),
            "bounded-output-view",
            realization,
            (
                ("output.capacity", "bounds", "output capacity covers every committed element",),
                ("output.no-growth", "ownership", "the generated region performs no allocation or ownership transfer",),
                ("output.trivial-lifetime", "lifetime", "output elements are trivially copyable and destructible",),
            ),
            output_mode=contract.output_mode,
        ),
    ]


def _compaction_nodes(contract: BoundedDataflowContract, realization: str) -> list[SemanticFlowNode]:
    nodes = _common_inputs(contract, realization)
    nodes.extend([
        _node("compare", "Compare", "current-not-equal-baseline", ("input.current", "input.baseline"), "mask<n>", realization),
        _node("mask", "Mask", "predicate-mask", ("compare",), "mask<n>", realization, (("mask.population", "representation", "mask bits equal selected predicates",),)),
        _node("extent", "PopulationCount", "exact-output-extent", ("mask",), "usize", realization),
        _node(
            "capacity",
            "CapacityGuard",
            contract.capacity_policy,
            ("extent", "input.output"),
            "bool",
            realization,
            (("capacity.atomicity", "bounds", "capacity failure follows the declared output atomicity policy",),),
            policy=contract.capacity_policy,
        ),
        _node("scan", "PrefixScan", "exclusive-mask-prefix", ("mask", "capacity"), "offset<n>", realization, (("scan.stability", "representation", "exclusive prefix offsets preserve input order",),)),
        _node("compact", "Compact", contract.output_mode, ("input.current", "mask", "scan", "input.output"), "bounded-output", realization, (("compact.sequence", "validation", "selected indices and values equal the stable reference sequence",),)),
        _node("output", "Output", "extent-or-capacity-failure", ("compact", "extent", "capacity"), "extent-status", realization),
    ])
    return nodes


def _codec_nodes(contract: BoundedDataflowContract, realization: str) -> list[SemanticFlowNode]:
    nodes = [
        _node("input.fields", "Input", "typed-fixed-width-fields", (), "field-tuple", realization),
        _node("guard", "Guard", "field-range-check", ("input.fields",), "bool", realization, (("codec.field-bounds", "bounds", "every field value fits its declared width",),)),
        _node("pack", "Pack", "fixed-bit-placement", ("input.fields", "guard"), "u64", realization, (("codec.bit-placement", "representation", "packed fields are disjoint and invertible",),), field_widths=list(contract.field_widths)),
        _node("endian", "EndianConvert", f"native-to-{contract.byte_order}", ("pack",), "bytes[8]", realization, (("codec.endian", "representation", "byte-order conversion is bijective",),)),
        _node("codec", "Codec", "fixed-envelope-store", ("endian",), "bytes[8]", realization),
        _node("output", "Output", "packed-envelope", ("codec",), "u64", realization),
    ]
    return nodes


def _state_nodes(contract: BoundedDataflowContract, realization: str) -> list[SemanticFlowNode]:
    nodes = _common_inputs(contract, realization)
    nodes.extend([
        _node("state.read", "StateRead", "acknowledged-baseline", ("input.baseline",), "state<n>", realization),
        _node("compare", "Compare", "current-not-equal-baseline", ("input.current", "state.read"), "mask<n>", realization),
        _node("mask", "Mask", "delta-mask", ("compare",), "mask<n>", realization),
        _node("extent", "PopulationCount", "delta-extent", ("mask",), "usize", realization),
        _node(
            "capacity",
            "CapacityGuard",
            contract.capacity_policy,
            ("extent", "input.output"),
            "bool",
            realization,
            (("capacity.atomicity", "bounds", "capacity failure preserves state and output"),),
        ),
        _node("scan", "PrefixScan", "stable-delta-offsets", ("mask", "capacity"), "offset<n>", realization),
        _node("compact", "Compact", "index-value-delta", ("input.current", "mask", "scan", "input.output"), "delta", realization),
        _node("state.write", "StateWrite", "candidate-next-state", ("state.read", "input.current", "mask"), "state<n>", realization),
        _node("commit", "Commit", "publish-output-and-state", ("capacity", "compact", "state.write"), "committed-state", realization, (("state.commit", "state", "output and next state publish atomically on success",),)),
        _node("rollback", "Rollback", "preserve-baseline-on-failure", ("capacity", "state.read"), "state<n>", realization, (("state.rollback", "state", "capacity failure preserves state and output extent",),)),
        _node("output", "Output", "delta-transition-result", ("commit", "rollback", "extent"), "transition-result", realization),
    ])
    return nodes


def _aos_nodes(contract: BoundedDataflowContract, realization: str) -> list[SemanticFlowNode]:
    return [
        _node("input.records", "Input", "borrowed-trivial-records", (), "span<record>", realization, (("aos.trivial", "lifetime", "records are trivially copyable and remain alive for the traversal",),)),
        _node("project", "Project", "project-kind-flags-bytes", ("input.records",), "field-streams", realization, (("aos.projection", "shape", "projected fields retain record identity",),)),
        _node("compare", "Compare", "compound-record-predicate", ("project",), "mask<n>", realization),
        _node("reduce.count", "Reduce", "selected-count", ("compare",), "u64", realization),
        _node("reduce.bytes", "Reduce", "selected-byte-sum", ("project", "compare"), "u64", realization),
        _node("reduce.flags", "Reduce", "selected-flag-count", ("project", "compare"), "u64", realization),
        _node("output", "Output", "multi-reduction-result", ("reduce.count", "reduce.bytes", "reduce.flags"), "stats", realization, (("aos.multi-reduction", "numeric", "fused reductions equal independent projections",),)),
    ]


def _block_nodes(contract: BoundedDataflowContract, realization: str) -> list[SemanticFlowNode]:
    quality_statement = {
        "exact-encoded": "candidate encoded bytes equal the deterministic reference",
        "exact-decoded": "candidate decoded values equal the deterministic reference",
        "bounded-quality": "candidate error remains within the declared metric and deterministic tie-breaking",
    }[contract.quality_class]
    return [
        _node("input.tile", "Input", "rgba8-tile-4x4", (), "tile<rgba8,4,4>", realization),
        _node("tile", "Tile", "fixed-4x4-coverage", ("input.tile",), "rgba8x16", realization, (("block.coverage", "shape", "all sixteen pixels are consumed exactly once",),)),
        _node("endpoints", "Reduce", "rgb-min-max", ("tile",), "endpoint-pair", realization, (("block.endpoints", "numeric", "channel endpoints equal the reference extrema",),)),
        _node("quantize", "Quantize", "rgb565-endpoints", ("endpoints",), "u16x2", realization),
        _node("palette", "Map", "deterministic-four-entry-palette", ("quantize",), "rgba8x4", realization),
        _node("indices", "Map", "nearest-palette-index", ("tile", "palette"), "u2x16", realization, (("block.tie-break", "numeric", "equal distances select the lowest palette index",),)),
        _node("pack", "Pack", "pack-2bit-indices", ("indices",), "u32", realization, (("block.index-pack", "representation", "all sixteen two-bit indices occupy disjoint positions",),)),
        _node("quality", "QualityMetric", contract.quality_class, ("tile", "quantize", "pack"), "proof-class", realization, (("block.quality", "validation", quality_statement,),), limit=contract.quality_limit),
        _node("output", "Output", "packed-block-envelope", ("quantize", "pack", "quality"), "u64", realization),
    ]


def build_bounded_dataflow_graph(
    contract: BoundedDataflowContract,
    realization: str,
    *,
    source_language: str = "language-neutral",
    function_identity: str = "bounded_dataflow",
    compiler_identity: str = "unlowered",
) -> BoundedDataflowGraph:
    builders = {
        "predicate-stable-compaction": _compaction_nodes,
        "fixed-width-codec": _codec_nodes,
        "stateful-delta-transducer": _state_nodes,
        "aos-fused-multi-reduction": _aos_nodes,
        "quantized-block-4x4": _block_nodes,
    }
    nodes = builders[contract.family](contract, realization)
    edges = [
        _edge(dependency, node.id, ordinal, node.output_type or "control", realization)
        for node in nodes for ordinal, dependency in enumerate(node.inputs)
    ]
    effects: list[SemanticEffect] = []
    protocols: list[ProtocolTransition] = []
    if contract.family in {"predicate-stable-compaction", "stateful-delta-transducer"}:
        effects.append(SemanticEffect(
            "dataflow.output.write", "MemoryWrite", "commit", "caller-owned-output",
            "exact-selected-sequence", "after-capacity-guard", ("compact",),
            ("dataflow.capacity.atomicity",), {"maximum_elements": contract.max_elements},
        ))
    if contract.family == "stateful-delta-transducer":
        effects.append(SemanticEffect(
            "dataflow.state.publish", "Publish", "commit", "candidate-state",
            "atomic-transition", "with-output-publication", ("commit",),
            ("dataflow.state.commit",), {},
        ))
        protocols.extend([
            ProtocolTransition("delta.commit", "Publication", "candidate", "capacity-pass", "published", "extent <= capacity", ("dataflow.state.commit",)),
            ProtocolTransition("delta.rollback", "Publication", "candidate", "capacity-fail", "baseline", "extent > capacity", ("dataflow.state.rollback",)),
        ])
    claims = (
        SemanticClaim("dataflow.contract", "required", "candidate preserves every declared output and failure observable", "bounded-dataflow-region"),
    )
    graph = SemanticFlowGraph(
        f"{contract.family}:{realization}",
        source_language,
        compiler_identity,
        "bounded-dataflow-v1",
        function_identity,
        tuple(nodes),
        tuple(edges),
        contract.to_dict(),
        (
            "owning allocator protocol",
            "throwing element construction",
            "concurrent publication outside an explicit protocol adapter",
            "whole-wrapper equivalence",
        ),
        effects=tuple(effects),
        protocols=tuple(protocols),
        claims=claims,
    )
    payload = {
        "schema_version": DATAFLOW_GRAPH_SCHEMA,
        "family": contract.family,
        "realization": realization,
        "semantic_graph_hash": graph.graph_hash,
    }
    return BoundedDataflowGraph(contract.family, realization, graph, canonical_hash(payload))
