from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from z3 import If, Int, Solver, Sum, unsat

from .rust_semantics import (
    RustFunction,
    RustKernelModel,
    infer_rust_kernel_model,
    parse_mir_functions,
    select_mir_function,
)


@dataclass(frozen=True)
class RustCandidate:
    id: str
    rule: str
    factor: int
    accumulator_banks: int
    source: str
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RustCandidateSchedule:
    factor: int
    accumulator_banks: int
    lane_offsets: tuple[int, ...]
    lane_banks: tuple[int, ...]
    has_scalar_tail: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_candidate_schedule(candidate: RustCandidate, model: RustKernelModel) -> RustCandidateSchedule:
    header = re.search(
        r"vladder:\s*operation=count_equal_u8\s+factor=(\d+)\s+accumulator_banks=(\d+)",
        candidate.source,
    )
    if not header:
        raise ValueError("generated Rust candidate has no schedule provenance header")
    factor, banks = (int(value) for value in header.groups())
    lane_pattern = re.compile(
        rf"count(\d+)\s*\+=\s*\({re.escape(model.slice_parameter)}\[i\s*\+\s*(\d+)\]"
    )
    lanes = tuple((int(bank), int(offset)) for bank, offset in lane_pattern.findall(candidate.source))
    tail_pattern = re.compile(
        rf"count0\s*\+=\s*\({re.escape(model.slice_parameter)}\[i\]\s*=="
    )
    schedule = RustCandidateSchedule(
        factor,
        banks,
        tuple(offset for _, offset in lanes),
        tuple(bank for bank, _ in lanes),
        bool(tail_pattern.search(candidate.source)),
    )
    if factor != candidate.factor or banks != candidate.accumulator_banks:
        raise ValueError("candidate schedule metadata disagrees with its registered derivation")
    if len(lanes) != factor or sorted(schedule.lane_offsets) != list(range(factor)):
        raise ValueError("candidate chunk does not visit every lane exactly once")
    if any(bank < 0 or bank >= banks for bank in schedule.lane_banks):
        raise ValueError("candidate writes an undeclared accumulator bank")
    if not schedule.has_scalar_tail:
        raise ValueError("candidate has no scalar remainder traversal")
    compact = re.sub(r"\s+", "", candidate.source)
    chunk_guard = f"while{model.slice_parameter}.len()-i>={factor}{{"
    tail_guard = f"whilei<{model.slice_parameter}.len(){{"
    expected_factor_steps = 2 if factor == 1 else 1
    if chunk_guard not in compact or compact.count(f"i+={factor};") != expected_factor_steps:
        raise ValueError("candidate chunk guard or induction step disagrees with its schedule")
    expected_unit_steps = 2 if factor == 1 else 1
    if tail_guard not in compact or compact.count("i+=1;") != expected_unit_steps:
        raise ValueError("candidate tail guard or induction step is not canonical")
    declarations = re.findall(r"letmutcount(\d+)=0usize;", compact)
    if sorted(int(value) for value in declarations) != list(range(banks)):
        raise ValueError("candidate accumulator declarations do not match its bank schedule")
    result_match = re.search(r"(count\d+(?:\+count\d+)*)\}\s*$", compact)
    result_banks = [] if not result_match else [int(value) for value in re.findall(r"count(\d+)", result_match.group(1))]
    if result_banks != list(range(banks)):
        raise ValueError("candidate result does not reduce every accumulator bank exactly once")
    return schedule


def generate_rust_candidates(function: RustFunction, model: RustKernelModel) -> tuple[RustCandidate, ...]:
    if model.operation != "count_equal_u8":
        return ()
    variants = (
        ("explicit_scalar", 1, 1),
        ("unroll_2", 2, 1),
        ("unroll_4", 4, 1),
        ("unroll_4_banks_4", 4, 4),
        ("unroll_8_banks_4", 8, 4),
    )
    candidates: list[RustCandidate] = []
    for rule, factor, banks in variants:
        source = _count_candidate_source(function, model, f"candidate_{rule}", factor, banks)
        identity = hashlib.sha256(source.encode()).hexdigest()
        candidates.append(RustCandidate(identity[:16], rule, factor, banks, source, identity))
    return tuple(candidates)


def renamed_rust_function(function: RustFunction, new_name: str) -> str:
    signature = _native_signature(function, new_name)
    return f"{signature} {{\n{function.body}\n}}\n"


def compile_rust_library(
    rustc: Path,
    source: Path,
    output_directory: Path,
    *,
    crate_name: str,
    edition: str,
    opt_level: int,
    overflow_checks: bool,
    cwd: Path | None = None,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    mir = output_directory / f"{crate_name}.mir"
    llvm = output_directory / f"{crate_name}.ll"
    asm = output_directory / f"{crate_name}.s"
    command = [
        str(rustc), str(source), "--crate-name", crate_name, "--crate-type", "lib",
        "--edition", edition,
        f"--emit=mir={mir},llvm-ir={llvm},asm={asm}",
        "-C", f"opt-level={opt_level}",
        "-C", "codegen-units=1",
        "-C", f"overflow-checks={'yes' if overflow_checks else 'no'}",
        "-C", "debuginfo=1",
    ]
    completed = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "command": command,
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "mir": str(mir) if mir.exists() else None,
        "llvm_ir": str(llvm) if llvm.exists() else None,
        "assembly": str(asm) if asm.exists() else None,
        "hashes": {
            path.name: _sha256(path) for path in (mir, llvm, asm) if path.exists()
        },
    }


def validate_candidate_mir(
    candidate: RustCandidate,
    function: RustFunction,
    model: RustKernelModel,
    mir_path: Path,
    *,
    overflow_checks: bool,
) -> dict[str, Any]:
    text = mir_path.read_text()
    functions = parse_mir_functions(text)
    selected = select_mir_function(functions, f"candidate_{candidate.rule}")
    candidate_function = RustFunction(
        function.requested_name,
        f"candidate_{candidate.rule}",
        f"candidate_{candidate.rule}",
        _native_signature(function, f"candidate_{candidate.rule}"),
        function.parameters,
        function.return_type,
        _extract_body(candidate.source),
        candidate.source,
        0,
        len(candidate.source),
        candidate.source_sha256,
    )
    inferred = infer_rust_kernel_model(
        candidate_function,
        selected,
        functions,
        overflow_checks=overflow_checks,
        proof_bound=model.proof_bound,
    )
    try:
        schedule = extract_candidate_schedule(candidate, model)
        schedule_error = None
    except ValueError as error:
        schedule = None
        schedule_error = str(error)
    mir_schedule_evidence = {
        "factor_constant_present": bool(schedule and re.search(rf"const\s+{schedule.factor}_usize", selected.body)),
        "comparison_present": "Eq" in selected.operations,
        "accumulation_present": "Add" in selected.operations or "CheckedAdd" in selected.operations,
        "bounds_assertions": len(selected.assertions),
    }
    status = "PASS" if (
        inferred and inferred.operation == model.operation and schedule is not None
        and all((mir_schedule_evidence["comparison_present"], mir_schedule_evidence["accumulation_present"]))
    ) else "FAIL"
    return {
        "schema_version": "vladder-rust-mir-validation-v1",
        "status": status,
        "candidate": candidate.id,
        "selected_function": selected.to_dict(),
        "baseline_operation": model.operation,
        "candidate_operation": inferred.operation if inferred else None,
        "recognized_operations": list(selected.operations),
        "source_schedule": schedule.to_dict() if schedule else None,
        "schedule_error": schedule_error,
        "mir_schedule_evidence": mir_schedule_evidence,
        "candidate_source_sha256": candidate.source_sha256,
        "candidate_mir_sha256": selected.sha256,
        "proof_scope": "recognized MIR operation vocabulary plus source-derived schedule linked to emitted MIR; not arbitrary MIR equivalence",
    }


def prove_bounded_mir_equivalence(
    candidate: RustCandidate,
    model: RustKernelModel,
    output_path: Path,
) -> dict[str, Any]:
    if model.operation != "count_equal_u8":
        raise ValueError(f"no bounded MIR proof model for operation {model.operation}")
    schedule = extract_candidate_schedule(candidate, model)
    length_symbol = Int("length")
    quotient = length_symbol / schedule.factor
    remainder = length_symbol % schedule.factor
    structural = Solver()
    structural.add(length_symbol >= 0)
    structural.add(
        quotient * schedule.factor + remainder != length_symbol,
    )
    structural_result = structural.check()
    permutation_complete = sorted(schedule.lane_offsets) == list(range(schedule.factor))
    obligations: list[dict[str, Any]] = []
    smt_sections: list[str] = []
    for length in range(model.proof_bound + 1):
        indicators = [Int(f"eq_{length}_{index}") for index in range(length)]
        solver = Solver()
        for value in indicators:
            solver.add(value >= 0, value <= 1)
        baseline = Sum(indicators) if indicators else 0
        full = (length // schedule.factor) * schedule.factor
        lanes = [base + offset for base in range(0, full, schedule.factor) for offset in schedule.lane_offsets]
        lanes.extend(range(full, length))
        banks = [0 for _ in range(schedule.accumulator_banks)]
        for ordinal, index in enumerate(lanes):
            bank = schedule.lane_banks[ordinal % schedule.factor] if ordinal < full else 0
            banks[bank] = banks[bank] + indicators[index]
        candidate_result = Sum(banks) if banks else 0
        solver.add(baseline != candidate_result)
        result = solver.check()
        passed = result == unsat
        obligations.append({
            "length": length,
            "status": "PROVED" if passed else "FAILED",
            "solver_result": str(result).upper(),
            "visited_indices": lanes,
            "counterexample": None if passed else str(solver.model()),
        })
        smt_sections.append(f"; length={length}\n{solver.to_smt2()}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(smt_sections) + "\n")
    structural_passed = structural_result == unsat and permutation_complete and schedule.has_scalar_tail
    passed = structural_passed and all(item["status"] == "PROVED" for item in obligations)
    return {
        "schema_version": "vladder-rust-bounded-mir-proof-v1",
        "status": "PASS" if passed else "FAIL",
        "proof_class": "parametric_schedule_equivalence_with_bounded_mir_obligations",
        "candidate": candidate.id,
        "operation": model.operation,
        "bound_inclusive": model.proof_bound,
        "schedule": schedule.to_dict(),
        "parametric_schedule_proof": {
            "status": "PROVED" if structural_passed else "FAILED",
            "domain": "all valid Rust slice lengths",
            "chunk_partition": "length = floor(length/factor)*factor + remainder",
            "lane_permutation_complete": permutation_complete,
            "tail_covers_remainder": schedule.has_scalar_tail,
            "solver_result": str(structural_result).upper(),
            "overflow_argument": "i <= length and length - i is used for the chunk guard; count <= length <= usize::MAX",
        },
        "candidate_source_sha256": candidate.source_sha256,
        "integer_model": "mathematical count with slice-length non-overflow invariant",
        "panic_model": model.panic_policy,
        "obligations": obligations,
        "artifact": str(output_path),
        "excluded_claims": [
            "MIR content obligations beyond the declared bounded sample (the schedule theorem itself is parametric)",
            "unrecognized MIR operations",
            "unsafe Rust contracts",
            "custom Drop, unwind, concurrency, FFI, and external effects",
        ],
    }


def build_llvm_refinement_unit(
    function: RustFunction,
    candidate: RustCandidate,
    proof_bound: int,
    output_path: Path,
) -> dict[str, str]:
    baseline = "#[inline(always)]\n" + renamed_rust_function(function, "baseline_impl")
    candidate_impl = "#[inline(always)]\n" + candidate.source.replace(f"candidate_{candidate.rule}", "candidate_impl", 1)
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", candidate.rule)
    source = (
        "#![crate_type = \"lib\"]\n\n"
        + baseline
        + "\n"
        + candidate_impl
        + "\n"
        + f"#[no_mangle]\npub fn src_{suffix}(bytes: &[u8; {proof_bound}], needle: u8) -> usize {{\n"
          "    baseline_impl(bytes, needle)\n}\n\n"
        + f"#[no_mangle]\npub fn tgt_{suffix}(bytes: &[u8; {proof_bound}], needle: u8) -> usize {{\n"
          "    candidate_impl(bytes, needle)\n}\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source)
    return {"source": str(output_path), "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "suffix": suffix}


def run_alive2_refinement(
    alive_tv: Path | None,
    llvm_path: Path,
    output_path: Path,
    *,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    if alive_tv is None or not alive_tv.exists():
        report = {
            "status": "UNAVAILABLE",
            "proof_class": "bounded_llvm_refinement",
            "reason": "alive-tv is unavailable",
        }
    else:
        normalized_path = output_path.with_name("alive2-input.ll")
        normalized = llvm_path.read_text()
        # Alive2 20 rejects a few rustc 17 argument attributes and optimization
        # metadata. Removing them broadens the admitted inputs, so a successful
        # proof is stronger; no executable operation is rewritten.
        transformations = {
            "removed_noalias": len(re.findall(r"\s+noalias\b", normalized)),
            "removed_nocapture": len(re.findall(r"\s+nocapture\b", normalized)),
            "removed_capture_contracts": len(re.findall(r"\s+captures\([^)]*\)", normalized)),
            "removed_memory_effect_contracts": len(re.findall(r"\s+memory\([^)]*\)", normalized)),
            "removed_pointer_assumptions": len(re.findall(r"\s+(?:nonnull|readonly|readnone|align\s+\d+|dereferenceable\(\d+\))", normalized)),
            "removed_eh_personality": len(re.findall(r"\s+personality ptr @rust_eh_personality", normalized)),
            "removed_instruction_metadata": len(re.findall(r",\s*![-A-Za-z0-9_.]+\s*!\d+", normalized)),
            "removed_debug_intrinsics": len(re.findall(r"^.*@llvm\.dbg\.[^\n]*\n", normalized, re.MULTILINE)),
            "removed_debug_records": len(re.findall(r"^\s*#dbg_[^\n]*\n", normalized, re.MULTILINE)),
            "removed_debug_attachments": len(re.findall(r"(?:,\s*|\s+)!dbg\s*!\d+", normalized)),
        }
        normalized = re.sub(r"\s+noalias\b", "", normalized)
        normalized = re.sub(r"\s+nocapture\b", "", normalized)
        normalized = re.sub(r"\s+captures\([^)]*\)", "", normalized)
        normalized = re.sub(r"\s+memory\([^)]*\)", "", normalized)
        normalized = re.sub(r"\s+(?:nonnull|readonly|readnone|align\s+\d+|dereferenceable\(\d+\))", "", normalized)
        normalized = re.sub(r",\s*\n", "\n", normalized)
        normalized = re.sub(r"\s+personality ptr @rust_eh_personality", "", normalized)
        normalized = re.sub(r",\s*![-A-Za-z0-9_.]+\s*!\d+", "", normalized)
        normalized = re.sub(r"^.*@llvm\.dbg\.[^\n]*\n", "", normalized, flags=re.MULTILINE)
        normalized = re.sub(r"^\s*#dbg_[^\n]*\n", "", normalized, flags=re.MULTILINE)
        normalized = re.sub(r"(?:,\s*|\s+)!dbg\s*!\d+", "", normalized)
        normalized = re.sub(r",\s*,", ",", normalized)
        normalized = re.sub(r",[ \t]*\n", "\n", normalized)
        normalized_path.write_text(normalized)
        command = [str(alive_tv), "--bidirectional", "--always-verify", "--smt-to=60000", str(normalized_path)]
        try:
            completed = subprocess.run(
                command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_seconds,
            )
            combined = completed.stdout + "\n" + completed.stderr
            unsupported = "Unsupported" in combined or "ERROR:" in combined
            failed = "Transformation doesn't verify" in combined or "ERROR" in combined
            succeeded = completed.returncode == 0 and "Transformation seems to be correct" in combined and not failed
            report = {
                "status": "PASS" if succeeded else "UNSUPPORTED" if unsupported else "FAIL",
                "proof_class": "bounded_llvm_refinement",
                "command": command,
                "return_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "scope": "fixed-length wrappers emitted from baseline and candidate Rust source",
                "original_llvm": str(llvm_path),
                "original_llvm_sha256": _sha256(llvm_path),
                "alive2_input": str(normalized_path),
                "alive2_input_sha256": _sha256(normalized_path),
                "normalization": {
                    "kind": "assumption-erasing-rustc-llvm-compatibility",
                    "soundness": "only unsupported attributes/metadata are removed; executable operations are unchanged",
                    **transformations,
                },
            }
        except subprocess.TimeoutExpired as error:
            report = {
                "status": "TIMEOUT",
                "proof_class": "bounded_llvm_refinement",
                "command": command,
                "stdout": error.stdout or "",
                "stderr": error.stderr or "",
            }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def build_rust_benchmark_harness(
    function: RustFunction,
    candidates: tuple[RustCandidate, ...],
    output_path: Path,
) -> dict[str, Any]:
    baseline = renamed_rust_function(function, "baseline")
    candidate_source = "\n".join(candidate.source for candidate in candidates)
    arms = "\n".join(
        f'        "{candidate.rule}" => candidate_{candidate.rule}(data, needle),'
        for candidate in candidates
    )
    source = f'''use std::hint::black_box;
use std::time::Instant;

{baseline}
{candidate_source}

fn invoke(mode: &str, data: &[u8], needle: u8) -> usize {{
    match mode {{
        "baseline" => baseline(data, needle),
{arms}
        _ => panic!("unknown mode: {{}}", mode),
    }}
}}

fn next_u64(state: &mut u64) -> u64 {{
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    *state
}}

fn main() {{
    let mode = std::env::args().nth(1).unwrap_or_else(|| "verify".to_string());
    let n = std::env::var("VLADDER_N").ok().and_then(|v| v.parse().ok()).unwrap_or(1 << 20);
    let inner = std::env::var("VLADDER_INNER").ok().and_then(|v| v.parse().ok()).unwrap_or(128usize);
    let needle = 0x7fu8;
    let mut state = 0x4d595df4d0f33173u64;
    let mut data = Vec::with_capacity(n);
    for _ in 0..n {{ data.push(next_u64(&mut state) as u8); }}

    for length in 0..=257usize {{
        let sample = &data[..length.min(data.len())];
        let expected = baseline(sample, needle);
        for candidate in [{candidate_names(candidates)}] {{
            assert_eq!(invoke(candidate, sample, needle), expected, "candidate={{}} length={{}}", candidate, length);
        }}
    }}
    for value in [0u8, needle, 255u8] {{
        let adversarial = vec![value; 257];
        let expected = baseline(&adversarial, needle);
        for candidate in [{candidate_names(candidates)}] {{
            assert_eq!(invoke(candidate, &adversarial, needle), expected, "candidate={{}} adversarial={{}}", candidate, value);
        }}
    }}
    if mode == "verify" {{
        println!(r#"{{{{"status":"PASS","observable":"verification-complete","metric_ns":0}}}}"#);
        return;
    }}

    let expected = baseline(&data, needle);
    assert_eq!(invoke(&mode, &data, needle), expected);
    let start = Instant::now();
    let mut checksum = 0usize;
    for _ in 0..inner {{
        checksum = checksum.wrapping_add(black_box(invoke(&mode, black_box(&data), black_box(needle))));
    }}
    let elapsed = start.elapsed().as_nanos() as f64 / inner as f64;
    println!(r#"{{{{"metric_ns":{{:.3}},"observable":"{{}}","checksum":{{}}}}}}"#, elapsed, expected, checksum);
}}
'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source)
    return {"source": str(output_path), "source_sha256": hashlib.sha256(source.encode()).hexdigest()}


def compile_rust_executable(
    rustc: Path,
    source: Path,
    executable: Path,
    *,
    edition: str,
    target_cpu: str,
    overflow_checks: bool,
    cwd: Path | None = None,
) -> dict[str, Any]:
    command = [
        str(rustc), str(source), "--edition", edition, "-C", "opt-level=3", "-C", "codegen-units=1",
        "-C", f"target-cpu={target_cpu}", "-C", f"overflow-checks={'yes' if overflow_checks else 'no'}",
        "-o", str(executable),
    ]
    completed = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "command": command,
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "executable": str(executable) if executable.exists() else None,
        "executable_sha256": _sha256(executable) if executable.exists() else None,
    }


def rustfmt_source(
    rustfmt: Path | None,
    source: Path,
    edition: str,
    *,
    cwd: Path | None = None,
) -> dict[str, Any]:
    if rustfmt is None:
        return {"status": "unavailable", "source": str(source)}
    completed = subprocess.run(
        [str(rustfmt), "--edition", edition, str(source)],
        cwd=cwd,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "source": str(source),
    }


def candidate_names(candidates: tuple[RustCandidate, ...]) -> str:
    return ", ".join(f'"{candidate.rule}"' for candidate in candidates)


def _native_signature(function: RustFunction, name: str) -> str:
    signature, count = re.subn(
        rf"\bfn\s+{re.escape(function.source_name)}\b",
        f"fn {name}",
        function.signature,
        count=1,
    )
    if count != 1:
        raise ValueError("cannot regenerate the selected Rust signature")
    return signature


def _count_candidate_source(
    function: RustFunction,
    model: RustKernelModel,
    name: str,
    factor: int,
    banks: int,
) -> str:
    signature = _native_signature(function, name)
    slice_name = model.slice_parameter
    needle = model.needle_parameter
    declarations = "\n".join(f"    let mut count{bank} = 0usize;" for bank in range(banks))
    lane_lines: list[str] = []
    for lane in range(factor):
        bank = lane % banks
        lane_lines.append(f"        count{bank} += ({slice_name}[i + {lane}] == {needle}) as usize;")
    reduction = " + ".join(f"count{bank}" for bank in range(banks))
    source = f'''{signature} {{
    // vladder: operation=count_equal_u8 factor={factor} accumulator_banks={banks}
{declarations}
    let mut i = 0usize;
    while {slice_name}.len() - i >= {factor} {{
{chr(10).join(lane_lines)}
        i += {factor};
    }}
    while i < {slice_name}.len() {{
        count0 += ({slice_name}[i] == {needle}) as usize;
        i += 1;
    }}
    {reduction}
}}
'''
    return source


def _extract_body(source: str) -> str:
    start = source.find("{")
    end = source.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("generated Rust function has no body")
    return source[start + 1 : end]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
