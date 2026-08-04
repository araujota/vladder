from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any


SSA = r"%[-A-Za-z$._0-9]+"


@dataclass(frozen=True)
class IRInstruction:
    id: str
    opcode: str
    type: str
    text: str
    block: str
    operands: tuple[str, ...]
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IRSlice:
    function: str
    arguments: list[dict[str, str]]
    nodes: list[IRInstruction]
    edges: list[dict[str, str]]
    roots: list[str]
    blocks: dict[str, list[str]]
    invariants: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_function_ir(path: Path, function: str) -> tuple[list[dict[str, str]], list[IRInstruction], dict[str, list[str]]]:
    """Parse the stable LLVM textual subset emitted by Clang for one function."""
    text = path.read_text(errors="replace")
    match = re.search(rf"^define\s+.*?@{re.escape(function)}\((.*?)\).*?\{{\s*$", text, re.MULTILINE)
    if not match:
        raise ValueError(f"function @{function} not found in {path}")
    arguments = []
    for index, arg in enumerate(_split_commas(match.group(1))):
        ssa = re.search(SSA, arg)
        arguments.append({"id": ssa.group(0) if ssa else f"%arg{index}", "type": _value_type(arg), "text": arg.strip()})

    body_start = match.end()
    body_end = _matching_function_end(text, body_start)
    lines = text[body_start:body_end].splitlines()
    instructions: list[IRInstruction] = []
    blocks: dict[str, list[str]] = {"entry": []}
    block = "entry"
    serial = 0
    for raw in lines:
        line = re.sub(r",\s*![A-Za-z0-9_.]+\s+![0-9]+", "", raw).strip()
        if not line or line.startswith(";"):
            continue
        label = re.match(r"^([-A-Za-z$._0-9]+):", line)
        if label:
            block = label.group(1)
            blocks.setdefault(block, [])
            continue
        result = re.match(rf"^({SSA})\s*=\s*(.*)$", line)
        if result:
            node_id, rhs = result.groups()
        else:
            serial += 1
            node_id, rhs = f"%effect.{serial}", line
        opcode = _opcode(rhs)
        operands = tuple(x for x in re.findall(SSA, rhs) if x != node_id)
        attrs: dict[str, Any] = {}
        if opcode == "store":
            parts = _split_commas(rhs[len("store "):])
            attrs["value"] = _last_value(parts[0]) if parts else ""
            attrs["pointer"] = _last_value(parts[1]) if len(parts) > 1 else ""
        elif opcode == "load":
            parts = _split_commas(rhs[len("load "):])
            attrs["pointer"] = _last_value(parts[1]) if len(parts) > 1 else ""
        elif opcode == "getelementptr":
            attrs["base"] = operands[0] if operands else ""
            attrs["indices"] = list(operands[1:])
        elif opcode == "phi":
            attrs["incoming_blocks"] = re.findall(r"\[.*?,\s*%([-A-Za-z$._0-9]+)\s*\]", rhs)
        elif opcode in {"br", "switch"}:
            attrs["targets"] = re.findall(r"label\s+%([-A-Za-z$._0-9]+)", rhs)
        inst = IRInstruction(node_id, opcode, _result_type(rhs, opcode), line, block, operands, attrs)
        instructions.append(inst)
        blocks.setdefault(block, []).append(node_id)
    return arguments, instructions, blocks


def extract_output_slice(path: Path, function: str, output_argument_indices: tuple[int, ...] = (0,)) -> IRSlice:
    arguments, instructions, blocks = parse_function_ir(path, function)
    defs = {node.id: node for node in instructions}
    output_bases = {
        arguments[index]["id"] for index in output_argument_indices
        if 0 <= index < len(arguments)
    }
    if not output_bases and arguments:
        output_bases.add(arguments[0]["id"])

    def pointer_base(value: str, seen: set[str] | None = None) -> str:
        seen = set() if seen is None else seen
        if value in seen or value not in defs:
            return value
        seen.add(value)
        node = defs[value]
        if node.opcode in {"getelementptr", "bitcast", "addrspacecast"} and node.operands:
            return pointer_base(node.operands[0], seen)
        if node.opcode == "phi":
            bases = {pointer_base(op, set(seen)) for op in node.operands}
            return next(iter(bases)) if len(bases) == 1 else value
        return value

    roots = [n.id for n in instructions if n.opcode == "store" and pointer_base(str(n.attrs.get("pointer", ""))) in output_bases]
    needed = set(roots)
    work = list(roots)
    while work:
        current = defs[work.pop()]
        for operand in current.operands:
            if operand in defs and operand not in needed:
                needed.add(operand)
                work.append(operand)

    # Retain guards controlling output stores and their data dependencies.
    store_blocks = {defs[root].block for root in roots}
    for node in instructions:
        if node.opcode not in {"br", "switch"}:
            continue
        targets = set(node.attrs.get("targets", []))
        if targets & store_blocks or node.block in store_blocks:
            if node.id not in needed:
                needed.add(node.id)
                work.append(node.id)
    while work:
        current = defs[work.pop()]
        for operand in current.operands:
            if operand in defs and operand not in needed:
                needed.add(operand)
                work.append(operand)

    selected = [n for n in instructions if n.id in needed]
    edges: list[dict[str, str]] = []
    for node in selected:
        for operand in node.operands:
            if operand in needed:
                kind = "memory" if node.opcode in {"load", "store", "getelementptr"} else "data"
                if node.opcode == "phi":
                    kind = "dependence"
                edges.append({"src": operand, "dst": node.id, "kind": kind})
        if node.opcode in {"br", "switch"}:
            for target in node.attrs.get("targets", []):
                for target_node in blocks.get(target, []):
                    if target_node in needed:
                        edges.append({"src": node.id, "dst": target_node, "kind": "control"})

    float_phis = _loop_carried_phis(selected)
    opcodes = [n.opcode for n in selected]
    invariants = {
        "output_store_count": len(roots),
        "loop_carried_values": [n.id for n in float_phis],
        "loop_carried_dependence": bool(float_phis),
        "has_indirect_index": "urem" in opcodes or "srem" in opcodes,
        "guard_count": sum(op in {"br", "switch", "select"} for op in opcodes),
        "load_count": opcodes.count("load"),
        "store_count": opcodes.count("store"),
    }
    return IRSlice(function, arguments, selected, edges, roots, {k: [n for n in v if n in needed] for k, v in blocks.items()}, invariants)


def classify_slice(slice_: IRSlice) -> dict[str, Any]:
    opcodes = [n.opcode for n in slice_.nodes]
    float_phis = _loop_carried_phis(slice_.nodes)
    geps = [n for n in slice_.nodes if n.opcode == "getelementptr"]
    loads = [n for n in slice_.nodes if n.opcode == "load"]
    comparisons = [n for n in slice_.nodes if n.opcode == "fcmp"]
    constants = _float_constants(slice_.nodes)
    if "urem" in opcodes or "srem" in opcodes:
        return {"family": "indirect_memory", "canonical": "strided_indirect", "evidence": ["urem/srem index"]}
    if len(loads) >= 3 and len(geps) >= 3:
        return {"family": "stencil", "canonical": "neighborhood", "evidence": ["multiple affine neighbor loads"]}
    if float_phis:
        if ("fadd" in opcodes or _has_intrinsic(slice_.nodes, "llvm.fmuladd")) and "fmul" in opcodes:
            return {"family": "recurrence", "canonical": "iir", "evidence": ["floating phi", "fmul", "fadd"]}
        if "fcmp" in opcodes:
            return {"family": "scan", "canonical": "running_max", "evidence": ["floating phi", "fcmp"]}
        return {"family": "scan", "canonical": "prefix_sum", "evidence": ["floating phi"]}
    family = "guarded_pointwise_map" if comparisons or "select" in opcodes or len(slice_.roots) > 1 else "pointwise_map"
    fmuladd_count = sum("llvm.fmuladd" in n.text for n in slice_.nodes)
    if len(comparisons) >= 2 and len(slice_.roots) >= 3:
        canonical = "saturating_projection"
    elif "fdiv" in opcodes and "fneg" in opcodes:
        canonical = "conditional_pointwise"
    elif any(_constant_divisor(n.text) for n in slice_.nodes if n.opcode == "fdiv"):
        canonical = "div_const"
    elif comparisons:
        canonical = "conditional_pointwise"
    elif fmuladd_count == 1 or ("fadd" in opcodes and constants and "fdiv" not in opcodes) or ("fmul" in opcodes and constants and "fcmp" not in opcodes):
        canonical = "affine"
    elif "fneg" in opcodes and comparisons:
        canonical = "abs_preserve_negzero"
    else:
        canonical = "pointwise_expr"
    return {"family": family, "canonical": canonical, "evidence": sorted(set(opcodes)), "constants": constants}


def _opcode(rhs: str) -> str:
    words = rhs.split()
    if not words:
        return "unknown"
    first = words[0]
    if first in {"tail", "musttail", "notail"} and len(words) > 1:
        first = words[1]
    while first in {"nuw", "nsw", "exact", "fast"} and len(words) > 1:
        words = words[1:]
        first = words[0]
    return first


def _value_type(text: str) -> str:
    match = re.search(r"\b(ptr|i\d+|half|float|double|<[^>]+>)\b", text)
    return match.group(1) if match else "unknown"


def _result_type(rhs: str, opcode: str) -> str:
    if opcode in {"store", "br", "ret", "switch"}:
        return "void"
    if opcode in {"icmp", "fcmp"}:
        return "i1"
    return _value_type(rhs)


def _split_commas(text: str) -> list[str]:
    parts, start, depth = [], 0, 0
    for index, char in enumerate(text):
        depth += char in "([<{"
        depth -= char in ")]}>"
        if char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _last_value(text: str) -> str:
    values = re.findall(rf"{SSA}|[-+]?(?:\d+\.\d+e[+-]?\d+|\d+\.\d+|\d+|0x[0-9A-Fa-f]+)", text, re.IGNORECASE)
    return values[-1] if values else ""


def _matching_function_end(text: str, start: int) -> int:
    depth = 1
    for index in range(start, len(text)):
        depth += text[index] == "{"
        depth -= text[index] == "}"
        if depth == 0:
            return index
    raise ValueError("unterminated LLVM function")


def _float_constants(nodes: list[IRInstruction]) -> list[str]:
    found: set[str] = set()
    for node in nodes:
        found.update(re.findall(r"(?<![%\w])(?:[-+]?\d+\.\d+(?:e[+-]?\d+)?|0x[0-9A-Fa-f]{16})(?!\w)", node.text, re.IGNORECASE))
    return sorted(found)


def _has_neighbor_geps(geps: list[IRInstruction]) -> bool:
    index_defs = {tuple(n.attrs.get("indices", [])) for n in geps}
    return len(index_defs) >= 3


def _loop_carried_phis(nodes: list[IRInstruction]) -> list[IRInstruction]:
    defs = {node.id: node for node in nodes}

    def reaches(start: str, target: str, seen: set[str]) -> bool:
        if start == target:
            return True
        if start in seen or start not in defs:
            return False
        seen.add(start)
        return any(reaches(op, target, seen) for op in defs[start].operands)

    return [
        node for node in nodes
        if node.opcode == "phi"
        and node.type in {"float", "double", "half"}
        and any(reaches(op, node.id, set()) for op in node.operands)
    ]


def _has_intrinsic(nodes: list[IRInstruction], name: str) -> bool:
    return any(name in node.text for node in nodes)


def _constant_divisor(text: str) -> bool:
    match = re.search(r"fdiv(?:\s+\w+)*\s+float\s+[^,]+,\s+(.+)$", text)
    if not match:
        return False
    return not re.search(SSA, match.group(1))
