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
from .rust_verification import run_alive2_refinement


ZIG_SUPPORT_VERSION = "bounded-zig-regions-v2"


@dataclass(frozen=True)
class ZigRegionRequest:
    source: Path
    function: str
    output_directory: Path
    build_root: Path | None = None
    optimize_mode: str = "ReleaseFast"
    target: str = "native"
    proof_bound: int = 32
    minimum_speedup_pct: float = 1.0
    benchmark_elements: int = 1 << 20
    benchmark_inner: int = 128
    benchmark_processes: int = 8
    benchmark_repetitions: int = 2
    cpu: int | None = None
    specialization: str | None = None


@dataclass(frozen=True)
class ZigCandidate:
    id: str
    rule: str
    schedule: ReductionSchedule
    source: str
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "schedule": self.schedule.to_dict()}


class ZigLanguageAdapter:
    name = "zig-native-llvm"
    source_language = "zig"
    support_version = ZIG_SUPPORT_VERSION

    def inspect(self, request: ZigRegionRequest) -> LanguageRegionEvidence:
        return _capture(request)[0]

    def synthesize(self, request: ZigRegionRequest) -> dict[str, Any]:
        return synthesize_zig_region(request)

    def optimize(self, request: ZigRegionRequest) -> dict[str, Any]:
        return optimize_zig_region(request)


def zig_language_registry() -> LanguageAdapterRegistry:
    registry = LanguageAdapterRegistry()
    registry.register(ZigLanguageAdapter())
    return registry


def zig_support_report() -> dict[str, Any]:
    zig = shutil.which("zig")
    alive = shutil.which("alive-tv")
    return {
        **zig_language_registry().support_matrix(),
        "status": "pass" if zig else "unavailable",
        "strict_proof_ready": bool(zig and alive),
        "tools": {
            "zig": {"available": bool(zig), "path": zig, "version": _command([zig, "version"]) if zig else None},
            "alive-tv": {"available": bool(alive), "path": alive, "version": _command([alive, "--version"]).splitlines()[0] if alive else None},
        },
        "semantic_vocabulary": "shared SemanticFlowGraph; Zig safety and error semantics are obligations",
    }


def inspect_zig_region(request: ZigRegionRequest) -> dict[str, Any]:
    return _capture(request)[0].to_dict()


def isolate_zig_region(request: ZigRegionRequest) -> dict[str, Any]:
    evidence, function_source = _capture(request)
    report = {
        "schema_version": "vladder-zig-isolation-v1",
        "status": "pass" if evidence.status == "supported" else "adapter_required",
        "support": evidence.to_dict(),
        "proof_unit": {"source": function_source, "source_sha256": hashlib.sha256(function_source.encode()).hexdigest()},
        "source_changes_performed": False,
    }
    _write_json(request.output_directory / "zig-isolation.json", report)
    return report


def synthesize_zig_region(request: ZigRegionRequest) -> dict[str, Any]:
    evidence, function_source = _capture(request)
    output = request.output_directory.resolve()
    if evidence.status != "supported":
        report = {"schema_version": "vladder-zig-synthesis-v1", "status": "adapter_required", "support": evidence.to_dict(), "candidate_count": 0}
        _write_json(output / "zig-synthesis.json", report)
        return report
    zig = Path(shutil.which("zig") or "")
    alive = Path(shutil.which("alive-tv")) if shutil.which("alive-tv") else None
    candidates = _generate_candidates()
    reports: list[dict[str, Any]] = []
    for candidate in candidates:
        root = output / "candidates" / candidate.rule
        root.mkdir(parents=True, exist_ok=True)
        source = root / "candidate.zig"
        source.write_text(candidate.source)
        fmt = subprocess.run([str(zig), "fmt", str(source)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        formatted = source.read_text()
        candidate = ZigCandidate(
            hashlib.sha256(formatted.encode()).hexdigest()[:16], candidate.rule, candidate.schedule,
            formatted, hashlib.sha256(formatted.encode()).hexdigest(),
        )
        compile_report = _compile_zig(zig, source, root / "build", request.optimize_mode)
        schedule = _parse_zig_schedule(formatted)
        z3 = prove_count_schedule(
            schedule, root / "proofs" / "schedule.smt2", proof_bound=request.proof_bound,
            candidate_id=candidate.id, source_sha256=candidate.source_sha256, language="zig",
            panic_policy="valid slice bounds; candidate uses checked remainder partition",
        )
        proof_source = root / "proofs" / "llvm-proof.zig"
        proof_source.parent.mkdir(parents=True, exist_ok=True)
        proof_source.write_text(_zig_proof_source(function_source, candidate.source, candidate.rule, request.proof_bound))
        proof_compile = _compile_zig(zig, proof_source, root / "proofs" / "build", "ReleaseFast")
        llvm = Path(proof_compile["llvm_ir"]) if proof_compile.get("status") == "pass" else None
        if llvm:
            proof_ir = re.sub(r"^@[^\n]+\s=\s+alias\s+[^\n]+\n", "", llvm.read_text(), flags=re.MULTILINE)
            proof_ir = proof_ir.replace("@llvm-proof.", "@")
            proof_ir = re.sub(rf"define internal([^\n]+@(src|tgt)_{re.escape(candidate.rule)}\()", r"define\1", proof_ir)
            proof_ir = re.sub(
                rf"^define[^\n]+@(src|tgt)_{re.escape(candidate.rule)}\(ptr[^,]*%0, i8[^%]*%1\)[^{{]*{{",
                lambda match: f"define i64 @{match.group(1)}_{candidate.rule}(ptr %0, i8 %1) {{",
                proof_ir,
                flags=re.MULTILINE,
            )
            llvm.write_text(proof_ir)
        native_llvm = {
            "status": "CAPTURED_NOT_PROOF",
            "artifact": str(llvm) if llvm else None,
            "reason": "Zig 0.16 frontend aliases and capture attributes are retained as provenance; strict proof uses the source-derived canonical LLVM unit",
        }
        llvm_proof = prove_schedule_llvm(
            schedule, root / "proofs" / "schedule-proof.ll", alive_tv=alive,
            bound=request.proof_bound, language="zig", source_sha256=candidate.source_sha256,
        )
        proved = compile_report["status"] == "pass" and z3["status"] == "PASS" and llvm_proof.get("status") == "PASS"
        item = {
            "candidate": candidate.to_dict(), "source": str(source), "compile": compile_report,
            "schedule_proof": z3, "llvm_proof_unit": str(proof_source), "native_llvm_refinement": native_llvm,
            "llvm_refinement": llvm_proof,
            "proof_status": "PASS" if proved else "FAIL", "application_performed": False,
        }
        _write_json(root / "candidate.json", item)
        reports.append(item)
    report = {
        "schema_version": "vladder-zig-synthesis-v1", "status": "pass", "support": evidence.to_dict(),
        "candidate_count": len(reports), "proved_candidate_count": sum(x["proof_status"] == "PASS" for x in reports),
        "candidates": reports, "source_changes_performed": False,
        "claim_boundary": "native Zig source, schedule theorem, fixed-bound LLVM refinement; project promotion remains separate",
    }
    _write_json(output / "zig-synthesis.json", report)
    return report


def optimize_zig_region(request: ZigRegionRequest) -> dict[str, Any]:
    synthesis = synthesize_zig_region(request)
    output = request.output_directory.resolve()
    if synthesis.get("status") != "pass":
        report = {"schema_version": "vladder-zig-optimization-v1", "status": "adapter_required", "synthesis": synthesis, "promotion": {"promotable": False}}
        _write_json(output / "zig-optimization.json", report)
        return report
    _capture(request)
    candidates = [_candidate_from_dict(item["candidate"]) for item in synthesis["candidates"]]
    harness = output / "benchmark" / "benchmark.zig"
    harness.parent.mkdir(parents=True, exist_ok=True)
    zig = Path(shutil.which("zig") or "")
    baseline, import_prelude, target_module = _zig_benchmark_baseline(request, zig)
    harness.write_text(_zig_benchmark_source(
        baseline, candidates, request.benchmark_elements, request.benchmark_inner,
        import_prelude=import_prelude,
    ))
    subprocess.run([str(zig), "fmt", str(harness)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    executable = output / "benchmark" / "benchmark"
    compiled = (
        _compile_zig_executable_module(zig, harness, target_module, executable)
        if target_module is not None else
        _compile_zig_executable(zig, harness, executable)
    )
    if compiled["status"] != "pass":
        report = {"schema_version": "vladder-zig-optimization-v1", "status": "benchmark_compile_failed", "benchmark_compile": compiled, "promotion": {"promotable": False}}
        _write_json(output / "zig-optimization.json", report)
        return report
    verify = subprocess.run([str(executable), "verify"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if verify.returncode:
        report = {"schema_version": "vladder-zig-optimization-v1", "status": "differential_failed", "differential": {"stdout": verify.stdout, "stderr": verify.stderr}, "promotion": {"promotable": False}}
        _write_json(output / "zig-optimization.json", report)
        return report
    proof_by_id = {item["candidate"]["id"]: item for item in synthesis["candidates"]}
    measurements = []
    for candidate in candidates:
        manifest = {
            "executable": str(executable), "baseline_args": ["baseline"], "candidate_args": [candidate.rule],
            "cwd": str(executable.parent), "processes": request.benchmark_processes,
            "repetitions_per_process": request.benchmark_repetitions, "metric_key": "metric_ns",
            "observable_key": "observable", "exact_observables": True, "direction": "lower",
            "minimum_effect_percent": request.minimum_speedup_pct, "bootstrap_rounds": 1000,
            "seed": int(candidate.id[:8], 16), "cpu": _available_cpu(request.cpu), "candidate_identity": candidate.id,
        }
        manifest_path = executable.parent / f"paired-{candidate.id}.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True))
        physical = run_paired_benchmark(manifest_path, executable.parent / candidate.id)
        strict = proof_by_id[candidate.id]["proof_status"] == "PASS"
        measurements.append({"candidate": candidate.to_dict(), "strict_proof": strict, "physical": physical, "promotable": strict and physical["promotable_physical_evidence"]})
    winners = sorted((x for x in measurements if x["promotable"]), key=lambda x: x["physical"]["paired_effect_percent"], reverse=True)
    winner = winners[0] if winners else None
    report = {
        "schema_version": "vladder-zig-optimization-v1", "status": "pass", "synthesis_report": str(output / "zig-synthesis.json"),
        "benchmark_compile": compiled, "differential": {"status": "PASS", "stdout": verify.stdout.strip()},
        "measurements": measurements, "winner": winner,
        "promotion": {"promotable": winner is not None, "requires_project_integration": True, "source_applied": False},
        "claim_boundary": "best verified bounded Zig realization on this hardware",
    }
    _write_json(output / "zig-optimization.json", report)
    return report


def audit_zig_regions(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("regions"), list):
        raise ValueError("Zig audit manifest requires a regions list")
    rows = []
    for index, item in enumerate(raw["regions"]):
        request = ZigRegionRequest(
            source=(manifest_path.parent / str(item["source"])).resolve(), function=str(item["function"]),
            output_directory=output_directory / str(item.get("id", index)), build_root=manifest_path.parent,
        )
        rows.append({"id": str(item.get("id", index)), **inspect_zig_region(request)})
    report = {"schema_version": "vladder-zig-audit-v1", "regions": rows, "supported_count": sum(x["status"] == "supported" for x in rows)}
    _write_json(output_directory / "zig-audit.json", report)
    return report


def _capture(request: ZigRegionRequest) -> tuple[LanguageRegionEvidence, str]:
    zig = shutil.which("zig")
    if not zig:
        raise RuntimeError("zig is required")
    source = request.source.resolve()
    text = source.read_text()
    function = _extract_zig_function(text, request.function)
    blockers = _zig_blockers(function, request.specialization)
    output = request.output_directory.resolve()
    capture = output / "capture"
    capture.mkdir(parents=True, exist_ok=True)
    snapshot = capture / "selected-function.zig"
    wrapper_name = request.function.split(".")[-1]
    snapshot.write_text(function + "\n")
    wrapper = capture / "capture-root.zig"
    std_module = _zig_std_module(Path(zig), source)
    owner = std_module or "target"
    call = (
        f"{owner}.{wrapper_name}({request.specialization}, ptr[0..n], needle)"
        if request.specialization else f"{owner}.{wrapper_name}(ptr[0..n], needle)"
    )
    signature_closed = not any(item["kind"] == "type-boundary" for item in blockers)
    if signature_closed:
        wrapper.write_text(
            ('const std = @import("std");\n' if std_module else 'const target = @import("target");\n')
            +
            f"export fn vladder_capture(ptr: [*]const u8, n: usize, needle: u8) usize {{\n    return {call};\n}}\n"
        )
        compiled = (
            _compile_zig(Path(zig), wrapper, capture / "build", request.optimize_mode)
            if std_module else
            _compile_zig_module(Path(zig), wrapper, source, capture / "build", request.optimize_mode)
        )
    else:
        compiled = _compile_zig(Path(zig), source, capture / "build", request.optimize_mode)
    if compiled["status"] != "pass":
        blockers.append({"kind": "compiler-semantic-failure", "reason": compiled.get("stderr", "")[-1000:], "required_adapter": "fix source/build capture before optimization"})
    version = _command([zig, "version"])
    build_root = (request.build_root or _find_zig_root(source)).resolve()
    config = []
    for name in ("build.zig", "build.zig.zon"):
        path = build_root / name
        if path.exists():
            config.append({"path": str(path), "sha256": file_sha256(path)})
    artifacts = {key: value for key, value in compiled.items() if key in {"llvm_ir", "assembly", "object"} and isinstance(value, str)}
    artifacts["source_snapshot"] = str(snapshot)
    artifacts["capture_root"] = str(wrapper) if wrapper.exists() else None
    graph = None
    if not blockers:
        graph = count_equal_graph(
            name=request.function, language="zig", compiler_identity=f"zig {version}", semantic_ir="typed Zig source + compiler semantic analysis",
            function_identity=f"{source}:{request.function}", source_provenance={"source": str(source), "source_sha256": file_sha256(source), "function": request.function},
            contracts={"operation": "count_equal_u8", "safety_mode": request.optimize_mode, "ownership": "borrowed slice", "integer_overflow": "count <= slice.len"},
            excluded_claims=("allocator/error-union/defer protocols", "atomics, volatile I/O, assembly, and external effects"),
        )
    compiler_captured = compiled["status"] == "pass"
    capabilities = _capabilities(compiler_captured, graph is not None, not blockers, artifacts)
    status = "supported" if graph is not None and not blockers else "local_graph_only" if compiler_captured else "adapter_required"
    evidence = LanguageRegionEvidence(
        LANGUAGE_ADAPTER_PROTOCOL_VERSION, ZigLanguageAdapter.name, "zig", ZIG_SUPPORT_VERSION,
        request.function, status, capabilities, graph,
        {"zig_identity": version, "optimize_mode": request.optimize_mode, "target": request.target, "build_root": str(build_root), "configuration": config, "source_sha256": file_sha256(source), "specialization": request.specialization},
        tuple(blockers), artifacts,
        "selected Zig function under captured safety mode; external ownership, error, and device protocols excluded",
    )
    _write_json(output / "zig-support.json", evidence.to_dict())
    return evidence, function


def _extract_zig_function(text: str, requested: str) -> str:
    name = requested.split(".")[-1]
    match = re.search(rf"\b(?:pub\s+)?(?:export\s+)?fn\s+{re.escape(name)}\s*\(", text)
    if not match:
        raise ValueError(f"Zig function not found: {requested}")
    opening = text.find("{", match.end())
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{": depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0: return text[match.start():index + 1]
    raise ValueError(f"unterminated Zig function: {requested}")


def _zig_blockers(function: str, specialization: str | None = None) -> list[dict[str, str]]:
    blockers = []
    def add(kind: str, reason: str, adapter: str) -> None: blockers.append({"kind": kind, "reason": reason, "required_adapter": adapter})
    signature = function[:function.find("{")]
    direct = bool(re.search(r"\[\]const\s+u8", signature) and re.search(r"\bneedle\s*:\s*u8", signature))
    specialized = bool(
        specialization
        and re.search(r"comptime\s+\w+\s*:\s*type", signature)
        and re.search(r"\[\]const\s+\w+", signature)
    )
    if not (direct or specialized) or not re.search(r"\)\s*usize", signature):
        add("type-boundary", "Z1 requires ([]const u8, u8) usize", "model the concrete Zig type/ownership boundary")
    checks = [
        (r"\b(anytype|Allocator|alloc|dupe|create)\b", "allocation-ownership", "allocator and ownership protocol"),
        (r"\b(try|catch|error\{|!\[|!usize)\b", "error-union", "error-set and error-return protocol"),
        (r"\b(defer|errdefer)\b", "defer-lifetime", "defer/errdefer destruction ordering"),
        (r"\b(volatile|@volatileLoad|@volatileStore)\b", "volatile-effect", "volatile device/I/O contract"),
        (r"\b(@atomic|std\.atomic)\b", "atomic-ordering", "atomic memory-order protocol"),
        (r"\b(asm|@cImport|extern)\b", "external-effect", "assembly/FFI effect model"),
    ]
    for pattern, kind, adapter in checks:
        if re.search(pattern, function): add(kind, f"selected function contains {kind}", adapter)
    if "@intFromBool" not in function or "for (" not in function:
        add("operation-shape", "Z1 recognizes exact byte equality reductions", "register a shared operation and Zig lowering")
    return blockers


def _generate_candidates() -> tuple[ZigCandidate, ...]:
    values = []
    for rule, schedule in standard_count_schedules():
        source = _zig_candidate_source(rule, schedule)
        digest = hashlib.sha256(source.encode()).hexdigest()
        values.append(ZigCandidate(digest[:16], rule, schedule, source, digest))
    return tuple(values)


def _zig_candidate_source(rule: str, schedule: ReductionSchedule) -> str:
    name = f"candidate_{rule}"
    if schedule.factor == 1:
        return f"pub noinline fn {name}(bytes: []const u8, needle: u8) usize {{\n    var count: usize = 0;\n    for (bytes) |value| count += @intFromBool(value == needle);\n    return count;\n}}\n"
    banks = "\n".join(f"    var count{b}: usize = 0;" for b in range(schedule.accumulator_banks))
    lanes = "\n".join(f"        count{schedule.lane_banks[i]} += @intFromBool(bytes[index + {i}] == needle);" for i in range(schedule.factor))
    total = " + ".join(f"count{b}" for b in range(schedule.accumulator_banks))
    return f"pub noinline fn {name}(bytes: []const u8, needle: u8) usize {{\n{banks}\n    var index: usize = 0;\n    while (index + {schedule.factor} <= bytes.len) : (index += {schedule.factor}) {{\n{lanes}\n    }}\n    while (index < bytes.len) : (index += 1) count0 += @intFromBool(bytes[index] == needle);\n    return {total};\n}}\n"


def _parse_zig_schedule(source: str) -> ReductionSchedule:
    match = re.search(r"index \+ (\d+) <= bytes\.len", source)
    factor = int(match.group(1)) if match else 1
    banks = max([int(x) for x in re.findall(r"var count(\d+)", source)] + [0]) + 1
    if factor == 1: return ReductionSchedule(1, 1, (0,), (0,))
    lane_banks = []
    for lane in range(factor):
        found = re.search(rf"count(\d+) \+= @intFromBool\(bytes\[index \+ {lane}\]", source)
        if not found: raise ValueError("generated Zig candidate does not visit every lane exactly once")
        lane_banks.append(int(found.group(1)))
    return ReductionSchedule(factor, banks, tuple(range(factor)), tuple(lane_banks))


def _zig_proof_source(baseline: str, candidate: str, rule: str, bound: int) -> str:
    baseline = re.sub(r"\b(?:pub\s+)?fn\s+\w+", "fn baseline_impl", baseline, count=1)
    candidate = candidate.replace(f"pub noinline fn candidate_{rule}", "fn candidate_impl", 1)
    safe = re.sub(r"[^A-Za-z0-9_]", "_", rule)
    return baseline + "\n\n" + candidate + f"\nexport fn src_{safe}(bytes: *const [{bound}]u8, needle: u8) usize {{ return baseline_impl(bytes, needle); }}\nexport fn tgt_{safe}(bytes: *const [{bound}]u8, needle: u8) usize {{ return candidate_impl(bytes, needle); }}\n"


def _zig_benchmark_source(
    baseline: str,
    candidates: list[ZigCandidate],
    size: int,
    inner: int,
    *,
    import_prelude: str = "",
) -> str:
    sources = "\n".join(c.source for c in candidates)
    branches = "\n".join(f'    else if (std.mem.eql(u8, mode, "{c.rule}")) observable = run(candidate_{c.rule}, &data, {inner})' for c in candidates)
    return f'''const std = @import("std");
{import_prelude}
const c = @cImport({{@cInclude("stdio.h");}});
{baseline}
{sources}
fn run(comptime function: anytype, data: []const u8, comptime inner_count: usize) usize {{
    var total: usize = 0;
    for (0..inner_count) |iteration| total +%= function(data, @truncate(iteration));
    return total;
}}
pub fn main(init: std.process.Init) !void {{
    var args = init.minimal.args.iterate();
    _ = args.next();
    const mode = args.next() orelse "verify";
    var data: [{size}]u8 = undefined;
    for (&data, 0..) |*value, index| value.* = @truncate(index *% 131 +% 17);
    if (std.mem.eql(u8, mode, "verify")) {{
        const sizes = [_]usize{{0, 1, 2, 3, 4, 7, 8, 15, 31, 64, 257}};
        for (sizes) |n| {{
            const expected = baseline_impl(data[0..n], 17);
            {''.join(f'if (candidate_{x.rule}(data[0..n], 17) != expected) return error.DifferentialMismatch; ' for x in candidates)}
        }}
        _ = c.printf("{{\\\"status\\\":\\\"PASS\\\"}}\\n");
        return;
    }}
    const start = std.Io.Clock.awake.now(init.io).nanoseconds;
    var observable: usize = 0;
    if (std.mem.eql(u8, mode, "baseline")) observable = run(baseline_impl, &data, {inner})
{branches}
    else return error.UnknownCandidate;
    const elapsed: f64 = @floatFromInt(std.Io.Clock.awake.now(init.io).nanoseconds - start);
    const metric = elapsed / @as(f64, @floatFromInt({size * inner}));
    _ = c.printf("{{\\\"metric_ns\\\":%.12f,\\\"observable\\\":%zu}}\\n", metric, observable);
}}
'''


def _zig_benchmark_baseline(
    request: ZigRegionRequest, zig: Path,
) -> tuple[str, str, Path | None]:
    source = request.source.resolve()
    owner = _zig_std_module(zig, source)
    target_module = None if owner else source
    owner = owner or "target"
    function = request.function.split(".")[-1]
    arguments = (
        f"{request.specialization}, bytes, needle"
        if request.specialization else "bytes, needle"
    )
    baseline = (
        "noinline fn baseline_impl(bytes: []const u8, needle: u8) usize {\n"
        f"    return {owner}.{function}({arguments});\n"
        "}\n"
    )
    prelude = "" if target_module is None else 'const target = @import("target");'
    return baseline, prelude, target_module


def _compile_zig(zig: Path, source: Path, output: Path, mode: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    llvm, assembly, obj = output / "module.ll", output / "module.s", output / "module.o"
    command = [str(zig), "build-obj", str(source), "-O", mode, f"-femit-llvm-ir={llvm}", f"-femit-asm={assembly}", f"-femit-bin={obj}"]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"status": "pass" if result.returncode == 0 else "fail", "command": command, "stdout": result.stdout, "stderr": result.stderr, "llvm_ir": str(llvm), "assembly": str(assembly), "object": str(obj)}


def _compile_zig_module(
    zig: Path, wrapper: Path, target: Path, output: Path, mode: str,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    llvm, assembly, obj = output / "module.ll", output / "module.s", output / "module.o"
    command = [
        str(zig), "build-obj", "-O", mode, "--dep", "target",
        f"-Mroot={wrapper}", f"-Mtarget={target}",
        f"-femit-llvm-ir={llvm}", f"-femit-asm={assembly}", f"-femit-bin={obj}",
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"status": "pass" if result.returncode == 0 else "fail", "command": command, "stdout": result.stdout, "stderr": result.stderr, "llvm_ir": str(llvm), "assembly": str(assembly), "object": str(obj)}


def _compile_zig_executable(zig: Path, source: Path, output: Path) -> dict[str, Any]:
    command = [str(zig), "build-exe", str(source), "-O", "ReleaseFast", "-lc", "-femit-bin=" + str(output)]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"status": "pass" if result.returncode == 0 else "fail", "command": command, "stdout": result.stdout, "stderr": result.stderr, "executable": str(output)}


def _compile_zig_executable_module(
    zig: Path, source: Path, target: Path, output: Path,
) -> dict[str, Any]:
    command = [
        str(zig), "build-exe", "-O", "ReleaseFast", "-lc", "--dep", "target",
        f"-Mroot={source}", f"-Mtarget={target}", f"-femit-bin={output}",
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"status": "pass" if result.returncode == 0 else "fail", "command": command, "stdout": result.stdout, "stderr": result.stderr, "executable": str(output)}


def _capabilities(captured: bool, graph: bool, closed: bool, artifacts: dict[str, str]) -> dict[str, LanguageCapability]:
    return {
        "semantic_capture": LanguageCapability(captured, captured, "native Zig module and safety policy captured", artifacts.get("llvm_ir")),
        "information_flow": LanguageCapability(graph, graph, "shared semantic information-flow graph"),
        "candidate_generation": LanguageCapability(closed, closed, "native Zig exact-reduction schedules"),
        "local_proof": LanguageCapability(closed, closed, "Z3 schedule and fixed-bound LLVM refinement"),
        "benchmark": LanguageCapability(closed, closed, "same-executable native Zig paired benchmark"),
        "source_rewrite": LanguageCapability(closed, closed, "native Zig source regeneration; no automatic application"),
        "protocol_equivalence": LanguageCapability(False, False, "allocator, error, defer, atomic, volatile, FFI, and external protocols excluded"),
    }


def _candidate_from_dict(raw: dict[str, Any]) -> ZigCandidate:
    schedule = ReductionSchedule(**raw["schedule"])
    return ZigCandidate(raw["id"], raw["rule"], schedule, raw["source"], raw["source_sha256"])


def _find_zig_root(source: Path) -> Path:
    for parent in (source.parent, *source.parents):
        if (parent / "build.zig.zon").exists() or (parent / "build.zig").exists(): return parent
    return source.parent


def _zig_std_module(zig: Path, source: Path) -> str | None:
    environment = _command([str(zig), "env"])
    match = re.search(r'\.std_dir\s*=\s*"([^"]+)"', environment)
    if not match:
        return None
    try:
        relative = source.resolve().relative_to(Path(match.group(1)).resolve())
    except ValueError:
        return None
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "std":
        return "std"
    return "std." + ".".join(parts)


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
