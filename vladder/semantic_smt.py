from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .c_lift import CExpr, graph_ast
from .flow import FlowGraph


@dataclass(frozen=True)
class SemanticSMT:
    status: str
    logic: str
    lanes: int
    model: str
    path: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "logic": self.logic,
            "lanes": self.lanes,
            "model": self.model,
            "path": self.path,
            "reason": self.reason,
        }


def emit_semantic_smt(graph: FlowGraph, path: Path, lanes: int = 4) -> SemanticSMT:
    path.parent.mkdir(parents=True, exist_ok=True)
    ast = graph_ast(graph)
    if ast is None:
        path.write_text(f"; unsupported semantic SMT encoding for {graph.family}/{graph.canonical}\n")
        return SemanticSMT("unsupported", "QF_AUFBVFP", lanes, "bounded-array", str(path), "no exact graph AST encoder for this family")
    try:
        import z3
    except Exception:
        path.write_text("; z3 unavailable\n")
        return SemanticSMT("unsupported", "QF_AUFBVFP", lanes, "bounded-array", str(path), "z3 unavailable")
    fp = z3.Float32()
    src = z3.Array("src", z3.BitVecSort(64), fp)
    dst = z3.Array("dst_after", z3.BitVecSort(64), fp)
    solver = z3.Solver()
    for lane in range(lanes):
        index = z3.BitVecVal(lane, 64)
        x = z3.Select(src, index)
        value = _to_z3(ast.expression, x, z3)
        solver.add(z3.Select(dst, index) == value)
    header = [
        "; vLadder bounded information-flow semantics",
        f"; family: {graph.family}",
        f"; canonical: {graph.canonical}",
        f"; unrolled lanes: {lanes}",
        "; This is a semantic relation, not an equivalence claim about a proposed implementation.",
    ]
    path.write_text("\n".join(header) + "\n" + solver.to_smt2())
    return SemanticSMT("encoded", "QF_AUFBVFP", lanes, "bounded-array", str(path))


def _to_z3(expr: CExpr, x: Any, z3: Any) -> Any:
    if expr.op == "atom":
        if expr.value == "x":
            return x
        return z3.FPVal(float(expr.value.rstrip("fF")), z3.Float32())
    if expr.op == "neg":
        return z3.fpNeg(_to_z3(expr.args[0], x, z3))
    if expr.op == "select":
        return z3.If(_to_z3(expr.args[0], x, z3), _to_z3(expr.args[1], x, z3), _to_z3(expr.args[2], x, z3))
    left = _to_z3(expr.args[0], x, z3)
    right = _to_z3(expr.args[1], x, z3)
    if expr.op == "+":
        return z3.fpAdd(z3.RNE(), left, right)
    if expr.op == "-":
        return z3.fpSub(z3.RNE(), left, right)
    if expr.op == "*":
        return z3.fpMul(z3.RNE(), left, right)
    if expr.op == "/":
        return z3.fpDiv(z3.RNE(), left, right)
    if expr.op == "<":
        return z3.fpLT(left, right)
    if expr.op == ">":
        return z3.fpGT(left, right)
    if expr.op == "<=":
        return z3.fpLEQ(left, right)
    if expr.op == ">=":
        return z3.fpGEQ(left, right)
    raise ValueError(f"unsupported SMT expression opcode {expr.op}")
