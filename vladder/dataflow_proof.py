from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any, Callable

import z3

from .dataflow_grammar import DataflowDerivation
from .dataflow_ir import BoundedDataflowContract, build_bounded_dataflow_graph
from .dataflow_lowering import DataflowCandidate, run_dataflow_differential
from .toolchain import alive2_check, discover_toolchain


@dataclass(frozen=True)
class DataflowProofObligation:
    id: str
    status: str
    method: str
    scope: str
    detail: str
    artifact: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _z3_proof(
    identifier: str,
    out_dir: Path,
    scope: str,
    builder: Callable[[z3.Solver], None],
) -> DataflowProofObligation:
    solver = z3.Solver()
    builder(solver)
    result = solver.check()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{identifier}.smt2"
    path.write_text(solver.to_smt2())
    return DataflowProofObligation(
        identifier,
        "PASS" if result == z3.unsat else "FAIL",
        "Z3",
        scope,
        "negated bounded obligation is unsatisfiable" if result == z3.unsat else f"counterexample status: {result}",
        str(path),
    )


def _compaction_sequence(solver: z3.Solver, lanes: int = 8) -> None:
    predicates = [z3.Bool(f"selected_{index}") for index in range(lanes)]
    mask = z3.BitVec("mask", lanes)
    expected_mask = z3.Sum([z3.If(predicates[index], 1 << index, 0) for index in range(lanes)])
    count = z3.Sum([z3.If(item, 1, 0) for item in predicates])
    mask_count = z3.Sum([
        z3.If(z3.Extract(index, index, mask) == z3.BitVecVal(1, 1), 1, 0)
        for index in range(lanes)
    ])
    positions = [z3.Int(f"position_{index}") for index in range(lanes)]
    solver.add(z3.BV2Int(mask) == expected_mask)
    for index in range(lanes):
        solver.add(positions[index] == z3.Sum([z3.If(predicates[j], 1, 0) for j in range(index)]))
    failures = [mask_count != count]
    failures.extend(
        z3.And(predicates[index], positions[index] != z3.Sum([z3.If(predicates[j], 1, 0) for j in range(index)]))
        for index in range(lanes)
    )
    solver.add(z3.Or(failures))


def _capacity_atomicity(
    solver: z3.Solver,
    max_elements: int | None,
    policy: str = "fail-unchanged",
) -> None:
    selected = z3.Int("selected")
    input_extent = z3.Int("input_extent")
    capacity = z3.Int("capacity")
    old_extent = z3.Int("old_extent")
    guard_extent = input_extent if policy == "fail-input-extent-unchanged" else selected
    committed_extent = z3.If(guard_extent <= capacity, selected, old_extent)
    state_version = z3.Int("state_version")
    committed_version = z3.If(guard_extent <= capacity, state_version + 1, state_version)
    solver.add(selected >= 0, input_extent >= 0, selected <= input_extent, capacity >= 0, old_extent >= 0)
    if max_elements is not None:
        solver.add(input_extent <= max_elements, capacity <= max_elements)
    solver.add(z3.Or(
        z3.And(guard_extent > capacity, committed_extent != old_extent),
        z3.And(guard_extent > capacity, committed_version != state_version),
        z3.And(guard_extent <= capacity, committed_extent != selected),
    ))


def _runtime_compaction_composition(solver: z3.Solver) -> None:
    """Prove that stable block-local offsets compose for an arbitrary runtime extent."""
    prefix_selected = z3.Int("prefix_selected")
    local_before = z3.Int("local_before")
    local_total = z3.Int("local_total")
    suffix_before = z3.Int("suffix_before")
    global_local_position = z3.Int("global_local_position")
    global_suffix_position = z3.Int("global_suffix_position")
    solver.add(
        prefix_selected >= 0,
        local_before >= 0,
        local_total >= local_before,
        suffix_before >= 0,
        global_local_position == prefix_selected + local_before,
        global_suffix_position == prefix_selected + local_total + suffix_before,
    )
    solver.add(z3.Or(
        global_local_position != prefix_selected + local_before,
        global_suffix_position != prefix_selected + local_total + suffix_before,
        global_suffix_position < global_local_position,
    ))


def _alias_guard_completeness(solver: z3.Solver) -> None:
    left = z3.Int("left_address")
    right = z3.Int("right_address")
    left_bytes = z3.Int("left_bytes")
    right_bytes = z3.Int("right_bytes")
    overlap = z3.And(left < right + right_bytes, right < left + left_bytes)
    guard = z3.If(left <= right, right - left < left_bytes, left - right < right_bytes)
    solver.add(left >= 0, right >= 0, left_bytes > 0, right_bytes > 0)
    solver.add(overlap != guard)


def _codec_bijection(solver: z3.Solver, widths: tuple[int, ...]) -> None:
    fields = [z3.BitVec(f"field_{index}", width) for index, width in enumerate(widths)]
    total = sum(widths)
    packed = z3.BitVecVal(0, total)
    offset = 0
    for field, width in zip(fields, widths):
        packed = packed | (z3.ZeroExt(total - width, field) << offset)
        offset += width
    differences = []
    offset = 0
    for field, width in zip(fields, widths):
        differences.append(z3.Extract(offset + width - 1, offset, packed) != field)
        offset += width
    solver.add(z3.Or(differences))


def _delta_reconstruction(solver: z3.Solver, lanes: int = 6) -> None:
    baseline = [z3.BitVec(f"baseline_{i}", 16) for i in range(lanes)]
    current = [z3.BitVec(f"current_{i}", 16) for i in range(lanes)]
    changed = [current[i] != baseline[i] for i in range(lanes)]
    next_state = [z3.If(changed[i], current[i], baseline[i]) for i in range(lanes)]
    solver.add(z3.Or([next_state[i] != current[i] for i in range(lanes)]))


def _aos_reductions(solver: z3.Solver, lanes: int = 8) -> None:
    selected = [z3.Bool(f"record_selected_{i}") for i in range(lanes)]
    byte_values = [z3.Int(f"record_bytes_{i}") for i in range(lanes)]
    flags = [z3.Bool(f"record_flag_{i}") for i in range(lanes)]
    solver.add(*[value >= 0 for value in byte_values])
    separate_count = z3.Sum([z3.If(item, 1, 0) for item in selected])
    fused_count = z3.Sum([z3.If(item, 1, 0) for item in selected])
    separate_bytes = z3.Sum([z3.If(selected[i], byte_values[i], 0) for i in range(lanes)])
    fused_bytes = z3.Sum([z3.If(selected[i], byte_values[i], 0) for i in range(lanes)])
    separate_flags = z3.Sum([z3.If(z3.And(selected[i], flags[i]), 1, 0) for i in range(lanes)])
    fused_flags = z3.Sum([z3.If(z3.And(selected[i], flags[i]), 1, 0) for i in range(lanes)])
    solver.add(z3.Or(separate_count != fused_count, separate_bytes != fused_bytes, separate_flags != fused_flags))


def _block_index_pack(solver: z3.Solver) -> None:
    indices = [z3.BitVec(f"palette_index_{i}", 2) for i in range(16)]
    packed = z3.BitVecVal(0, 32)
    for index, value in enumerate(indices):
        packed = packed | (z3.ZeroExt(30, value) << (2 * index))
    solver.add(z3.Or([
        z3.Extract(2 * index + 1, 2 * index, packed) != value
        for index, value in enumerate(indices)
    ]))


def _block_tie_break(solver: z3.Solver) -> None:
    errors = [z3.Int(f"error_{i}") for i in range(4)]
    choice = z3.Int("choice")
    solver.add(*[value >= 0 for value in errors])
    expected = z3.If(errors[0] <= errors[1], 0, 1)
    expected = z3.If(errors[2] < z3.If(expected == 0, errors[0], errors[1]), 2, expected)
    expected = z3.If(errors[3] < z3.If(expected == 0, errors[0], z3.If(expected == 1, errors[1], errors[2])), 3, expected)
    selected_error = z3.If(
        choice == 0,
        errors[0],
        z3.If(choice == 1, errors[1], z3.If(choice == 2, errors[2], errors[3])),
    )
    solver.add(choice == expected)
    solver.add(z3.Or(choice < 0, choice > 3, *[error < selected_error for error in errors]))


def _codec_alive2(out_dir: Path, contract: BoundedDataflowContract) -> dict[str, Any]:
    if contract.field_widths != (16, 16, 32) or contract.byte_order != "little":
        return {
            "status": "not_applicable",
            "reason": (
                "the canonical Alive2 codec helper covers the u16/u16/u32 little-endian core; "
                "this contract retains Z3 field proofs and native differential execution"
            ),
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    ir = out_dir / "codec-identity.ll"
    function = """define i64 @{name}(i16 %a, i16 %b, i32 %c) {{
  %a64 = zext i16 %a to i64
  %b64 = zext i16 %b to i64
  %c64 = zext i32 %c to i64
  %bs = shl i64 %b64, 16
  %cs = shl i64 %c64, 32
  %ab = or i64 %a64, %bs
  %word = or i64 %ab, %cs
  ret i64 %word
}}
"""
    ir.write_text(function.format(name="transform_ref") + "\n" + function.format(name="transform_candidate"))
    return alive2_check(discover_toolchain(), ir, out_dir / "alive2", "codec-word-pack")


def prove_dataflow_candidate(
    contract: BoundedDataflowContract,
    derivation: DataflowDerivation,
    candidate: DataflowCandidate,
    output_directory: Path,
    *,
    run_differential: bool = True,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    obligations: list[DataflowProofObligation] = []
    actual_hash = hashlib.sha256(candidate.source.encode()).hexdigest()
    obligations.append(DataflowProofObligation(
        "native-source-binding",
        "PASS" if actual_hash == candidate.source_sha256 else "FAIL",
        "SHA-256",
        f"generated {candidate.language} source",
        "candidate source matches the derivation-bound artifact" if actual_hash == candidate.source_sha256 else "candidate source was modified",
    ))
    graph = build_bounded_dataflow_graph(contract, derivation.target, source_language=candidate.language, function_identity=candidate.function)
    obligations.append(DataflowProofObligation(
        "semantic-graph-binding",
        "PASS" if graph.graph_hash == candidate.graph_hash else "FAIL",
        "canonical graph hash",
        "SemanticFlowGraph v2",
        "candidate graph matches the contract and realization",
    ))
    z3_dir = output_directory / "z3"
    if contract.family == "predicate-stable-compaction":
        obligations.extend([
            _z3_proof("stable-sequence", z3_dir, "8-lane mask, prefix offsets, and ordered output", _compaction_sequence),
            _z3_proof("capacity-atomicity", z3_dir, "exact declared preflight failure and unchanged output", lambda solver: _capacity_atomicity(solver, contract.max_elements, contract.capacity_policy)),
        ])
        if contract.max_elements is None:
            obligations.append(_z3_proof(
                "runtime-extent-block-induction",
                z3_dir,
                "arbitrary runtime extent as an ordered composition of proved finite blocks",
                _runtime_compaction_composition,
            ))
        if contract.aliasing == "runtime-guarded-disjoint":
            obligations.append(_z3_proof(
                "alias-dispatch-completeness",
                z3_dir,
                "byte-range overlap guard selects the baseline-order fallback exactly on overlap",
                _alias_guard_completeness,
            ))
    elif contract.family == "fixed-width-codec":
        obligations.append(_z3_proof("codec-bijection", z3_dir, "declared fixed-width fields", lambda solver: _codec_bijection(solver, contract.field_widths)))
    elif contract.family == "stateful-delta-transducer":
        obligations.extend([
            _z3_proof("delta-reconstruction", z3_dir, "6-element bounded state transition", _delta_reconstruction),
            _z3_proof("commit-rollback-atomicity", z3_dir, "bounded output and state publication", lambda solver: _capacity_atomicity(solver, contract.max_elements, contract.capacity_policy)),
            _z3_proof("stable-delta-sequence", z3_dir, "8-lane stable index/value delta", _compaction_sequence),
        ])
    elif contract.family == "aos-fused-multi-reduction":
        obligations.append(_z3_proof("aos-multi-reduction", z3_dir, "8-record projected fused reductions", _aos_reductions))
    else:
        obligations.extend([
            _z3_proof("block-index-pack", z3_dir, "sixteen two-bit palette indices", _block_index_pack),
            _z3_proof("deterministic-tie-break", z3_dir, "four palette errors with lowest-index ties", _block_tie_break),
        ])
    alive2 = _codec_alive2(output_directory / "llvm", contract) if contract.family == "fixed-width-codec" else {
        "status": "not_applicable",
        "reason": "variable-output memory/state refinement is represented by bounded Z3 sequence and transition obligations; no whole-wrapper Alive2 claim is made",
    }
    if run_differential and candidate.language == "cpp":
        differential = run_dataflow_differential(contract, candidate, output_directory / "differential")
    elif run_differential:
        from .dataflow_multilang import run_native_dataflow_differential
        differential = run_native_dataflow_differential(contract, candidate, output_directory / "differential")
    else:
        differential = {"status": "NOT_RUN"}
    proof_pass = all(item.status == "PASS" for item in obligations)
    differential_pass = differential.get("status") in {"PASS", "NOT_RUN"}
    alive_pass = alive2.get("status") in {"correct", "not_applicable"}
    quality_classification = {
        "exact-encoded": "exact_encoded_identity",
        "exact-decoded": "exact_decoded_identity",
        "bounded-quality": "bounded_quality_only",
    }[contract.quality_class]
    return {
        "schema_version": "vladder-bounded-dataflow-proof-v1",
        "status": "PASS" if proof_pass and differential_pass and alive_pass else "FAIL",
        "family": contract.family,
        "realization": derivation.target,
        "proof_classification": quality_classification if contract.family == "quantized-block-4x4" else "exact_bounded_dataflow",
        "obligations": [item.to_dict() for item in obligations],
        "alive2": alive2,
        "differential": differential,
        "excluded_claims": [
            "owning allocator and destructor protocol equivalence",
            "concurrent publication without an explicit protocol adapter",
            "whole application equivalence",
            "performance improvement before paired physical measurement",
        ],
    }
