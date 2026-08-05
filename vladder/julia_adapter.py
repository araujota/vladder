from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import yaml

from .bounded_reduction import ReductionSchedule, count_equal_graph, prove_count_schedule, prove_schedule_llvm, standard_count_schedules
from .language_adapter import LANGUAGE_ADAPTER_PROTOCOL_VERSION, LanguageAdapterRegistry, LanguageCapability, LanguageRegionEvidence, file_sha256
from .paired_benchmark import run_paired_benchmark


JULIA_SUPPORT_VERSION = "bounded-julia-regions-v1"


@dataclass(frozen=True)
class JuliaRegionRequest:
    project: Path
    source: Path
    module: str
    function: str
    signature: str
    output_directory: Path
    proof_bound: int = 32
    minimum_speedup_pct: float = 1.0
    benchmark_elements: int = 1 << 20
    benchmark_inner: int = 128
    benchmark_processes: int = 8
    benchmark_repetitions: int = 2
    cpu: int | None = None
    cpu_target: str = "native"


@dataclass(frozen=True)
class JuliaCandidate:
    id: str
    rule: str
    schedule: ReductionSchedule
    source: str
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "schedule": self.schedule.to_dict()}


class JuliaLanguageAdapter:
    name = "julia-typed-llvm"
    source_language = "julia"
    support_version = JULIA_SUPPORT_VERSION

    def inspect(self, request: JuliaRegionRequest) -> LanguageRegionEvidence:
        return _capture(request)[0]

    def synthesize(self, request: JuliaRegionRequest) -> dict[str, Any]:
        return synthesize_julia_region(request)

    def optimize(self, request: JuliaRegionRequest) -> dict[str, Any]:
        return optimize_julia_region(request)


def julia_language_registry() -> LanguageAdapterRegistry:
    registry = LanguageAdapterRegistry()
    registry.register(JuliaLanguageAdapter())
    return registry


def julia_support_report() -> dict[str, Any]:
    julia = shutil.which("julia")
    alive = shutil.which("alive-tv")
    return {
        **julia_language_registry().support_matrix(),
        "status": "pass" if julia else "unavailable",
        "strict_proof_ready": bool(julia and alive),
        "tools": {
            "julia": {"available": bool(julia), "path": julia, "version": _command([julia, "--version"]) if julia else None},
            "alive-tv": {"available": bool(alive), "path": alive, "version": _command([alive, "--version"]).splitlines()[0] if alive else None},
        },
        "semantic_vocabulary": "shared SemanticFlowGraph; specialization, world, GC, and dispatch facts are obligations",
    }


def inspect_julia_region(request: JuliaRegionRequest) -> dict[str, Any]:
    return _capture(request)[0].to_dict()


def isolate_julia_region(request: JuliaRegionRequest) -> dict[str, Any]:
    evidence, function_source = _capture(request)
    report = {
        "schema_version": "vladder-julia-isolation-v1",
        "status": "pass" if evidence.status == "supported" else "adapter_required",
        "support": evidence.to_dict(),
        "proof_unit": {"source": function_source, "source_sha256": hashlib.sha256(function_source.encode()).hexdigest()},
        "source_changes_performed": False,
    }
    _write_json(request.output_directory / "julia-isolation.json", report)
    return report


def synthesize_julia_region(request: JuliaRegionRequest) -> dict[str, Any]:
    evidence, function_source = _capture(request)
    output = request.output_directory.resolve()
    if evidence.status != "supported":
        report = {"schema_version": "vladder-julia-synthesis-v1", "status": "adapter_required", "support": evidence.to_dict(), "candidate_count": 0}
        _write_json(output / "julia-synthesis.json", report)
        return report
    candidates = _generate_candidates()
    reports = []
    for candidate in candidates:
        root = output / "candidates" / candidate.rule
        root.mkdir(parents=True, exist_ok=True)
        source = root / "candidate.jl"
        source.write_text(candidate.source)
        schedule = _parse_julia_schedule(candidate.source)
        z3 = prove_count_schedule(
            schedule, root / "proofs" / "schedule.smt2", proof_bound=request.proof_bound,
            candidate_id=candidate.id, source_sha256=candidate.source_sha256, language="julia",
            panic_policy="captured @inbounds valid-vector contract; exact Int count cannot overflow length",
        )
        native = _capture_candidate_ir(request, candidate, root / "compiled")
        native_llvm = {
            "status": "CAPTURED_NOT_PROOF", "artifact": native.get("llvm_ir"),
            "reason": "Julia GC/safepoint ABI IR is retained as specialization provenance; strict proof uses the source-derived canonical LLVM unit",
        }
        alive = Path(shutil.which("alive-tv")) if shutil.which("alive-tv") else None
        llvm = prove_schedule_llvm(
            schedule, root / "proofs" / "schedule-proof.ll", alive_tv=alive,
            bound=request.proof_bound, language="julia", source_sha256=candidate.source_sha256,
        )
        proved = z3["status"] == "PASS" and native["status"] == "pass" and llvm["status"] == "PASS"
        item = {
            "candidate": candidate.to_dict(), "source": str(source), "compiled_semantics": native,
            "schedule_proof": z3, "native_llvm_refinement": native_llvm, "llvm_refinement": llvm,
            "proof_status": "PASS" if proved else "FAIL",
            "application_performed": False,
        }
        _write_json(root / "candidate.json", item)
        reports.append(item)
    report = {
        "schema_version": "vladder-julia-synthesis-v1", "status": "pass", "support": evidence.to_dict(),
        "candidate_count": len(reports), "proved_candidate_count": sum(x["proof_status"] == "PASS" for x in reports),
        "candidates": reports, "source_changes_performed": False,
        "claim_boundary": "one concrete Julia method specialization and world identity; other methods and future world states excluded",
    }
    _write_json(output / "julia-synthesis.json", report)
    return report


def optimize_julia_region(request: JuliaRegionRequest) -> dict[str, Any]:
    synthesis = synthesize_julia_region(request)
    output = request.output_directory.resolve()
    if synthesis.get("status") != "pass":
        report = {"schema_version": "vladder-julia-optimization-v1", "status": "adapter_required", "synthesis": synthesis, "promotion": {"promotable": False}}
        _write_json(output / "julia-optimization.json", report)
        return report
    _, baseline = _capture(request)
    candidates = [_candidate_from_dict(x["candidate"]) for x in synthesis["candidates"]]
    harness = output / "benchmark" / "benchmark.jl"
    harness.parent.mkdir(parents=True, exist_ok=True)
    harness.write_text(_julia_benchmark_source(baseline, candidates, request.benchmark_elements, request.benchmark_inner))
    executable = output / "benchmark" / "run-julia"
    executable.write_text(f"#!/bin/sh\nexec {shutil.which('julia')} --startup-file=no --project={request.project.resolve()} {harness} \"$@\"\n")
    executable.chmod(0o755)
    verify = subprocess.run([str(executable), "verify"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if verify.returncode:
        report = {"schema_version": "vladder-julia-optimization-v1", "status": "differential_failed", "differential": {"stdout": verify.stdout, "stderr": verify.stderr}, "promotion": {"promotable": False}}
        _write_json(output / "julia-optimization.json", report)
        return report
    proof_by_id = {x["candidate"]["id"]: x for x in synthesis["candidates"]}
    measurements = []
    for candidate in candidates:
        manifest = {
            "executable": str(executable), "baseline_args": ["baseline"], "candidate_args": [candidate.rule],
            "cwd": str(executable.parent), "processes": request.benchmark_processes,
            "repetitions_per_process": request.benchmark_repetitions, "metric_key": "metric_ns",
            "observable_key": "observable", "exact_observables": True, "direction": "lower",
            "minimum_effect_percent": request.minimum_speedup_pct, "bootstrap_rounds": 1000,
            "seed": int(candidate.id[:8], 16), "cpu": _available_cpu(request.cpu), "candidate_identity": candidate.id,
            "environment": {"JULIA_CPU_TARGET": request.cpu_target, "JULIA_NUM_THREADS": "1"},
        }
        manifest_path = executable.parent / f"paired-{candidate.id}.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True))
        physical = run_paired_benchmark(manifest_path, executable.parent / candidate.id)
        strict = proof_by_id[candidate.id]["proof_status"] == "PASS"
        measurements.append({"candidate": candidate.to_dict(), "strict_proof": strict, "physical": physical, "promotable": strict and physical["promotable_physical_evidence"]})
    winners = sorted((x for x in measurements if x["promotable"]), key=lambda x: x["physical"]["paired_effect_percent"], reverse=True)
    winner = winners[0] if winners else None
    report = {
        "schema_version": "vladder-julia-optimization-v1", "status": "pass", "synthesis_report": str(output / "julia-synthesis.json"),
        "benchmark_harness": str(harness), "differential": {"status": "PASS", "stdout": verify.stdout.strip()},
        "measurements": measurements, "winner": winner,
        "promotion": {"promotable": winner is not None, "requires_project_integration": True, "source_applied": False},
        "claim_boundary": "best verified steady-state realization for the captured Julia specialization and world",
    }
    _write_json(output / "julia-optimization.json", report)
    return report


def audit_julia_regions(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("regions"), list):
        raise ValueError("Julia audit manifest requires a regions list")
    rows = []
    for index, item in enumerate(raw["regions"]):
        request = JuliaRegionRequest(
            project=(manifest_path.parent / str(item.get("project", "."))).resolve(),
            source=(manifest_path.parent / str(item["source"])).resolve(), module=str(item["module"]),
            function=str(item["function"]), signature=str(item["signature"]),
            output_directory=output_directory / str(item.get("id", index)),
        )
        rows.append({"id": str(item.get("id", index)), **inspect_julia_region(request)})
    report = {"schema_version": "vladder-julia-audit-v1", "regions": rows, "supported_count": sum(x["status"] == "supported" for x in rows)}
    _write_json(output_directory / "julia-audit.json", report)
    return report


def _capture(request: JuliaRegionRequest) -> tuple[LanguageRegionEvidence, str]:
    julia = shutil.which("julia")
    if not julia: raise RuntimeError("julia is required")
    source = request.source.resolve()
    function = _extract_julia_function(source.read_text(), request.function)
    blockers = _source_blockers(function, request.signature)
    output = request.output_directory.resolve()
    capture = output / "capture"
    capture.mkdir(parents=True, exist_ok=True)
    reflection = _run_reflection(request, capture)
    if reflection["status"] != "pass":
        blockers.append({"kind": "compiler-semantic-failure", "reason": reflection.get("stderr", "")[-1000:], "required_adapter": "resolve module/method/signature capture"})
    else:
        typed = Path(reflection["artifacts"]["typed_ir"]).read_text()
        allocation = int(reflection["metadata"].get("allocated_bytes", "-1"))
        if " dynamic " in typed or "::Any" in typed:
            blockers.append({"kind": "dynamic-dispatch", "reason": "typed IR is not fully concrete", "required_adapter": "specialize the method and remove dynamic dispatch"})
        if reflection["metadata"].get("return_type") != "Int64":
            blockers.append({"kind": "type-instability", "reason": f"inferred return type is {reflection['metadata'].get('return_type')}", "required_adapter": "isolate a concretely inferred specialization"})
        if allocation != 0:
            blockers.append({"kind": "gc-allocation", "reason": f"sampled steady-state allocation is {allocation} bytes", "required_adapter": "isolate an allocation-free kernel or model GC-visible ownership"})
    version = _command([julia, "--version"])
    project = request.project.resolve()
    config = []
    for name in ("Project.toml", "JuliaProject.toml", "Manifest.toml", f"Manifest-v{version.split()[-1].rsplit('.', 1)[0]}.toml", "LocalPreferences.toml"):
        path = project / name
        if path.exists(): config.append({"path": str(path), "sha256": file_sha256(path)})
    artifacts = reflection.get("artifacts", {})
    graph = None
    if not blockers:
        graph = count_equal_graph(
            name=request.function, language="julia", compiler_identity=version, semantic_ir="Julia lowered + inferred typed IR",
            function_identity=f"{request.module}.{request.function}::{request.signature}",
            source_provenance={"source": str(source), "source_sha256": file_sha256(source), "module": request.module, "function": request.function, "signature": request.signature},
            contracts={"operation": "count_equal_u8", "specialization": request.signature, "world": reflection["metadata"].get("world"), "bounds": "@inbounds valid Vector storage", "allocation": "zero steady-state bytes"},
            excluded_claims=("other generic-function methods or future world states", "GC ownership, tasks, global mutation, ccall, and external effects"),
        )
    capabilities = _capabilities(graph is not None, not blockers, artifacts)
    status = "supported" if graph is not None and not blockers else "local_graph_only" if graph else "adapter_required"
    evidence = LanguageRegionEvidence(
        LANGUAGE_ADAPTER_PROTOCOL_VERSION, JuliaLanguageAdapter.name, "julia", JULIA_SUPPORT_VERSION,
        f"{request.module}.{request.function}::{request.signature}", status, capabilities, graph,
        {"julia_identity": version, "project": str(project), "configuration": config, "source_sha256": file_sha256(source), "cpu_target": request.cpu_target, **reflection.get("metadata", {})},
        tuple(blockers), artifacts,
        "one concrete inferred Julia method specialization in the captured world and project",
    )
    _write_json(output / "julia-support.json", evidence.to_dict())
    return evidence, function


def _run_reflection(request: JuliaRegionRequest, output: Path) -> dict[str, Any]:
    script = output / "capture.jl"
    paths = {name: output / name for name in ("lowered.txt", "typed.txt", "llvm.ll", "native.s")}
    script.write_text(f'''using InteractiveUtils
include({json.dumps(str(request.source.resolve()))})
mod = getfield(Main, Symbol({json.dumps(request.module)}))
fun = getfield(mod, Symbol({json.dumps(request.function)}))
types = Tuple{{{request.signature}}}
open({json.dumps(str(paths['lowered.txt']))}, "w") do io; show(io, MIME("text/plain"), code_lowered(fun, types)); end
open({json.dumps(str(paths['typed.txt']))}, "w") do io; show(io, MIME("text/plain"), code_typed(fun, types; optimize=true)); end
open({json.dumps(str(paths['llvm.ll']))}, "w") do io; code_llvm(io, fun, types; raw=true, dump_module=false, optimize=true, debuginfo=:none); end
open({json.dumps(str(paths['native.s']))}, "w") do io; code_native(io, fun, types; syntax=:intel, debuginfo=:none); end
sample = fill(UInt8(1), 1024)
fun(sample, UInt8(1))
measure_allocated(f, value) = @allocated f(value, UInt8(1))
allocated = measure_allocated(fun, sample)
method = which(fun, types)
println("VLADDER|world|", Base.get_world_counter())
println("VLADDER|method|", method)
println("VLADDER|method_file|", method.file)
println("VLADDER|method_line|", method.line)
println("VLADDER|allocated_bytes|", allocated)
println("VLADDER|return_type|", only(code_typed(fun, types; optimize=true))[2])
println("VLADDER|effects|", Base.infer_effects(fun, types))
println("VLADDER|sysimage|", unsafe_string(Base.JLOptions().image_file))
''')
    command = [shutil.which("julia") or "julia", "--startup-file=no", f"--project={request.project.resolve()}", str(script)]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    metadata = {}
    for line in result.stdout.splitlines():
        if line.startswith("VLADDER|"):
            _, key, value = line.split("|", 2); metadata[key] = value
    artifacts = {"reflection_script": str(script)}
    if result.returncode == 0:
        artifacts.update({"lowered_ir": str(paths["lowered.txt"]), "typed_ir": str(paths["typed.txt"]), "llvm_ir": str(paths["llvm.ll"]), "assembly": str(paths["native.s"])})
    return {"status": "pass" if result.returncode == 0 else "fail", "command": command, "stdout": result.stdout, "stderr": result.stderr, "metadata": metadata, "artifacts": artifacts}


def _capture_candidate_ir(request: JuliaRegionRequest, candidate: JuliaCandidate, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    source = output / "capture.jl"
    typed, llvm, native = output / "typed.txt", output / "candidate.ll", output / "candidate.s"
    source.write_text(f'''using InteractiveUtils
{candidate.source}
fun = candidate_{candidate.rule}
types = Tuple{{Vector{{UInt8}},UInt8}}
open({json.dumps(str(typed))}, "w") do io; show(io, MIME("text/plain"), code_typed(fun, types; optimize=true)); end
open({json.dumps(str(llvm))}, "w") do io; code_llvm(io, fun, types; raw=true, dump_module=false, optimize=true, debuginfo=:none); end
open({json.dumps(str(native))}, "w") do io; code_native(io, fun, types; syntax=:intel, debuginfo=:none); end
measure_allocated(f, value) = @allocated f(value, UInt8(1))
sample = fill(UInt8(1), 1024); fun(sample, UInt8(1)); println(measure_allocated(fun, sample))
''')
    result = subprocess.run([shutil.which("julia") or "julia", "--startup-file=no", f"--project={request.project.resolve()}", str(source)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    allocated = int(result.stdout.strip().splitlines()[-1]) if result.returncode == 0 and result.stdout.strip() else -1
    return {"status": "pass" if result.returncode == 0 and allocated == 0 else "fail", "allocated_bytes": allocated, "typed_ir": str(typed), "llvm_ir": str(llvm), "assembly": str(native), "stderr": result.stderr}


def _prove_julia_llvm(request: JuliaRegionRequest, baseline: str, candidate: JuliaCandidate, output: Path, bound: int) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    script = output / "llvm-proof.jl"
    source_ir, target_ir = output / "source.ll", output / "target.ll"
    baseline_body = _julia_fixed_source("proof_function", ReductionSchedule(1, 1, (0,), (0,)), bound)
    candidate_body = _julia_fixed_source("proof_function", candidate.schedule, bound)
    script.write_text(f'''using InteractiveUtils
module SourceProof
{baseline_body}
end
module TargetProof
{candidate_body}
end
types = Tuple{{NTuple{{{bound},UInt8}},UInt8}}
open({json.dumps(str(source_ir))}, "w") do io; code_llvm(io, SourceProof.proof_function, types; raw=true, dump_module=false, optimize=true, debuginfo=:none); end
open({json.dumps(str(target_ir))}, "w") do io; code_llvm(io, TargetProof.proof_function, types; raw=true, dump_module=false, optimize=true, debuginfo=:none); end
''')
    run = subprocess.run([shutil.which("julia") or "julia", "--startup-file=no", f"--project={request.project.resolve()}", str(script)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run.returncode:
        return {"status": "NOT_RUN", "reason": "Julia LLVM proof emission failed", "stderr": run.stderr}
    _rename_first_llvm_function(source_ir, "proof_function")
    _rename_first_llvm_function(target_ir, "proof_function")
    alive = shutil.which("alive-tv")
    if not alive: return {"status": "UNAVAILABLE", "reason": "alive-tv is unavailable"}
    command = [alive, "--bidirectional", "--always-verify", "--smt-to=60000", str(source_ir), str(target_ir)]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    combined = result.stdout + result.stderr
    passed = result.returncode == 0 and "Transformation seems to be correct" in combined
    report = {"status": "PASS" if passed else "FAIL", "proof_class": "Julia-emitted fixed-specialization bounded LLVM refinement", "command": command, "stdout": result.stdout, "stderr": result.stderr, "source_ir": str(source_ir), "target_ir": str(target_ir), "bound": bound}
    _write_json(output / "alive2.json", report)
    return report


def _rename_first_llvm_function(path: Path, name: str) -> None:
    text = path.read_text()
    text, count = re.subn(r"(define\s+[^@\n]*@)(?:\"[^\"]+\"|[-A-Za-z0-9_.$]+)(\()", rf"\1{name}\2", text, count=1)
    if count != 1: raise ValueError("Julia LLVM artifact has no function definition")
    path.write_text(text)


def _extract_julia_function(text: str, requested: str) -> str:
    name = requested.split(".")[-1]
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if re.match(rf"\s*function\s+{re.escape(name)}\s*\(", line)), None)
    if start is None: raise ValueError(f"Julia long-form function not found: {requested}")
    depth = 0
    starters = re.compile(r"\b(function|for|while|if|let|begin|try|struct|macro)\b")
    for index in range(start, len(lines)):
        stripped = lines[index].split("#", 1)[0]
        if starters.search(stripped): depth += 1
        if re.match(r"^\s*end\b", stripped):
            depth -= 1
            if depth == 0: return "".join(lines[start:index + 1])
    raise ValueError(f"unterminated Julia function: {requested}")


def _source_blockers(function: str, signature: str) -> list[dict[str, str]]:
    blockers = []
    def add(kind: str, reason: str, adapter: str) -> None: blockers.append({"kind": kind, "reason": reason, "required_adapter": adapter})
    normalized = signature.replace(" ", "")
    if normalized not in {"Vector{UInt8},UInt8", "Array{UInt8,1},UInt8"}:
        add("specialization-boundary", "J1 requires Vector{UInt8},UInt8", "register the concrete array/layout specialization")
    checks = [
        (r"\b(copy|similar|zeros|ones|push!|append!)\s*\(", "gc-allocation", "GC allocation/ownership protocol"),
        (r"\b(ccall|@ccall|llvmcall)\b", "external-effect", "native/external call contract"),
        (r"\b(@async|@spawn|Threads\.|Channel\s*\()", "task-concurrency", "task and synchronization protocol"),
        (r"\b(global|eval|@eval)\b", "world-or-global-state", "global mutation and world-age protocol"),
        (r"\brand\s*\(", "nondeterministic-effect", "random-state and determinism contract"),
        (r"\b(throw|error|try|catch|finally)\b", "exception-effect", "exception and cleanup protocol"),
    ]
    for pattern, kind, adapter in checks:
        if re.search(pattern, function): add(kind, f"selected method contains {kind}", adapter)
    if "for " not in function or "== needle" not in function:
        add("operation-shape", "J1 recognizes exact byte equality reductions", "register a shared operation and Julia lowering")
    if "@inbounds" not in function:
        add("bounds-policy", "J1 candidates require an explicit @inbounds contract", "preserve and prove the method's bounds-failure behavior")
    return blockers


def _generate_candidates() -> tuple[JuliaCandidate, ...]:
    values = []
    for rule, schedule in standard_count_schedules():
        source = _julia_candidate_source(rule, schedule)
        digest = hashlib.sha256(source.encode()).hexdigest()
        values.append(JuliaCandidate(digest[:16], rule, schedule, source, digest))
    return tuple(values)


def _julia_candidate_source(rule: str, schedule: ReductionSchedule) -> str:
    name = f"candidate_{rule}"
    if schedule.factor == 1:
        return f"function {name}(bytes::Vector{{UInt8}}, needle::UInt8)::Int\n    count = 0\n    @inbounds for value in bytes\n        count += value == needle\n    end\n    return count\nend\n"
    banks = "\n".join(f"    count{b} = 0" for b in range(schedule.accumulator_banks))
    lanes = "\n".join(f"        count{schedule.lane_banks[i]} += bytes[index + {i + 1}] == needle" for i in range(schedule.factor))
    total = " + ".join(f"count{b}" for b in range(schedule.accumulator_banks))
    return f"function {name}(bytes::Vector{{UInt8}}, needle::UInt8)::Int\n{banks}\n    index = 0\n    @inbounds while index + {schedule.factor} <= length(bytes)\n{lanes}\n        index += {schedule.factor}\n    end\n    @inbounds while index < length(bytes)\n        index += 1\n        count0 += bytes[index] == needle\n    end\n    return {total}\nend\n"


def _parse_julia_schedule(source: str) -> ReductionSchedule:
    match = re.search(r"index \+ (\d+) <= length\(bytes\)", source)
    factor = int(match.group(1)) if match else 1
    banks = max([int(x) for x in re.findall(r"count(\d+) = 0", source)] + [0]) + 1
    if factor == 1: return ReductionSchedule(1, 1, (0,), (0,))
    lane_banks = []
    for lane in range(factor):
        found = re.search(rf"count(\d+) \+= bytes\[index \+ {lane + 1}\] == needle", source)
        if not found: raise ValueError("generated Julia candidate does not visit every lane exactly once")
        lane_banks.append(int(found.group(1)))
    return ReductionSchedule(factor, banks, tuple(range(factor)), tuple(lane_banks))


def _julia_fixed_source(name: str, schedule: ReductionSchedule, bound: int) -> str:
    if schedule.factor == 1:
        return f"function {name}(bytes::NTuple{{{bound},UInt8}}, needle::UInt8)::Int\n count=0; for value in bytes; count += value == needle; end; count; end"
    banks = "; ".join(f"count{b}=0" for b in range(schedule.accumulator_banks))
    lanes = "; ".join(f"count{schedule.lane_banks[i]} += bytes[index+{i+1}] == needle" for i in range(schedule.factor))
    total = "+".join(f"count{b}" for b in range(schedule.accumulator_banks))
    return f"function {name}(bytes::NTuple{{{bound},UInt8}}, needle::UInt8)::Int\n {banks}; index=0; while index+{schedule.factor}<={bound}; {lanes}; index+={schedule.factor}; end; while index<{bound}; index+=1; count0 += bytes[index] == needle; end; {total}; end"


def _julia_benchmark_source(baseline: str, candidates: list[JuliaCandidate], size: int, inner: int) -> str:
    baseline = re.sub(r"function\s+\w+", "function baseline_impl", baseline, count=1)
    sources = "\n".join(c.source for c in candidates)
    branches = "\n".join(f'elseif mode == "{c.rule}"; observable = run(candidate_{c.rule}, data)' for c in candidates)
    verifies = "\n".join(f'candidate_{c.rule}(view_data, UInt8(17)) == expected || error("differential mismatch: {c.rule}")' for c in candidates)
    return f'''{baseline}
{sources}
const N = {size}
const INNER = {inner}
function run(fun, data)
    total = 0
    for iteration in 0:INNER-1
        total += fun(data, UInt8(iteration % 256))
    end
    return total
end
mode = isempty(ARGS) ? "verify" : ARGS[1]
data = Vector{{UInt8}}(undef, N)
for index in eachindex(data); data[index] = UInt8(mod((index-1)*131+17, 256)); end
if mode == "verify"
    for n in (0,1,2,3,4,7,8,15,31,64,257)
        view_data = data[1:n]
        expected = baseline_impl(view_data, UInt8(17))
        {verifies}
    end
    println(Char(123), Char(34), "status", Char(34), ":", Char(34), "PASS", Char(34), Char(125))
    exit()
end
run(baseline_impl, data)
{''.join(f'run(candidate_{c.rule}, data);' for c in candidates)}
GC.gc()
start = time_ns()
observable = 0
if mode == "baseline"; observable = run(baseline_impl, data)
{branches}
else; error("unknown candidate")
end
elapsed = time_ns() - start
println(Char(123), Char(34), "metric_ns", Char(34), ":", elapsed/(N*INNER), ",", Char(34), "observable", Char(34), ":", observable, Char(125))
'''


def _capabilities(graph: bool, closed: bool, artifacts: dict[str, str]) -> dict[str, LanguageCapability]:
    return {
        "semantic_capture": LanguageCapability(graph, graph, "one concrete Julia method specialization captured", artifacts.get("typed_ir")),
        "information_flow": LanguageCapability(graph, graph, "shared semantic information-flow graph"),
        "candidate_generation": LanguageCapability(closed, closed, "native Julia exact-reduction schedules"),
        "local_proof": LanguageCapability(closed, closed, "source-derived Z3 schedule plus fixed-specialization LLVM refinement"),
        "benchmark": LanguageCapability(closed, closed, "independent warmed Julia processes with one generated harness"),
        "source_rewrite": LanguageCapability(closed, closed, "native Julia method regeneration; no automatic application"),
        "protocol_equivalence": LanguageCapability(False, False, "other methods/worlds, GC ownership, tasks, globals, ccall, and external protocols excluded"),
    }


def _candidate_from_dict(raw: dict[str, Any]) -> JuliaCandidate:
    return JuliaCandidate(raw["id"], raw["rule"], ReductionSchedule(**raw["schedule"]), raw["source"], raw["source_sha256"])


def _available_cpu(cpu: int | None) -> int | None:
    if cpu is None: return None
    available = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    return cpu if not available or cpu in available else available[0]


def _command(command: list[str]) -> str:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (result.stdout + result.stderr).strip()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
