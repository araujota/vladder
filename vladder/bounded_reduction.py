from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess
from typing import Any

from z3 import Int, Solver, Sum, unsat

from .language_adapter import SemanticFlowEdge, SemanticFlowGraph, SemanticFlowNode


@dataclass(frozen=True)
class ReductionSchedule:
    factor: int
    accumulator_banks: int
    lane_offsets: tuple[int, ...]
    lane_banks: tuple[int, ...]
    scalar_tail: bool = True

    def __post_init__(self) -> None:
        if self.factor < 1 or self.accumulator_banks < 1:
            raise ValueError("factor and accumulator bank count must be positive")
        if sorted(self.lane_offsets) != list(range(self.factor)):
            raise ValueError("schedule must visit every lane exactly once")
        if len(self.lane_banks) != self.factor:
            raise ValueError("schedule must assign every lane to an accumulator bank")
        if any(bank < 0 or bank >= self.accumulator_banks for bank in self.lane_banks):
            raise ValueError("schedule references an unavailable accumulator bank")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def standard_count_schedules() -> tuple[tuple[str, ReductionSchedule], ...]:
    return (
        ("scalar", ReductionSchedule(1, 1, (0,), (0,))),
        ("unroll2", ReductionSchedule(2, 1, (0, 1), (0, 0))),
        ("unroll4", ReductionSchedule(4, 1, (0, 1, 2, 3), (0, 0, 0, 0))),
        ("unroll4_banks2", ReductionSchedule(4, 2, (0, 1, 2, 3), (0, 1, 0, 1))),
    )


def prove_count_schedule(
    schedule: ReductionSchedule,
    output_path: Path,
    *,
    proof_bound: int,
    candidate_id: str,
    source_sha256: str,
    language: str,
    panic_policy: str,
) -> dict[str, Any]:
    length = Int("length")
    quotient = length / schedule.factor
    remainder = length % schedule.factor
    structural = Solver()
    structural.add(length >= 0)
    structural.add(quotient * schedule.factor + remainder != length)
    structural_result = structural.check()
    obligations: list[dict[str, Any]] = []
    sections: list[str] = []
    for size in range(proof_bound + 1):
        indicators = [Int(f"eq_{size}_{index}") for index in range(size)]
        solver = Solver()
        for value in indicators:
            solver.add(value >= 0, value <= 1)
        baseline = Sum(indicators) if indicators else 0
        full = size // schedule.factor * schedule.factor
        visited = [
            base + offset
            for base in range(0, full, schedule.factor)
            for offset in schedule.lane_offsets
        ]
        visited.extend(range(full, size))
        banks: list[Any] = [0] * schedule.accumulator_banks
        for ordinal, index in enumerate(visited):
            bank = schedule.lane_banks[ordinal % schedule.factor] if ordinal < full else 0
            banks[bank] = banks[bank] + indicators[index]
        candidate = Sum(banks) if banks else 0
        solver.add(baseline != candidate)
        result = solver.check()
        obligations.append({
            "length": size,
            "status": "PROVED" if result == unsat else "FAILED",
            "visited_indices": visited,
            "counterexample": None if result == unsat else str(solver.model()),
        })
        sections.append(f"; length={size}\n{solver.to_smt2()}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(sections) + "\n")
    parametric = structural_result == unsat and schedule.scalar_tail
    passed = parametric and all(item["status"] == "PROVED" for item in obligations)
    return {
        "schema_version": "vladder-bounded-reduction-proof-v1",
        "status": "PASS" if passed else "FAIL",
        "proof_class": "parametric_exact_reduction_schedule_with_bounded_value_obligations",
        "source_language": language,
        "candidate": candidate_id,
        "operation": "count_equal_u8",
        "schedule": schedule.to_dict(),
        "bound_inclusive": proof_bound,
        "source_sha256": source_sha256,
        "panic_policy": panic_policy,
        "parametric_schedule_proof": {
            "status": "PROVED" if parametric else "FAILED",
            "domain": "all nonnegative valid input lengths",
            "partition": "length = floor(length/factor)*factor + remainder",
            "tail_covers_remainder": schedule.scalar_tail,
        },
        "obligations": obligations,
        "artifact": str(output_path),
    }


def count_equal_graph(
    *,
    name: str,
    language: str,
    compiler_identity: str,
    semantic_ir: str,
    function_identity: str,
    source_provenance: dict[str, Any],
    contracts: dict[str, Any],
    excluded_claims: tuple[str, ...],
) -> SemanticFlowGraph:
    def node(identifier: str, kind: str, operation: str, inputs: tuple[str, ...], output: str | None, obligations: tuple[str, ...] = ()) -> SemanticFlowNode:
        return SemanticFlowNode(identifier, kind, operation, inputs, output, {}, source_provenance, obligations)

    nodes = (
        node("bytes", "Input", "borrowed-byte-sequence", (), "u8[]", ("valid for region lifetime",)),
        node("needle", "Input", "comparison-value", (), "u8"),
        node("loop", "Loop", "iterate-valid-indices", ("bytes",), "index", ("bounds policy preserved",)),
        node("load", "Load", "load-u8", ("bytes", "loop"), "u8"),
        node("equal", "Compare", "equal-u8", ("load", "needle"), "bool"),
        node("reduce", "Reduce", "count-true", ("equal",), "usize", ("exact integer count",)),
        node("result", "Output", "return-count", ("reduce",), "usize"),
    )
    edges = (
        SemanticFlowEdge("e0", "bytes", "loop", "u8[]", "borrowed", "input", "region", "ordered"),
        SemanticFlowEdge("e1", "loop", "load", "index", "value", "index", "iteration", "ordered"),
        SemanticFlowEdge("e2", "bytes", "load", "u8[]", "borrowed", "input", "region", "ordered"),
        SemanticFlowEdge("e3", "load", "equal", "u8", "value", "lane", "iteration", "ordered"),
        SemanticFlowEdge("e4", "needle", "equal", "u8", "value", "needle", "region", "ordered"),
        SemanticFlowEdge("e5", "equal", "reduce", "bool", "value", "predicate", "iteration", "reduction"),
        SemanticFlowEdge("e6", "reduce", "result", "usize", "value", "result", "region", "ordered"),
    )
    return SemanticFlowGraph(
        name, language, compiler_identity, semantic_ir, function_identity,
        nodes, edges, contracts, excluded_claims,
    )


def prove_schedule_llvm(
    schedule: ReductionSchedule,
    output_path: Path,
    *,
    alive_tv: Path | None,
    bound: int,
    language: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Prove the source-derived schedule in canonical LLVM.

    This deliberately does not claim native frontend refinement. Native compiler IR is retained as
    separate provenance; the Z3 theorem binds source to schedule and this check validates the shared
    schedule-to-LLVM lowerer over a fixed symbolic value vector.
    """
    width = max(1, min(bound, 4))
    args = ", ".join(f"i1 %p{index}" for index in range(width))

    def body(order: list[int], banks: list[int]) -> str:
        lines = [f"  %v{index} = zext i1 %p{index} to i64" for index in range(width)]
        bank_values: list[str | None] = [None] * max(1, schedule.accumulator_banks if banks else 1)
        ordinal = 0
        for index in order:
            bank = banks[ordinal] if banks else 0
            current = bank_values[bank]
            if current is None:
                bank_values[bank] = f"%v{index}"
            else:
                name = f"%a{ordinal}"
                lines.append(f"  {name} = add i64 {current}, %v{index}")
                bank_values[bank] = name
            ordinal += 1
        values = [value for value in bank_values if value is not None]
        current = values[0]
        for index, value in enumerate(values[1:]):
            name = f"%r{index}"
            lines.append(f"  {name} = add i64 {current}, {value}")
            current = name
        lines.append(f"  ret i64 {current}")
        return "\n".join(lines)

    full = width // schedule.factor * schedule.factor
    candidate_order = [base + offset for base in range(0, full, schedule.factor) for offset in schedule.lane_offsets]
    candidate_order.extend(range(full, width))
    candidate_banks = [schedule.lane_banks[i % schedule.factor] if i < full else 0 for i in range(width)]
    source = (
        f"define i64 @src({args}) {{\nentry:\n{body(list(range(width)), [])}\n}}\n\n"
        f"define i64 @tgt({args}) {{\nentry:\n{body(candidate_order, candidate_banks)}\n}}\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source)
    if alive_tv is None or not alive_tv.exists():
        return {"status": "UNAVAILABLE", "reason": "alive-tv is unavailable", "artifact": str(output_path)}
    command = [str(alive_tv), "--bidirectional", "--always-verify", "--smt-to=60000", str(output_path)]
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except subprocess.TimeoutExpired as error:
        return {
            "status": "TIMEOUT", "proof_class": "source-derived-schedule canonical LLVM refinement",
            "source_language": language, "source_sha256": source_sha256, "bound": width,
            "schedule": schedule.to_dict(), "command": command, "stdout": error.stdout or "",
            "stderr": error.stderr or "", "artifact": str(output_path),
        }
    combined = result.stdout + result.stderr
    passed = result.returncode == 0 and "Transformation seems to be correct" in combined and "ERROR" not in combined
    return {
        "status": "PASS" if passed else "FAIL",
        "proof_class": "source-derived-schedule canonical LLVM refinement",
        "source_language": language,
        "source_sha256": source_sha256,
        "bound": width,
        "schedule": schedule.to_dict(),
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "artifact": str(output_path),
        "claim_boundary": "validates the shared schedule LLVM lowerer; native frontend LLVM is separate provenance",
    }
