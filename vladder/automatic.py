from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from .candidates import Candidate
from .extractor import ExtractedFunction, extract_function
from .flow import FlowGraph, analyze_ir, build_flow_graph, emit_target_ir, write_flow_artifacts
from .report import write_json
from .region_closure import describe_c_boundary
from .toolchain import discover_toolchain
from .semantic_closure import EffectFootprint, FunctionSummary
from .cpp_semantics import analyze_ir_effects
from .closure_bindings import cpp_function_summary


AUTOMATIC_SUPPORT_VERSION = "bounded-regions-v1"
SUPPORTED_FAMILIES = frozenset(
    {"pointwise_map", "guarded_pointwise_map", "stencil", "scan", "recurrence", "indirect_memory"}
)


@dataclass(frozen=True)
class AdapterRequirement:
    kind: str
    reason: str
    required_boundary: str
    next_workflow: str


@dataclass(frozen=True)
class CanonicalLoop:
    index: str
    start: int
    bound: str
    bound_offset: int
    condition: str
    body: str
    start_offset: int
    end_offset: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start,
            "bound": self.bound,
            "bound_offset": self.bound_offset,
            "condition": self.condition,
            "body_sha256": hashlib.sha256(self.body.encode()).hexdigest(),
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }


@dataclass(frozen=True)
class AutomaticSupport:
    status: str
    support_version: str
    source: str
    source_sha256: str
    function: str
    function_sha256: str | None
    language: str
    family: str | None
    canonical: str | None
    exactness: str
    lowerer: str | None
    loop: CanonicalLoop | None
    adapters: tuple[AdapterRequirement, ...]
    proof_layers: tuple[str, ...]
    region_closure: dict[str, Any] | None = None
    compositional_summary: dict[str, Any] | None = None

    @property
    def supported(self) -> bool:
        return self.status == "supported"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["supported"] = self.supported
        data["loop"] = self.loop.to_dict() if self.loop else None
        return data


def inspect_automatic_region(source: Path, function: str, out_dir: Path | None = None) -> AutomaticSupport:
    source = source.resolve()
    text = source.read_text()
    language = "c" if source.suffix.lower() == ".c" else "c++"
    source_digest = hashlib.sha256(text.encode()).hexdigest()

    def finish(report: AutomaticSupport) -> AutomaticSupport:
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(out_dir / "automatic-support.json", report.to_dict())
        return report

    if language != "c":
        return finish(_unsupported(
            source,
            source_digest,
            function,
            language,
            "language-adapter",
            "the C frontend accepts C source only; use the compilation-database-aware C++ frontend",
            "a compile_commands-backed bounded C++ definition",
            "vladder cpp inspect|isolate|synthesize|optimize, then a project-specific adapter if required",
        ))
    try:
        extracted = extract_function(text, function)
    except ValueError as error:
        return finish(_unsupported(source, source_digest, function, language, "function-extraction-adapter", str(error), "one defined standalone function", "project-specific extraction adapter"))
    function_digest = hashlib.sha256(extracted.source.encode()).hexdigest()
    if not _canonical_abi(extracted):
        boundary = describe_c_boundary(extracted.signature, extracted.name)
        tc = discover_toolchain()
        analysis_root = (out_dir or source.parent / ".vladder-inspect").resolve()
        ir_info = emit_target_ir(tc, source, analysis_root / "analysis", function)
        normalized_ir = Path(str(ir_info.get("normalized_ir", "")))
        ir_text = normalized_ir.read_text(errors="replace") if normalized_ir.is_file() else ""
        lowered_signature = ir_text.splitlines()[0] if ir_text else None
        closure = {
            "schema_version": "vladder-region-closure-v1",
            "status": "abi_closed_grammar_missing" if boundary.modeled else "abi_unmodeled",
            "c_boundary": boundary.to_dict(),
            "ir_transform_ready": boundary.modeled and ir_info.get("status") == "ok" and bool(ir_text),
            "source_transform_ready": False,
            "compiler_ir": {
                "status": ir_info.get("status"),
                "compiler": ir_info.get("compiler"),
                "compiler_version": ir_info.get("compiler_version"),
                "target_triple": ir_info.get("target_triple"),
                "normalized_ir": str(normalized_ir) if ir_text else None,
                "normalized_ir_sha256": hashlib.sha256(ir_text.encode()).hexdigest() if ir_text else None,
                "lowered_signature": lowered_signature,
                "error": ir_info.get("error"),
            },
            "claim_boundary": "typed C ABI capture only; an executable semantic grammar is still required",
        }
        compositional_summary = None
        if boundary.modeled and ir_text:
            try:
                effects = analyze_ir_effects(ir_text, function)
                compositional_summary = cpp_function_summary(
                    function,
                    str(ir_info.get("compiler_version", "unknown")),
                    effects,
                    source_language="c",
                    semantic_capture="abi_and_effects_only",
                    residual_boundaries=({
                        "kind": "grammar-adapter",
                        "reason": "the ABI and effects are captured but no executable semantic grammar represents this body",
                        "required_adapter": "select or implement a bounded semantic grammar",
                    },),
                ).to_dict()
            except ValueError:
                compositional_summary = None
        return finish(_unsupported(
            source, source_digest, function, language,
            "grammar-adapter" if boundary.modeled else "abi-adapter",
            (
                "the first-order C ABI is modeled, but no executable grammar is registered for this semantic region"
                if boundary.modeled else "signature is outside the bounded first-order C ABI model"
            ),
            "a scalar/POD result and scalar or borrowed pointer/extent inputs",
            "select a bounded semantic grammar or supply a protocol adapter",
            function_digest,
            region_closure=closure,
            compositional_summary=compositional_summary,
        ))
    try:
        loop = extract_canonical_loop(extracted)
    except ValueError as error:
        return finish(_unsupported(source, source_digest, function, language, "loop-shape-adapter", str(error), "one braced size_t loop with unit increment and recognized bound", "operator or loop-domain adapter", function_digest))
    forbidden = _forbidden_semantics(loop.body, extracted.body)
    if forbidden:
        return finish(_unsupported(source, source_digest, function, language, forbidden[0], forbidden[1], forbidden[2], forbidden[3], function_digest))

    tc = discover_toolchain()
    analysis_root = (out_dir or source.parent / ".vladder-inspect").resolve()
    ir_info = emit_target_ir(tc, source, analysis_root / "analysis", function)
    if ir_info.get("status") != "ok":
        return finish(_unsupported(source, source_digest, function, language, "compiler-adapter", str(ir_info.get("error", "IR emission failed")), "Clang-compatible bounded source", "compile-command adapter", function_digest))
    try:
        ir_slice = analyze_ir(ir_info, function)
        graph = build_flow_graph(extracted, dict(ir_info.get("stats") or {}), ir_slice)
    except Exception as error:
        return finish(_unsupported(source, source_digest, function, language, "ir-extraction-adapter", str(error), "an extractable output slice", "specialized graph adapter", function_digest))
    if out_dir is not None:
        write_flow_artifacts(out_dir, graph, ir_info, ir_slice)
    if graph.family not in SUPPORTED_FAMILIES:
        return finish(_unsupported(source, source_digest, function, language, "region-class-adapter", f"classified region {graph.family}/{graph.canonical} is not in {AUTOMATIC_SUPPORT_VERSION}", "a supported single-loop array region", "operator, pipeline, or specialist adapter", function_digest, graph.family, graph.canonical))
    if graph.family == "indirect_memory" and not isinstance(graph.source_pattern.get("indirect_stride"), int):
        return finish(_unsupported(source, source_digest, function, language, "proof-model-adapter", "indirect index is outside the constant-stride modulo-n footprint model", "size_t j = (i * CONSTANT) % n with n>0", "specialized pointer-footprint adapter", function_digest, graph.family, graph.canonical))
    report = AutomaticSupport(
        "supported",
        AUTOMATIC_SUPPORT_VERSION,
        str(source),
        source_digest,
        function,
        function_digest,
        language,
        graph.family,
        graph.canonical,
        "E1-ordered",
        "ordered-unroll",
        loop,
        (),
        ("structural legality", "Z3 loop partition", "Z3 memory footprint", "LLVM refinement identity or Alive2", "differential execution", "applied-source identity"),
        None,
        FunctionSummary(
            f"c::{function}", "c", str(ir_info.get("compiler_version", "unknown")),
            function_digest, getattr(graph, "graph_hash", ""),
            EffectFootprint(("argmem",), ("argmem",)), (), 0,
            {"family": graph.family, "canonical": graph.canonical, "semantic_capture": "closed", "residual_boundaries": []},
        ).to_dict(),
    )
    return finish(report)


def _unsupported(
    source: Path,
    source_digest: str,
    function: str,
    language: str,
    kind: str,
    reason: str,
    boundary: str,
    workflow: str,
    function_digest: str | None = None,
    family: str | None = None,
    canonical: str | None = None,
    region_closure: dict[str, Any] | None = None,
    compositional_summary: dict[str, Any] | None = None,
) -> AutomaticSupport:
    return AutomaticSupport(
        "adapter_required",
        AUTOMATIC_SUPPORT_VERSION,
        str(source),
        source_digest,
        function,
        function_digest,
        language,
        family,
        canonical,
        "unclassified",
        None,
        None,
        (AdapterRequirement(kind, reason, boundary, workflow),),
        (),
        region_closure,
        compositional_summary,
    )


def _canonical_abi(fn: ExtractedFunction) -> bool:
    signature = re.sub(r"\s+", " ", fn.signature).strip()
    pattern = (
        rf"^(?:static\s+)?void\s+{re.escape(fn.name)}\s*\(\s*"
        r"float\s*\*\s*(?:restrict\s+)?dst\s*,\s*"
        r"const\s+float\s*\*\s*(?:restrict\s+)?src\s*,\s*"
        r"size_t\s+n\s*\)$"
    )
    return re.match(pattern, signature) is not None


def _forbidden_semantics(loop_body: str, function_body: str | None = None) -> tuple[str, str, str, str] | None:
    if re.search(r"\b(?:volatile|_Atomic|atomic_)\b", function_body or loop_body):
        return ("memory-order-adapter", "volatile or atomic semantics occur in the target", "an explicit ownership and memory-order contract", "concurrency-memory-order adapter")
    if re.search(r"\b(?:break|continue|goto|return)\b", loop_body):
        return ("control-flow-adapter", "nonlocal loop control occurs in the target", "structured fallthrough loop control", "control-flow region adapter")
    calls = [name for name in re.findall(r"\b([A-Za-z_]\w*)\s*\(", loop_body) if name not in {"for", "if", "while", "switch", "sizeof", "_Alignof"}]
    if calls:
        return ("external-call-adapter", f"loop region contains calls: {sorted(set(calls))}", "a pure modeled call or an inlined semantic contract", "ExternalCall semantic adapter")
    return None


def extract_canonical_loop(fn: ExtractedFunction) -> CanonicalLoop:
    starts = list(re.finditer(r"\bfor\s*\(", fn.body))
    if len(starts) != 1:
        raise ValueError(f"expected exactly one for-loop, found {len(starts)}")
    start = starts[0].start()
    open_paren = fn.body.find("(", start)
    close_paren = _match_delimiter(fn.body, open_paren, "(", ")")
    header = fn.body[open_paren + 1 : close_paren]
    parts = header.split(";")
    if len(parts) != 3:
        raise ValueError("for-loop header must contain three canonical clauses")
    init, condition, increment = (item.strip() for item in parts)
    init_match = re.fullmatch(r"size_t\s+([A-Za-z_]\w*)\s*=\s*(\d+)", init)
    if not init_match:
        raise ValueError("loop initializer must be `size_t index = constant`")
    index = init_match.group(1)
    if not re.fullmatch(rf"(?:\+\+\s*{re.escape(index)}|{re.escape(index)}\s*\+\+)", increment):
        raise ValueError("loop increment must be unit pre/post increment")
    direct = re.fullmatch(rf"{re.escape(index)}\s*<\s*([A-Za-z_]\w*)", condition)
    offset = re.fullmatch(rf"{re.escape(index)}\s*\+\s*(\d+)\s*<\s*([A-Za-z_]\w*)", condition)
    if direct:
        bound_offset, bound = 0, direct.group(1)
    elif offset:
        bound_offset, bound = int(offset.group(1)), offset.group(2)
    else:
        raise ValueError("loop condition must be `index < bound` or `index + constant < bound`")
    body_open = close_paren + 1
    while body_open < len(fn.body) and fn.body[body_open].isspace():
        body_open += 1
    if body_open >= len(fn.body) or fn.body[body_open] != "{":
        raise ValueError("loop body must use braces")
    body_end = _match_delimiter(fn.body, body_open, "{", "}")
    return CanonicalLoop(index, int(init_match.group(2)), bound, bound_offset, condition, fn.body[body_open + 1 : body_end], start, body_end + 1)


def _match_delimiter(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string: str | None = None
    escaped = False
    i = start
    while i < len(text):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
        elif char in {'"', "'"}:
            in_string = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"unbalanced {opening}{closing} delimiters")


def ordered_unroll_candidate(fn: ExtractedFunction, graph: FlowGraph, factor: int = 4) -> Candidate | None:
    if graph.family not in SUPPORTED_FAMILIES or factor < 2:
        return None
    try:
        loop = extract_canonical_loop(fn)
    except ValueError:
        return None
    forbidden = _forbidden_semantics(loop.body, fn.body)
    if forbidden or not _canonical_abi(fn):
        return None
    body = loop.body.strip()
    lanes = []
    for lane in range(factor):
        lane_body = body if lane == 0 else re.sub(rf"\b{re.escape(loop.index)}\b", f"({loop.index} + {lane}u)", body)
        lanes.append("        {\n" + _indent(lane_body, 12) + "\n        }")
    required = loop.bound_offset + factor
    block_condition = f"{loop.index} < {loop.bound} && {loop.bound} - {loop.index} >= {required}u"
    replacement = "\n".join(
        [
            "{",
            f"    size_t {loop.index} = {loop.start}u;",
            f"    for (; {block_condition}; {loop.index} += {factor}u) {{",
            *lanes,
            "    }",
            f"    for (; {loop.condition}; ++{loop.index}) {{",
            _indent(body, 8),
            "    }",
            "}",
        ]
    )
    new_body = fn.body[: loop.start_offset] + replacement + fn.body[loop.end_offset :]
    open_brace = fn.source.find("{")
    regenerated = fn.source[: open_brace + 1] + new_body + fn.source[-1:]
    regenerated_fn = extract_function(regenerated, fn.name).renamed("transform_candidate")
    return Candidate(
        f"automatic_ordered_unroll{factor}_{graph.family}",
        "__attribute__((noinline))\n" + regenerated_fn,
        tags=("automatic-region", "ordered-unroll", f"factor:{factor}", graph.family, graph.canonical),
        proof="structural_ordered_unroll",
    )


def loop_hint_candidate(fn: ExtractedFunction, graph: FlowGraph, factor: int = 4) -> Candidate | None:
    if graph.family not in SUPPORTED_FAMILIES or factor < 2:
        return None
    try:
        loop = extract_canonical_loop(fn)
    except ValueError:
        return None
    if _forbidden_semantics(loop.body, fn.body) or not _canonical_abi(fn):
        return None
    directive = (
        "\n#if defined(__clang__) && !defined(VLADDER_PROOF)\n"
        f"#pragma clang loop unroll_count({factor})\n"
        "#endif\n"
    )
    new_body = fn.body[: loop.start_offset] + directive + fn.body[loop.start_offset :]
    open_brace = fn.source.find("{")
    regenerated = fn.source[: open_brace + 1] + new_body + fn.source[-1:]
    regenerated_fn = extract_function(regenerated, fn.name).renamed("transform_candidate")
    return Candidate(
        f"automatic_unroll_hint{factor}_{graph.family}",
        "__attribute__((noinline))\n" + regenerated_fn,
        tags=("automatic-region", "source-regenerated", "loop-unroll-hint", f"factor:{factor}", graph.family, graph.canonical),
        proof="structural_loop_hint",
    )


def _indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line.rstrip() for line in text.splitlines())
