from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from pathlib import Path
import re
from typing import Any

from .extractor import ExtractedFunction
from .llvm_ir import IRSlice, classify_slice, extract_output_slice
from .report import write_json
from .toolchain import Toolchain, compiler_version, cpu_model, run


@dataclass(frozen=True)
class FlowNode:
    id: str
    opcode: str
    type: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FlowEdge:
    src: str
    dst: str
    kind: str


@dataclass(frozen=True)
class FlowGraph:
    family: str
    canonical: str
    nodes: list[FlowNode]
    edges: list[FlowEdge]
    invariants: dict[str, Any]
    grammar: list[str]
    source_pattern: dict[str, Any]
    ir_stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)f?"


def _body1(fn: ExtractedFunction) -> str:
    return re.sub(r"\s+", " ", fn.body).strip()


def _f32(value: str) -> str:
    value = value.strip()
    return value if value.endswith(("f", "F")) else value + "f"


def emit_target_ir(tc: Toolchain, source: Path, out_dir: Path, function: str) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "target.raw.ll"
    normalized = out_dir / "target.normalized.ll"
    analysis_raw = out_dir / "target.analysis.raw.ll"
    analysis_ir = out_dir / "target.analysis.ll"
    optimized_flags = ["-std=c99", "-O3", "-march=native"]
    analysis_flags = ["-std=c99", "-O1", "-fno-vectorize", "-fno-slp-vectorize", "-fno-unroll-loops"]
    result = run(
        [
            tc.compiler,
            *optimized_flags,
            "-S",
            "-emit-llvm",
            str(source),
            "-o",
            str(raw),
        ],
        timeout=120,
    )
    if result.returncode != 0:
        return {"status": "error", "error": (result.stdout + result.stderr)[-2000:]}
    analysis_result = run(
        [tc.compiler, *analysis_flags, "-S", "-emit-llvm", str(source), "-o", str(analysis_raw)],
        timeout=120,
    )
    if analysis_result.returncode != 0:
        return {"status": "error", "error": (analysis_result.stdout + analysis_result.stderr)[-2000:]}
    text = raw.read_text(errors="replace")
    normalized.write_text(_normalize_ir(text, function))
    analysis_ir.write_text(_normalize_ir(analysis_raw.read_text(errors="replace"), function))
    triple = re.search(r'^target triple = "([^"]+)"', text, re.MULTILINE)
    return {
        "status": "ok",
        "source": str(source.resolve()),
        "function": function,
        "compiler": tc.compiler,
        "compiler_version": compiler_version(tc.compiler),
        "target_triple": triple.group(1) if triple else "unknown",
        "target_cpu": cpu_model(),
        "optimized_flags": optimized_flags,
        "analysis_flags": analysis_flags,
        "raw_ir": str(raw),
        "normalized_ir": str(normalized),
        "analysis_raw_ir": str(analysis_raw),
        "analysis_ir": str(analysis_ir),
        "stats": llvm_ir_stats(normalized),
    }


def _normalize_ir(text: str, function: str) -> str:
    lines = []
    keep = False
    brace_depth = 0
    for line in text.splitlines():
        if line.startswith(f"define ") and f"@{function}(" in line:
            keep = True
            brace_depth = line.count("{") - line.count("}")
        if keep:
            line = re.sub(r",\s*![A-Za-z0-9_.]+\s+![0-9]+", "", line)
            lines.append(line)
            if not line.startswith("define "):
                brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0 and line.strip() == "}":
                keep = False
    return "\n".join(lines) + "\n"


def emit_function_ir(source_ir: Path, destination: Path, function: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_normalize_ir(source_ir.read_text(errors="replace"), function))


def llvm_ir_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(errors="replace")
    return {
        "loads": len(re.findall(r"\bload\b", text)),
        "stores": len(re.findall(r"\bstore\b", text)),
        "phis": len(re.findall(r"\bphi\b", text)),
        "branches": len(re.findall(r"\bbr\b", text)),
        "selects": len(re.findall(r"\bselect\b", text)),
        "vector_ops": len(re.findall(r"<\d+\s+x\s+", text)),
    }


def build_flow_graph(fn: ExtractedFunction, ir_stats: dict[str, Any] | None = None, ir_slice: IRSlice | None = None) -> FlowGraph:
    body = _body1(fn)
    source_pattern = _classify_source(body)
    expression = _recover_pointwise_expression(body)
    if expression:
        source_pattern["expression"] = expression
    if ir_slice is not None:
        ir_pattern = classify_slice(ir_slice)
        pattern = dict(source_pattern)
        pattern["family"] = ir_pattern["family"]
        pattern["canonical"] = ir_pattern["canonical"]
        # Refine generic IR conditional forms without making source text the
        # semantic authority for affine, clamp, recurrence, or memory shapes.
        if ir_pattern["canonical"] in {"conditional_pointwise", "pointwise_expr", "affine"} and source_pattern["canonical"] not in {"unknown", "pointwise_expr", "conditional_pointwise"}:
            pattern["canonical"] = source_pattern["canonical"]
        elif source_pattern["canonical"] == "pointwise_expr" and expression:
            # LLVM's presence-based affine heuristic also matches x*x+c. Keep
            # the independently recovered expression when no affine constants
            # were recovered from source.
            pattern["canonical"] = "pointwise_expr"
        if source_pattern["family"] == "indirect_memory":
            pattern["family"] = "indirect_memory"
            pattern["canonical"] = source_pattern["canonical"]
        if source_pattern["canonical"] == "signum":
            pattern["canonical"] = "signum"
        pattern["ir_evidence"] = ir_pattern.get("evidence", [])
        pattern["ir_constants"] = ir_pattern.get("constants", [])
    else:
        pattern = source_pattern
    family = pattern["family"]
    canonical = pattern["canonical"]
    if ir_slice is not None:
        nodes = [
            FlowNode(arg["id"], "argument", arg["type"], {"provenance": "llvm-argument", "text": arg["text"]})
            for arg in ir_slice.arguments
        ]
        nodes.extend(
            FlowNode(node.id, node.opcode, node.type, {**node.attrs, "block": node.block, "provenance": node.text})
            for node in ir_slice.nodes
        )
        edges = [FlowEdge(edge["src"], edge["dst"], edge["kind"]) for edge in ir_slice.edges]
        invariants = _invariants(pattern)
        invariants.update(ir_slice.invariants)
        invariants["pointwise_independent"] = family in {"pointwise_map", "guarded_pointwise_map"} and not ir_slice.invariants["loop_carried_dependence"]
        invariants["parallel_iteration_space"] = invariants["pointwise_independent"] or family == "stencil"
        return FlowGraph(family, canonical, nodes, edges, invariants, grammar_for_family(family, canonical), pattern, ir_stats or {})

    nodes = [
        FlowNode("arg.dst", "argument", "float*"),
        FlowNode("arg.src", "argument", "const float*"),
        FlowNode("arg.n", "argument", "size_t"),
        FlowNode("idx.i", "induction", "size_t"),
    ]
    edges = [
        FlowEdge("arg.n", "idx.i", "domain"),
    ]
    if pattern.get("loads_src_i", True):
        nodes.append(FlowNode("load.src_i", "load", "float", {"array": "src", "index": "i"}))
        edges.append(FlowEdge("arg.src", "load.src_i", "memory"))
        edges.append(FlowEdge("idx.i", "load.src_i", "index"))
    op_node = FlowNode("op.root", canonical, "float", {k: v for k, v in pattern.items() if k not in {"family", "canonical"}})
    nodes.append(op_node)
    if pattern.get("loads_src_i", True):
        edges.append(FlowEdge("load.src_i", "op.root", "data"))
    nodes.append(FlowNode("store.dst_i", "store", "void", {"array": "dst", "index": "i"}))
    edges.extend([FlowEdge("op.root", "store.dst_i", "data"), FlowEdge("idx.i", "store.dst_i", "index")])
    if pattern.get("carried"):
        nodes.append(FlowNode("state.carried", "phi", "float", {"dependence": pattern["carried"]}))
        edges.append(FlowEdge("state.carried", "op.root", "loop_carried"))
        edges.append(FlowEdge("op.root", "state.carried", "next_iteration"))
    if pattern.get("neighbor_offsets"):
        for off in pattern["neighbor_offsets"]:
            nid = f"load.src_i{off:+d}"
            nodes.append(FlowNode(nid, "load", "float", {"array": "src", "index": f"i{off:+d}"}))
            edges.append(FlowEdge(nid, "op.root", "neighbor"))
    invariants = _invariants(pattern)
    grammar = grammar_for_family(family, canonical)
    return FlowGraph(family, canonical, nodes, edges, invariants, grammar, pattern, ir_stats or {})


def _classify_source(body: str) -> dict[str, Any]:
    if re.search(r"dst\s*\[\s*i\s*\]\s*=\s*src\s*\[\s*i\s*\]\s*\*\s*(?P<mul>" + FLOAT + r")\s*\+\s*(?P<add>" + FLOAT + r")\s*;", body):
        m = re.search(r"src\s*\[\s*i\s*\]\s*\*\s*(?P<mul>" + FLOAT + r")\s*\+\s*(?P<add>" + FLOAT + r")", body)
        return {"family": "pointwise_map", "canonical": "affine", "mul": _f32(m.group("mul")), "add": _f32(m.group("add"))}
    if re.search(r"dst\s*\[\s*i\s*\]\s*=\s*src\s*\[\s*i\s*\]\s*\+\s*(?P<add>" + FLOAT + r")\s*;", body):
        m = re.search(r"src\s*\[\s*i\s*\]\s*\+\s*(?P<add>" + FLOAT + r")", body)
        return {"family": "pointwise_map", "canonical": "affine", "mul": "1.0f", "add": _f32(m.group("add"))}
    if re.search(r"dst\s*\[\s*i\s*\]\s*=\s*src\s*\[\s*i\s*\]\s*/\s*(?P<div>" + FLOAT + r")\s*;", body):
        m = re.search(r"src\s*\[\s*i\s*\]\s*/\s*(?P<div>" + FLOAT + r")", body)
        div = float(m.group("div").rstrip("fF"))
        log2 = math.log2(abs(div)) if div else float("inf")
        return {"family": "pointwise_map", "canonical": "div_const", "divisor": _f32(m.group("div")), "exact_power2": div != 0.0 and abs(log2 - round(log2)) < 1e-12}
    clamp = re.search(
        r"if\s*\(\s*x\s*<\s*(?P<low>" + FLOAT + r")\s*\).*?dst\s*\[\s*i\s*\]\s*=\s*(?P=low)\s*;.*?"
        r"else\s+if\s*\(\s*x\s*>\s*(?P<high>" + FLOAT + r")\s*\).*?dst\s*\[\s*i\s*\]\s*=\s*(?P=high)\s*;.*?"
        r"else.*?dst\s*\[\s*i\s*\]\s*=\s*x\s*;",
        body,
    )
    if clamp:
        return {"family": "guarded_pointwise_map", "canonical": "saturating_projection", "low": _f32(clamp.group("low")), "high": _f32(clamp.group("high"))}
    if re.search(r"dst\s*\[\s*i\s*\]\s*=\s*x\s*<\s*0\.0f?\s*\?\s*-x\s*:\s*x\s*;", body):
        return {"family": "guarded_pointwise_map", "canonical": "abs_preserve_negzero"}
    if re.search(r"dst\s*\[\s*i\s*\]\s*=\s*x\s*>\s*0\.0f?\s*\?\s*x\s*:\s*0\.0f?\s*;", body):
        return {"family": "guarded_pointwise_map", "canonical": "relu"}
    if re.search(r"dst\s*\[\s*i\s*\]\s*=\s*x\s*>\s*0\.0f?\s*\?\s*x\s*:\s*x\s*\*\s*(?P<slope>" + FLOAT + r")\s*;", body):
        m = re.search(r"x\s*>\s*0\.0f?\s*\?\s*x\s*:\s*x\s*\*\s*(?P<slope>" + FLOAT + r")", body)
        return {"family": "guarded_pointwise_map", "canonical": "leaky_relu", "slope": _f32(m.group("slope"))}
    if re.search(r"dst\s*\[\s*i\s*\]\s*=\s*src\s*\[\s*i\s*\]\s*>\s*(?P<th>" + FLOAT + r")\s*\?\s*1\.0f?\s*:\s*0\.0f?\s*;", body):
        m = re.search(r"src\s*\[\s*i\s*\]\s*>\s*(?P<th>" + FLOAT + r")", body)
        return {"family": "guarded_pointwise_map", "canonical": "threshold01", "threshold": _f32(m.group("th"))}
    if "else if" in body and re.search(r"dst\s*\[\s*i\s*\]\s*=\s*1\.0f", body) and re.search(r"dst\s*\[\s*i\s*\]\s*=\s*-1\.0f", body) and re.search(r"dst\s*\[\s*i\s*\]\s*=\s*0\.0f", body):
        return {"family": "guarded_pointwise_map", "canonical": "signum"}
    if "src[i - 2]" in body and "src[i + 2]" in body:
        return {"family": "stencil", "canonical": "neighborhood", "neighbor_offsets": [-2, -1, 0, 1, 2]}
    if "src[i - 1]" in body and "src[i + 1]" in body:
        return {"family": "stencil", "canonical": "neighborhood", "neighbor_offsets": [-1, 0, 1]}
    if re.search(r"sum\s*\+=\s*src\s*\[\s*i\s*\]", body):
        return {"family": "scan", "canonical": "prefix_sum", "carried": "sum"}
    if "max_value" in body:
        return {"family": "scan", "canonical": "running_max", "carried": "max_value"}
    if re.search(r"\by\s*=\s*y\s*\*", body):
        return {"family": "recurrence", "canonical": "iir", "carried": "y"}
    indirect = re.search(
        r"size_t\s+j\s*=\s*\(\s*i\s*\*\s*(?P<stride>\d+)u?\s*\)\s*%\s*n\s*;.*?src\s*\[\s*j\s*\]",
        body,
    )
    if indirect:
        return {
            "family": "indirect_memory",
            "canonical": "strided_indirect",
            "indirect_stride": int(indirect.group("stride")),
            "indirect_index": f"(i * {int(indirect.group('stride'))}) % n",
        }
    if "%" in body and "src[j]" in body:
        return {"family": "indirect_memory", "canonical": "strided_indirect"}
    if "?" in body:
        return {"family": "guarded_pointwise_map", "canonical": "conditional_pointwise"}
    if re.search(r"dst\s*\[\s*i\s*\]\s*=", body):
        return {"family": "pointwise_map", "canonical": "pointwise_expr"}
    return {"family": "unknown", "canonical": "unknown", "loads_src_i": False}


def _recover_pointwise_expression(body: str) -> str | None:
    assignments = re.findall(r"dst\s*\[\s*i\s*\]\s*=\s*(.*?);", body)
    if len(assignments) != 1:
        return None
    expression = re.sub(r"src\s*\[\s*i\s*\]", "x", assignments[0]).strip()
    return expression


def _invariants(pattern: dict[str, Any]) -> dict[str, Any]:
    family = pattern["family"]
    pointwise = family in {"pointwise_map", "guarded_pointwise_map"}
    return {
        "pointwise_independent": pointwise,
        "loop_carried_dependence": pattern.get("carried"),
        "memory_access": "indirect" if family == "indirect_memory" else "affine",
        "parallel_iteration_space": pointwise or family == "stencil",
        "exact_fp_required": True,
    }


def grammar_for_family(family: str, canonical: str) -> list[str]:
    if canonical == "saturating_projection":
        return ["branch_to_select", "select_chain", "mask_blend", "vector_lanes", "compiler_flag_variants"]
    if canonical in {"affine", "div_const"}:
        return ["identity", "exact_strength_reduction", "vector_lanes", "compiler_flag_variants"]
    if family == "guarded_pointwise_map":
        return ["branch_to_select", "mask_blend", "compiler_flag_variants"]
    if family == "stencil":
        return ["boundary_peeling", "interior_vectorization", "compiler_flag_variants"]
    if family in {"scan", "recurrence"}:
        return ["dependency_latency_reduction", "compiler_flag_variants"]
    return ["compiler_flag_variants"]


def write_flow_artifacts(out_dir: Path, graph: FlowGraph, ir_info: dict[str, Any], ir_slice: IRSlice | None = None) -> None:
    analysis_dir = out_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    write_json(analysis_dir / "flow_graph.json", graph.to_dict())
    write_json(analysis_dir / "shape.json", {"family": graph.family, "canonical": graph.canonical, "invariants": graph.invariants, "grammar": graph.grammar})
    write_json(analysis_dir / "ir.json", ir_info)
    if ir_slice is not None:
        write_json(analysis_dir / "slice.json", ir_slice.to_dict())


def analyze_ir(ir_info: dict[str, Any], function: str) -> IRSlice:
    path = Path(str(ir_info["analysis_ir"]))
    return extract_output_slice(path, function)
