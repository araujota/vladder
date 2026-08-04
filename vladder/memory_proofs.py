from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .candidates import Candidate
from .flow import FlowGraph


@dataclass(frozen=True)
class MemoryProof:
    status: str
    method: str
    obligations: list[str]
    preconditions: list[str]
    footprint: dict[str, Any]
    solver_result: str
    smt2: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("smt2")
        return data


def prove_memory_safety(graph: FlowGraph, candidate: Candidate, assume_no_alias: bool) -> MemoryProof:
    try:
        import z3
    except Exception:
        return MemoryProof("unsupported", "z3-int", [], [], {}, "z3 unavailable")

    n, i, src, dst = z3.Ints("n i src_base dst_base")
    max_addr = 2**64 - 1
    common = [n >= 0, i >= 0, i < n, src >= 0, dst >= 0, src <= max_addr - 4 * n, dst <= max_addr - 4 * n]
    obligations = ["all computed accesses are inside their declared float-array footprint", "pointer arithmetic does not wrap a 64-bit address space"]
    preconditions = ["src and dst each designate at least n readable/writable float elements"]
    indices = [i]
    footprint: dict[str, Any] = {"writes": "dst[0:n]", "reads": "src[0:n]", "access": graph.family}
    if graph.family == "stencil":
        radius = max(abs(int(x)) for x in graph.source_pattern.get("neighbor_offsets", [0]))
        interior = z3.And(i >= radius, i + radius < n)
        for offset in range(-radius, radius + 1):
            indices.append(z3.If(interior, i + offset, i))
        footprint["neighbor_radius"] = radius
        obligations.append("boundary iterations use src[i]; interior neighbor offsets remain in [0,n)")
    elif graph.family == "indirect_memory":
        stride = graph.source_pattern.get("indirect_stride")
        if not isinstance(stride, int) or stride < 0:
            return MemoryProof(
                "unsupported",
                "z3-unbounded-integer-address-model",
                obligations,
                preconditions,
                footprint,
                "indirect stride is outside the admitted proof model",
            )
        j = z3.Int("j")
        common.extend([n > 0, j == (i * stride) % n])
        indices.append(j)
        footprint["indirect_index"] = f"(i * {stride}) % n"
        obligations.append("modulo-derived source index is in [0,n) for n>0")

    if candidate.requires_no_alias:
        preconditions.append("src[0:n] and dst[0:n] are disjoint")
        common.append(z3.Or(dst + 4 * n <= src, src + 4 * n <= dst))
        obligations.append("restrict/vector loads cannot overlap output stores")
    elif assume_no_alias:
        preconditions.append("run-level no-alias contract is active")

    bad = []
    for index in indices:
        bad.append(z3.Or(index < 0, index >= n, src + 4 * index < src, src + 4 * index + 3 >= src + 4 * n))
    bad.append(z3.Or(dst + 4 * i < dst, dst + 4 * i + 3 >= dst + 4 * n))
    solver = z3.Solver()
    solver.add(*common, z3.Or(*bad))
    result = solver.check()
    return MemoryProof(
        "proved" if result == z3.unsat else "failed",
        "z3-unbounded-integer-address-model",
        obligations,
        preconditions,
        footprint,
        str(result),
        solver.to_smt2(),
    )
