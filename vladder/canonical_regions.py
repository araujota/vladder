from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

from .language_adapter import (
    SemanticEffect,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    obligation,
)


CANONICAL_REGION_VERSION = "canonical-bounded-regions-v1"
CANONICAL_FAMILIES = frozenset({
    "ordered_reduction",
    "pointwise_map",
    "guarded_pointwise_map",
    "stencil",
    "scan",
    "recurrence",
    "indirect_memory",
})


@dataclass(frozen=True)
class CanonicalBoundedRegion:
    family: str
    canonical: str
    operation: str
    element_type: str
    result_type: str
    input_roles: tuple[str, ...]
    output_roles: tuple[str, ...]
    loop_form: str
    exactness: str
    carried_state: str | None = None
    neighbor_offsets: tuple[int, ...] = ()
    indirect_stride: int | None = None
    source_traits: tuple[str, ...] = ()
    semantic_parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.family not in CANONICAL_FAMILIES:
            raise ValueError(f"unsupported canonical family: {self.family}")

    @property
    def executable_grammar(self) -> str:
        return "deep-v2-exact-reduction" if self.operation == "count_equal_u8" else "ordered-loop-v1"

    @property
    def region_hash(self) -> str:
        return canonical_hash(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "region_hash": self.region_hash, "executable_grammar": self.executable_grammar}


class CanonicalRegionError(ValueError):
    def __init__(self, kind: str, reason: str, required_adapter: str):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason
        self.required_adapter = required_adapter

    def to_blocker(self) -> dict[str, str]:
        return {"kind": self.kind, "reason": self.reason, "required_adapter": self.required_adapter}


def classify_canonical_region(language: str, function_source: str, signature: str) -> CanonicalBoundedRegion:
    """Recover language-neutral bounded dataflow from one selected native function.

    This is deliberately a bounded recognizer. Compiler IR corroboration is a separate mandatory
    step so source spelling is never the sole semantic authority.
    """
    if language not in {"rust", "zig", "julia"}:
        raise ValueError(f"unsupported canonical source language: {language}")
    compact = _compact(function_source)
    names = _sequence_names(language, signature, function_source)

    if _is_count_equal(language, compact, signature):
        return CanonicalBoundedRegion(
            "ordered_reduction", "count_equal", "count_equal_u8", "u8", "machine-word",
            ("source", "needle"), ("count",), _loop_form(language, function_source, allow_fold=True),
            "E1", carried_state="count", source_traits=("bounded", "allocation-free", "ordered"),
        )

    if names is None:
        raise CanonicalRegionError(
            "type-boundary",
            "the selected function is not a concrete borrowed f32 source/destination region",
            "provide one mutable contiguous output and one immutable contiguous input specialization",
        )
    dst, src = names
    loop_count = _loop_count(language, function_source)
    if loop_count != 1:
        raise CanonicalRegionError(
            "loop-shape",
            f"canonical bounded extraction requires one loop, found {loop_count}",
            "isolate one loop region or use an operator/pipeline graph",
        )
    index = _loop_index(language, function_source)
    if index is None:
        raise CanonicalRegionError(
            "loop-shape", "the loop induction variable could not be recovered",
            "use a bounded range/eachindex traversal or provide a loop-domain adapter",
        )
    dst_i = rf"{re.escape(dst)}\[{re.escape(index)}\]"
    src_i = rf"{re.escape(src)}\[{re.escape(index)}\]"

    stride = _indirect_stride(compact, index)
    if stride is not None and re.search(dst_i, compact):
        expression = _assignment_rhs(compact, dst_i)
        return _region(
            "indirect_memory", "strided_indirect", "strided_indirect_map_f32", stride=stride,
            parameters=(("expression", _normalize_expression(expression or "", src, index)),),
        )

    has_minus = bool(re.search(rf"{re.escape(src)}\[{re.escape(index)}-1\]", compact))
    has_plus = bool(re.search(rf"{re.escape(src)}\[{re.escape(index)}\+1\]", compact))
    if has_minus and has_plus and re.search(dst_i, compact):
        expression = _assignment_rhs(compact, dst_i)
        return _region(
            "stencil", "neighborhood", "stencil_3_f32", neighbors=(-1, 0, 1),
            parameters=(("expression", _normalize_expression(expression or "", src, index)),),
        )

    scan = re.search(rf"([A-Za-z_]\w*)\+={src_i}", compact)
    if scan and re.search(rf"{dst_i}={re.escape(scan.group(1))}(?:;|$)", compact):
        return _region(
            "scan", "prefix_sum", "prefix_sum_f32", carried=scan.group(1),
            parameters=(("transition", "state+x"),),
        )

    recurrence = re.search(
        rf"([A-Za-z_]\w*)=\1\*[^;+}}]+\+{src_i}\*[^;+}}]+", compact,
    )
    if recurrence and re.search(rf"{dst_i}={re.escape(recurrence.group(1))}(?:;|$)", compact):
        transition = recurrence.group(0).split("=", 1)[1]
        transition = _normalize_expression(transition, src, index).replace(recurrence.group(1), "state")
        return _region(
            "recurrence", "iir", "iir_f32", carried=recurrence.group(1),
            parameters=(("transition", transition),),
        )

    if re.search(dst_i, compact) and re.search(src_i, compact):
        assignment = _assignment_rhs(compact, dst_i)
        if assignment and _is_guarded_rhs(assignment, src, index, compact):
            return _region(
                "guarded_pointwise_map", "relu", "relu_f32",
                parameters=(("expression", "select(x>0,x,0)"),),
            )
        return _region(
            "pointwise_map", "pointwise_expr", "pointwise_expr_f32",
            parameters=(("expression", _normalize_expression(assignment or "", src, index)),),
        )

    raise CanonicalRegionError(
        "semantic-region-shape",
        "the selected function is outside the registered canonical bounded information-flow families",
        "add an attributed shared grammar family or isolate a supported bounded region",
    )


def corroborate_compiler_shape(
    region: CanonicalBoundedRegion,
    compiler_texts: Iterable[str],
) -> dict[str, Any]:
    text = "\n".join(value for value in compiler_texts if value)
    lowered = text.lower()
    signals = {
        "memory": bool(re.search(r"\b(load|store|getindex|setindex|index|len|slice)\b", lowered)),
        "arithmetic": bool(re.search(r"\b(add|fadd|mul|fmul|sub|fsub|div|fdiv|checkedadd)\b", lowered)),
        "compare": bool(re.search(r"\b(eq|ne|lt|le|gt|ge|icmp|fcmp|switchint|select)\b", lowered)),
        "loop_carried": bool(re.search(r"\b(phi|phinode|backedge|checkedadd)\b", lowered)),
        "remainder": bool(
            re.search(r"\b(urem|srem|frem|rem)\b", lowered)
            or (
                re.search(r"\b(sdiv|udiv|checked_sdiv_int|checked_udiv_int)\b", lowered)
                and re.search(r"\b(mul|mul_int)\b", lowered)
                and re.search(r"\b(sub|sub_int)\b", lowered)
            )
        ),
    }
    required = {
        "ordered_reduction": ("arithmetic", "compare"),
        "pointwise_map": ("memory", "arithmetic"),
        "guarded_pointwise_map": ("memory", "compare"),
        "stencil": ("memory", "arithmetic"),
        "scan": ("memory", "arithmetic", "loop_carried"),
        "recurrence": ("memory", "arithmetic", "loop_carried"),
        "indirect_memory": ("memory", "remainder"),
    }[region.family]
    missing = tuple(name for name in required if not signals[name])
    return {
        "status": "pass" if text and not missing else "fail",
        "required_signals": list(required),
        "observed_signals": signals,
        "missing_signals": list(missing),
        "evidence_sha256": canonical_hash({"text": text}),
        "claim_boundary": "structural compiler corroboration, not candidate equivalence",
    }


def build_canonical_graph(
    region: CanonicalBoundedRegion,
    *,
    name: str,
    language: str,
    compiler_identity: str,
    semantic_ir: str,
    function_identity: str,
    source_provenance: dict[str, Any],
    language_contracts: dict[str, Any],
    compiler_corroboration: dict[str, Any],
    excluded_claims: tuple[str, ...],
) -> SemanticFlowGraph:
    method = f"{language}-compiler-shape-plus-contract"

    def bound(identifier: str, category: str, statement: str, construct: str):
        return obligation(
            f"{language}.{identifier}", category, statement, proof_method=method,
            language=language, native_construct=construct,
            facts={"canonical_region_hash": region.region_hash},
        )

    bounds = bound("bounds", "bounds", "all indexed accesses remain within declared sequence extents", "bounded-sequence")
    aliasing = bound("alias", "aliasing", "input/output aliasing matches the declared region contract", "borrowed-view")
    numeric = bound("numeric", "numeric", "arithmetic, overflow, and floating-point order preserve the native contract", region.operation)
    nodes: list[SemanticFlowNode] = [
        SemanticFlowNode("input.src", "Input", "borrowed sequence", (), f"sequence<{region.element_type}>", {"role": "source"}, source_provenance, (bounds,)),
    ]
    if region.output_roles and region.output_roles != ("count",):
        nodes.append(SemanticFlowNode("input.dst", "Input", "borrowed mutable sequence", (), f"sequence<{region.element_type}>", {"role": "destination"}, source_provenance, (aliasing, bounds)))
    nodes.append(SemanticFlowNode("control.loop", "Loop", "bounded ordered traversal", ("input.src",), "index", {"form": region.loop_form}, source_provenance, (bounds,)))

    load_ids: list[str] = []
    offsets = region.neighbor_offsets or (0,)
    for offset in offsets:
        suffix = "0" if offset == 0 else f"p{offset}" if offset > 0 else f"m{-offset}"
        node_id = f"load.src.{suffix}"
        load_ids.append(node_id)
        nodes.append(SemanticFlowNode(node_id, "Load", "sequence element", ("input.src", "control.loop"), region.element_type, {"offset": offset}, source_provenance, (bounds,)))

    operation_inputs: tuple[str, ...] = tuple(load_ids)
    if region.family == "indirect_memory":
        nodes.append(SemanticFlowNode("address.indirect", "Address", "constant-stride modulo extent", ("control.loop", "input.src"), "index", {"stride": region.indirect_stride}, source_provenance, (bounds,)))
        operation_inputs = (*operation_inputs, "address.indirect")
    if region.family in {"scan", "recurrence"}:
        state_obligation = bound("state.order", "state", "loop-carried state follows source iteration order", "loop-carried-state")
        nodes.append(SemanticFlowNode("state.previous", "StateRead", region.carried_state or "state", ("control.loop",), region.element_type, {}, source_provenance, (state_obligation,)))
        operation_inputs = (*operation_inputs, "state.previous")
    if region.family == "guarded_pointwise_map":
        nodes.append(SemanticFlowNode("predicate", "Compare", "pointwise guard", operation_inputs, "bool", {}, source_provenance, (numeric,)))
        nodes.append(SemanticFlowNode("operation", "Select", region.operation, (*operation_inputs, "predicate"), region.element_type, {"semantic_parameters": dict(region.semantic_parameters)}, source_provenance, (numeric,)))
    elif region.family == "ordered_reduction":
        nodes.append(SemanticFlowNode("predicate", "Compare", "element predicate", operation_inputs, "bool", {}, source_provenance, (numeric,)))
        nodes.append(SemanticFlowNode("operation", "Reduce", region.operation, ("predicate", "control.loop"), region.result_type, {"algebra": "ordered-sum", "semantic_parameters": dict(region.semantic_parameters)}, source_provenance, (numeric,)))
    else:
        nodes.append(SemanticFlowNode("operation", "Map", region.operation, operation_inputs, region.element_type, {"semantic_parameters": dict(region.semantic_parameters)}, source_provenance, (numeric,)))
    if region.family in {"scan", "recurrence"}:
        nodes.append(SemanticFlowNode("state.next", "StateWrite", region.carried_state or "state", ("operation",), region.element_type, {}, source_provenance, (numeric,)))
    if region.output_roles == ("count",):
        nodes.append(SemanticFlowNode("output", "Output", "scalar result", ("operation",), region.result_type, {}, source_provenance, ()))
    else:
        nodes.append(SemanticFlowNode("store.dst", "Store", "sequence element", ("input.dst", "control.loop", "operation"), None, {}, source_provenance, (bounds, aliasing)))
        nodes.append(SemanticFlowNode("output", "Output", "mutated destination extent", ("store.dst",), "void", {}, source_provenance, ()))

    node_by_id = {node.id: node for node in nodes}
    edges: list[SemanticFlowEdge] = []
    for destination in nodes:
        for source in destination.inputs:
            source_node = node_by_id[source]
            memory = "argument" if source_node.kind == "Input" else "register"
            edges.append(SemanticFlowEdge(
                f"edge.{len(edges)}", source, destination.id,
                source_node.output_type or "effect", "borrowed" if source_node.kind == "Input" else "ephemeral",
                "source" if source == "input.src" else "destination" if source == "input.dst" else "local",
                "function-call", "source-order", memory_region=memory,
                logical_shape=("n",) if source_node.kind == "Input" else (), validity_scope="region",
            ))

    effects = [SemanticEffect(
        "effect.read", "MemoryRead", "execute", "source sequence", "observable-through-result",
        "source-order", tuple(load_ids), (bounds.id,), {"family": region.family},
    )]
    if region.output_roles != ("count",):
        effects.append(SemanticEffect(
            "effect.write", "MemoryWrite", "execute", "destination sequence", "function-observable",
            "source-order", ("store.dst",), (bounds.id, aliasing.id), {"family": region.family},
        ))

    return SemanticFlowGraph(
        name, language, compiler_identity, semantic_ir, function_identity,
        tuple(nodes), tuple(edges),
        {
            "canonical_region_version": CANONICAL_REGION_VERSION,
            "canonical_region": region.to_dict(),
            "compiler_corroboration": compiler_corroboration,
            "language_contracts": language_contracts,
            "exactness": region.exactness,
        },
        excluded_claims,
        obligations=(bounds, aliasing, numeric),
        effects=tuple(effects),
    )


def _region(
    family: str,
    canonical: str,
    operation: str,
    *,
    carried: str | None = None,
    neighbors: tuple[int, ...] = (),
    stride: int | None = None,
    parameters: tuple[tuple[str, str], ...] = (),
) -> CanonicalBoundedRegion:
    return CanonicalBoundedRegion(
        family, canonical, operation, "f32", "void", ("source",), ("destination",),
        "single-bounded-loop", "E1-ordered", carried, neighbors, stride,
        ("bounded", "allocation-free", "single-output"), parameters,
    )


def _compact(value: str) -> str:
    value = re.sub(r"//[^\n]*|#[^\n]*", "", value)
    value = re.sub(r"\s*\n\s*", ";", value)
    return re.sub(r"[ \t\r]+", "", value)


def _sequence_names(language: str, signature: str, source: str) -> tuple[str, str] | None:
    if language == "rust":
        mutable = re.search(r"([A-Za-z_]\w*)\s*:\s*&\s*mut\s*\[f32\]", signature)
        borrowed = re.search(r"([A-Za-z_]\w*)\s*:\s*&\s*\[f32\]", signature)
    elif language == "zig":
        mutable = re.search(r"([A-Za-z_]\w*)\s*:\s*\[\]f32", signature)
        borrowed = re.search(r"([A-Za-z_]\w*)\s*:\s*\[\]const\s+f32", signature)
    else:
        header = source.split("\n", 1)[0]
        mutable_values = re.findall(r"([A-Za-z_]\w*)\s*::\s*(?:Vector|Array)\{Float32(?:,\s*1)?\}", header)
        if len(mutable_values) < 2:
            return None
        return mutable_values[0], mutable_values[1]
    return (mutable.group(1), borrowed.group(1)) if mutable and borrowed else None


def _is_count_equal(language: str, compact: str, signature: str) -> bool:
    signature_compact = re.sub(r"\s+", "", signature)
    if language == "rust":
        boundary = "&[u8]" in signature_compact and "u8" in signature_compact and "->usize" in signature_compact
        operation = "==" in compact and (".fold(" in compact or ".count(" in compact or "while" in compact or "for" in compact)
    elif language == "zig":
        boundary = "[]constu8" in signature_compact and ":u8" in signature_compact and ")usize" in signature_compact
        operation = "@intFromBool(" in compact and "==" in compact
    else:
        boundary = signature_compact in {"Vector{UInt8},UInt8", "Array{UInt8,1},UInt8"}
        operation = "==needle" in compact and ("count+=" in compact or "count(" in compact)
    return boundary and operation


def _loop_count(language: str, source: str) -> int:
    if language == "rust":
        return len(re.findall(r"\b(?:for|while|loop)\b", source))
    if language == "zig":
        return len(re.findall(r"\b(?:for|while)\s*\(", source))
    return len(re.findall(r"(?m)^\s*(?:@\w+\s+)?(?:for|while)\b", source))


def _loop_form(language: str, source: str, *, allow_fold: bool = False) -> str:
    # Source spelling belongs in provenance. The canonical graph records the semantic traversal.
    _ = language, source, allow_fold
    return "ordered-bounded-traversal"


def _loop_index(language: str, source: str) -> str | None:
    patterns = {
        "rust": r"\bfor\s+([A-Za-z_]\w*)\s+in\s+",
        "zig": r"\bfor\s*\([^)]*\)\s*\|(?:[^,|]+,\s*)?([A-Za-z_]\w*)\|",
        "julia": r"\bfor\s+([A-Za-z_]\w*)\s+in\s+",
    }
    match = re.search(patterns[language], source)
    return match.group(1) if match else None


def _indirect_stride(compact: str, index: str) -> int | None:
    match = re.search(rf"(?:\(|=){re.escape(index)}\*(\d+)(?:u|usize)?\)?%", compact)
    if not match:
        match = re.search(rf"mod\({re.escape(index)}\*(\d+),", compact)
    return int(match.group(1)) if match else None


def _assignment_rhs(compact: str, lhs_pattern: str) -> str | None:
    match = re.search(lhs_pattern + r"=([^;}}]+)", compact)
    return match.group(1) if match else None


def _is_guarded_rhs(rhs: str, src: str, index: str, compact: str) -> bool:
    source_value = rf"{re.escape(src)}\[{re.escape(index)}\]"
    return bool(
        ("?" in rhs and ":" in rhs)
        or ("if" in rhs and "else" in compact)
        or re.search(source_value + r">(?:0|0\.0f?)", compact)
    )


def _normalize_expression(expression: str, source: str, index: str) -> str:
    value = expression
    replacements = (
        (rf"{re.escape(source)}\[{re.escape(index)}-1\]", "x[-1]"),
        (rf"{re.escape(source)}\[{re.escape(index)}\+1\]", "x[1]"),
        (rf"{re.escape(source)}\[{re.escape(index)}\]", "x"),
        (rf"{re.escape(source)}\[[A-Za-z_]\w*\]", "indirect"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    value = re.sub(
        r"(?<![A-Za-z0-9_.])(\d+(?:\.\d+)?)(?:f0|f32|f64)(?![A-Za-z0-9_])",
        lambda match: _canonical_number(match.group(1)),
        value,
    )
    value = re.sub(
        r"(?<![A-Za-z0-9_.])(\d+\.\d+)(?![A-Za-z0-9_])",
        lambda match: _canonical_number(match.group(1)),
        value,
    )
    return value


def _canonical_number(value: str) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else format(number, ".9g")
