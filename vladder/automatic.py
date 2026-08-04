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
from .toolchain import discover_toolchain


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
            "vladder cpp inspect|isolate|optimize, then a project-specific adapter if required",
        ))
    try:
        extracted = extract_function(text, function)
    except ValueError as error:
        return finish(_unsupported(source, source_digest, function, language, "function-extraction-adapter", str(error), "one defined standalone function", "project-specific extraction adapter"))
    function_digest = hashlib.sha256(extracted.source.encode()).hexdigest()
    if not _canonical_abi(extracted):
        return finish(_unsupported(source, source_digest, function, language, "abi-adapter", "signature is outside the canonical bounded-region ABI", "void function(float *dst, const float *src, size_t n)", "operator contract adapter", function_digest))
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
