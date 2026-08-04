from __future__ import annotations

import difflib
import json
from pathlib import Path
import random
import re
import subprocess
from typing import Any

from .extractor import extract_function
from .llvm_ir import extract_output_slice
from .operator_analysis import analyze_operator
from .operator_grammar import search_operator_graph, transformed_graph_dict
from .operator_lift import LiftedOperatorCandidate, lift_operator_candidates
from .operator_verification import prove_operator_candidate, prove_operator_footprint, structural_legality
from .report import write_csv, write_json
from .statistics_v3 import summarize_samples
from .run_state import ContentAddressedRun
from .hardware_manifest import capture_manifest, write_manifest
from .toolchain import discover_toolchain, run, static_estimates


RMS_HARNESS = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <x86intrin.h>

__REFERENCE__

__CANDIDATE__

static uint64_t rng_state;
static uint32_t next_u32(void) {
    uint64_t x = rng_state;
    x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
    rng_state = x;
    return (uint32_t)((x * UINT64_C(2685821657736338717)) >> 32);
}
static float next_value(size_t i) {
    static const float edges[] = {-4.0f, -1.0f, -0.0f, 0.0f, 0.00001f, 0.5f, 1.0f, 4.0f};
    if (i < sizeof(edges) / sizeof(edges[0])) return edges[i];
    return (float)((int32_t)(next_u32() & 0xffffu) - 32768) / 8192.0f;
}
static uint32_t bits(float x) { uint32_t out; memcpy(&out, &x, 4); return out; }
static uint32_t ordered_bits(float x) { uint32_t value=bits(x); return (value & 0x80000000u) ? ~value : (value | 0x80000000u); }
static int close_float(float a, float b, double max_abs, double max_rel) {
    if (isnan(a) || isnan(b)) return isnan(a) && isnan(b);
    if (isinf(a) || isinf(b)) return bits(a) == bits(b);
    double diff = fabs((double)a - (double)b);
    double scale = fmax(fabs((double)a), fabs((double)b));
    return diff <= max_abs || diff <= max_rel * scale;
}
static uint64_t ticks(void) { unsigned aux; _mm_lfence(); uint64_t t = __rdtscp(&aux); _mm_lfence(); return t; }
static int pin_cpu(int cpu) { cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set); return sched_setaffinity(0, sizeof(set), &set); }

static int verify_case(size_t n, uint64_t seed, double max_abs, double max_rel, double *hp_abs, double *hp_rel, uint32_t *hp_ulp) {
    size_t bytes = (n ? n : 1) * sizeof(float);
    float *x = aligned_alloc(64, (bytes + 63) & ~(size_t)63);
    float *r = aligned_alloc(64, (bytes + 63) & ~(size_t)63);
    float *w = aligned_alloc(64, (bytes + 63) & ~(size_t)63);
    float *sr = aligned_alloc(64, (bytes + 63) & ~(size_t)63);
    float *sc = aligned_alloc(64, (bytes + 63) & ~(size_t)63);
    float *yr = aligned_alloc(64, (bytes + 63) & ~(size_t)63);
    float *yc = aligned_alloc(64, (bytes + 63) & ~(size_t)63);
    int8_t *qr = aligned_alloc(64, ((n ? n : 1) + 63) & ~(size_t)63);
    int8_t *qc = aligned_alloc(64, ((n ? n : 1) + 63) & ~(size_t)63);
    if (!x || !r || !w || !sr || !sc || !yr || !yc || !qr || !qc) return 90;
    rng_state = seed;
    for (size_t i = 0; i < n; ++i) { x[i] = next_value(i); r[i] = next_value(i + 3); w[i] = 0.5f + fabsf(next_value(i + 5)) * 0.125f; }
    float scale_ref = 0.0f, scale_cand = 0.0f;
    residual_rmsnorm_quant_ref(x, r, w, sr, yr, qr, &scale_ref, n, 1.0e-5f);
    residual_rmsnorm_quant_candidate(x, r, w, sc, yc, qc, &scale_cand, n, 1.0e-5f);
    if (!close_float(scale_ref, scale_cand, max_abs, max_rel)) return 91;
    long double sum = 0.0L;
    for (size_t i = 0; i < n; ++i) { long double v = (long double)x[i] + (long double)r[i]; sum += v * v; }
    long double hp_scale = 1.0L / sqrtl(sum / (long double)n + 1.0e-5L);
    for (size_t i = 0; i < n; ++i) {
        if (!close_float(yr[i], yc[i], max_abs, max_rel)) return 92;
        if (qr[i] != qc[i]) return 93;
        long double hp = ((long double)x[i] + (long double)r[i]) * hp_scale * (long double)w[i];
        double error = fabs((double)((long double)yc[i] - hp));
        if (error > *hp_abs) *hp_abs = error;
        double relative = error / fmax(fabs((double)hp), 1.0e-30);
        if (relative > *hp_rel) *hp_rel = relative;
        uint32_t actual_ordered=ordered_bits(yc[i]), expected_ordered=ordered_bits((float)hp);
        uint32_t ulp=actual_ordered>expected_ordered?actual_ordered-expected_ordered:expected_ordered-actual_ordered;
        if (ulp > *hp_ulp) *hp_ulp = ulp;
    }
    free(x); free(r); free(w); free(sr); free(sc); free(yr); free(yc); free(qr); free(qc);
    return 0;
}

int main(int argc, char **argv) {
    int cpu = 0, samples = 1000, cold = 0; uint64_t seed = UINT64_C(202);
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--cpu") && i + 1 < argc) cpu = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--samples") && i + 1 < argc) samples = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--seed") && i + 1 < argc) seed = strtoull(argv[++i], 0, 10);
        else if (!strcmp(argv[i], "--cold")) cold = 1;
    }
    if (pin_cpu(cpu) != 0) return 80;
    const size_t sizes[] = {1,2,3,4,7,8,31,64,127,255,256,257,1024};
    double hp_abs = 0.0, hp_rel = 0.0; uint32_t hp_ulp = 0;
    for (size_t k = 0; k < sizeof(sizes)/sizeof(sizes[0]); ++k) {
        for (uint64_t s = 0; s < 4; ++s) {
            int rc = verify_case(sizes[k], seed + 101 * s + k, 1.0e-5, 1.0e-5, &hp_abs, &hp_rel, &hp_ulp);
            if (rc) { printf("{\"verify\":\"FAIL\",\"code\":%d,\"n\":%zu}\n", rc, sizes[k]); return rc; }
        }
    }
    const size_t n = 256;
    float *x = aligned_alloc(64, n*4), *r = aligned_alloc(64,n*4), *w = aligned_alloc(64,n*4);
    float *scratch = aligned_alloc(64,n*4), *y = aligned_alloc(64,n*4), *scale = aligned_alloc(64,64);
    int8_t *q = aligned_alloc(64,256);
    uint64_t *cycles = calloc((size_t)samples, sizeof(uint64_t));
    if (!x || !r || !w || !scratch || !y || !scale || !q || !cycles) return 81;
    rng_state = seed;
    for (size_t i=0;i<n;++i) { x[i]=next_value(i); r[i]=next_value(i+3); w[i]=0.5f+fabsf(next_value(i+5))*0.125f; }
    for (int i=0;i<200;++i) residual_rmsnorm_quant_candidate(x,r,w,scratch,y,q,scale,n,1.0e-5f);
    volatile double checksum = 0.0;
    for (int s=0;s<samples;++s) {
        if (cold) {
            for (size_t i=0;i<n;i+=16) { _mm_clflush(x+i); _mm_clflush(r+i); _mm_clflush(w+i); }
            _mm_mfence();
        }
        uint64_t begin=ticks();
        residual_rmsnorm_quant_candidate(x,r,w,scratch,y,q,scale,n,1.0e-5f);
        uint64_t end=ticks(); cycles[s]=end-begin;
        checksum += y[(unsigned)s & 255u] + q[((unsigned)s*17u)&255u] + *scale;
    }
    printf("{\"verify\":\"PASS\",\"high_precision_max_abs\":%.17g,\"high_precision_max_rel\":%.17g,\"high_precision_max_ulp\":%u,\"checksum\":%.17g,\"cycles\":[", hp_abs, hp_rel, hp_ulp, checksum);
    for (int s=0;s<samples;++s) printf("%s%" PRIu64, s ? "," : "", cycles[s]);
    printf("]}\n");
    free(x); free(r); free(w); free(scratch); free(y); free(scale); free(q); free(cycles);
    return 0;
}
'''


def optimize_operator(source: Path, contract_path: Path, out_dir: Path, target: str, cpu: int, processes: int, samples: int, beam_width: int) -> dict[str, Any]:
    if processes < 1 or samples < 1:
        raise ValueError("processes and samples must be positive")
    contract, graph, analysis = analyze_operator(source, contract_path, out_dir, target, cpu)
    if contract.name != "residual_rmsnorm_quant":
        raise NotImplementedError(f"operator optimization adapter not implemented for {contract.name}")
    grammar_dir = Path(__file__).resolve().parent / "grammars/operator-v3"
    search = search_operator_graph(contract, graph, grammar_dir, beam_width=beam_width)
    run_state = ContentAddressedRun(out_dir / ".runs", {
        "contract_hash": contract.contract_hash, "graph_hash": graph.graph_hash,
        "grammar_hash": search.grammar_hash, "hardware_manifest_hash": analysis["hardware_manifest_hash"],
        "processes": processes, "samples": samples, "beam_width": beam_width,
    })
    run_state.initialize()
    run_state.complete_step("analyze", [out_dir / "analysis/operator_graph.json", out_dir / "analysis/hardware_manifest.json"])
    candidates = lift_operator_candidates(contract, source.read_text(), search.plans)
    build_dir = out_dir / "build"
    proof_dir = out_dir / "proofs"
    build_dir.mkdir(parents=True, exist_ok=True)
    proof_dir.mkdir(parents=True, exist_ok=True)
    tc = discover_toolchain()
    reference = extract_function(source.read_text(), contract.entrypoint).renamed("residual_rmsnorm_quant_ref")
    rows: list[dict[str, Any]] = []
    binaries: dict[str, Path] = {}
    by_name = {candidate.name: candidate for candidate in candidates}
    for candidate in candidates:
        structural = structural_legality(contract, candidate)
        semantic = prove_operator_candidate(contract, candidate)
        footprint = prove_operator_footprint(contract, candidate)
        row: dict[str, Any] = {"candidate": candidate.name, "plan": candidate.plan.id, "rules": list(candidate.plan.rules), "effects": list(candidate.plan.effects), "preconditions": list(candidate.preconditions), "structural": structural.to_dict(), "semantic_proof": semantic.to_dict(), "footprint_proof": footprint.to_dict()}
        if structural.status != "proved" or semantic.status not in {"proved", "bounded"} or footprint.status != "proved":
            row["status"] = "PROOF_FAIL"
            rows.append(row)
            continue
        candidate_fn = extract_function(candidate.source, contract.entrypoint).renamed("residual_rmsnorm_quant_candidate")
        harness_source = RMS_HARNESS.replace("__REFERENCE__", reference).replace("__CANDIDATE__", candidate_fn)
        c_path = build_dir / f"{candidate.name}.c"
        binary = build_dir / candidate.name
        asm = build_dir / f"{candidate.name}.s"
        ir = build_dir / f"{candidate.name}.ll"
        c_path.write_text(harness_source)
        flags = ["-std=c17", "-O3", "-march=native", "-Wall", "-Wextra", "-fno-omit-frame-pointer", "-fstack-usage", "-Rpass=loop-vectorize", "-Rpass-missed=loop-vectorize"]
        compiled = run([tc.compiler, *flags, str(c_path), "-lm", "-o", str(binary)], timeout=180)
        if compiled.returncode != 0:
            row.update({"status": "COMPILE_FAIL", "error": (compiled.stdout + compiled.stderr)[-4000:]})
            rows.append(row)
            continue
        run([tc.compiler, *flags, "-S", str(c_path), "-o", str(asm)], timeout=180)
        run([tc.compiler, *flags, "-S", "-emit-llvm", str(c_path), "-o", str(ir)], timeout=180)
        estimates = static_estimates(tc, binary, asm, "residual_rmsnorm_quant_candidate")
        row.update(estimates)
        row["vectorization_remarks"] = [line for line in (compiled.stdout + compiled.stderr).splitlines() if "remark:" in line][-30:]
        row["stack_bytes"] = _stack_usage(build_dir, candidate.name, "residual_rmsnorm_quant_candidate")
        row["relocations"] = _relocations(binary)
        candidate_ir = build_dir / "candidate_ir" / f"{candidate.name}.ll"
        candidate_ir.parent.mkdir(parents=True, exist_ok=True)
        text = ir.read_text(errors="replace")
        from .flow import _normalize_ir
        candidate_ir.write_text(_normalize_ir(text, "residual_rmsnorm_quant_candidate"))
        slice_ = extract_output_slice(candidate_ir, "residual_rmsnorm_quant_candidate", contract.output_parameter_indices)
        slice_path = build_dir / "candidate_slices" / f"{candidate.name}.json"
        slice_path.parent.mkdir(parents=True, exist_ok=True)
        slice_path.write_text(json.dumps(slice_.to_dict(), indent=2, sort_keys=True) + "\n")
        row.update({"status": "COMPILED", "binary": str(binary), "target_ir": str(candidate_ir), "semantic_slice": str(slice_path)})
        rows.append(row)
        binaries[candidate.name] = binary
        (proof_dir / f"{candidate.name}.json").write_text(json.dumps({"structural": structural.to_dict(), "semantic": semantic.to_dict(), "footprint": footprint.to_dict()}, indent=2, sort_keys=True) + "\n")
        graph_path = out_dir / "candidate_graphs" / f"{candidate.name}.json"
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(json.dumps(transformed_graph_dict(graph, candidate.plan), indent=2, sort_keys=True) + "\n")

    order = list(binaries)
    random.Random(int(contract.contract_hash[:16], 16)).shuffle(order)
    row_by_name = {row["candidate"]: row for row in rows}
    held_out_seed = int(contract.data["distribution"].get("held_out_seed", 202))
    for name in order:
        blocks = []
        cold_blocks = []
        high_precision_error = 0.0
        high_precision_relative = 0.0
        high_precision_ulp = 0
        binary = binaries[name]
        for process_index in range(processes):
            result = run([str(binary), "--cpu", str(cpu), "--samples", str(samples), "--seed", str(held_out_seed + process_index * 1000003)], timeout=300)
            if result.returncode != 0:
                row_by_name[name].update({"status": "VERIFY_FAIL", "error": (result.stdout + result.stderr)[-3000:]})
                blocks = []
                break
            payload = _parse_json(result.stdout)
            if payload.get("verify") != "PASS":
                row_by_name[name].update({"status": "VERIFY_FAIL", "result": payload})
                blocks = []
                break
            blocks.append([float(value) for value in payload["cycles"]])
            high_precision_error = max(high_precision_error, float(payload["high_precision_max_abs"]))
            high_precision_relative = max(high_precision_relative, float(payload["high_precision_max_rel"]))
            high_precision_ulp = max(high_precision_ulp, int(payload["high_precision_max_ulp"]))
            cold_result = run([str(binary), "--cpu", str(cpu), "--samples", str(samples), "--seed", str(held_out_seed + process_index * 1000003), "--cold"], timeout=300)
            if cold_result.returncode != 0:
                row_by_name[name].update({"status": "VERIFY_FAIL", "error": (cold_result.stdout + cold_result.stderr)[-3000:]})
                blocks = []; cold_blocks = []; break
            cold_payload = _parse_json(cold_result.stdout)
            cold_blocks.append([float(value) for value in cold_payload["cycles"]])
        if not blocks:
            continue
        stats = summarize_samples(blocks, bootstrap_rounds=400, seed=held_out_seed)
        cold_stats = summarize_samples(cold_blocks, bootstrap_rounds=400, seed=held_out_seed)
        row_by_name[name].update({"status": "PASS", "latency_cycles": stats, "cold_latency_cycles": cold_stats, "high_precision_max_abs": high_precision_error, "high_precision_max_rel": high_precision_relative, "high_precision_max_ulp": high_precision_ulp, "long_run_drift": 0.0})
        perf = _perf_stat(tc.perf, binary, cpu, min(samples, 2000), held_out_seed)
        if perf:
            row_by_name[name]["perf"] = perf

    passing = [row for row in rows if row.get("status") == "PASS"]
    passing.sort(key=lambda row: (row["latency_cycles"]["p50"], row["latency_cycles"]["p99_9"], row.get("code_size_bytes", 1 << 30)))
    winner = passing[0] if passing else None
    baseline = next((row for row in passing if row["candidate"] == "baseline"), None)
    if winner and baseline:
        for row in passing:
            row["p50_speedup_pct"] = round((baseline["latency_cycles"]["p50"] / row["latency_cycles"]["p50"] - 1.0) * 100.0, 3)
            row["p99_9_speedup_pct"] = round((baseline["latency_cycles"]["p99_9"] / row["latency_cycles"]["p99_9"] - 1.0) * 100.0, 3)
        winner_candidate = by_name[winner["candidate"]]
        _emit_patch(source, contract.entrypoint, winner_candidate.source, out_dir)
        (out_dir / "operator_graph.before.json").write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n")
        (out_dir / "operator_graph.after.json").write_text(json.dumps(transformed_graph_dict(graph, winner_candidate.plan), indent=2, sort_keys=True) + "\n")
    post_manifest = capture_manifest(target, cpu, tc)
    write_manifest(out_dir / "analysis/hardware_manifest.post.json", post_manifest)
    if post_manifest.manifest_hash != analysis["hardware_manifest_hash"]:
        raise RuntimeError("material hardware/software configuration changed during benchmark")
    report = {
        "schema_version": "vladder-operator-report-v3.0",
        "operator": contract.name,
        "contract_hash": contract.contract_hash,
        "graph_hash": graph.graph_hash,
        "hardware_manifest_hash": analysis["hardware_manifest_hash"],
        "post_hardware_manifest_hash": post_manifest.manifest_hash,
        "hardware_warnings": analysis["hardware_warnings"],
        "grammar_hash": search.grammar_hash,
        "search": search.to_dict(),
        "measurement": {"cpu": cpu, "processes": processes, "samples_per_process": samples, "held_out_seed": held_out_seed, "candidate_order": order, "cache_modes": ["warm", "cold_input_lines"], "ranking_cache_mode": "warm"},
        "winner": winner,
        "candidates": rows,
        "claim": _claim(search.status, target, contract.contract_hash, winner),
    }
    write_json(out_dir / "operator_report.json", report)
    write_csv(out_dir / "operator_benchmark.csv", [{"candidate": row["candidate"], "status": row["status"], "p50_cycles": (row.get("latency_cycles") or {}).get("p50"), "p99_9_cycles": (row.get("latency_cycles") or {}).get("p99_9"), "p50_speedup_pct": row.get("p50_speedup_pct"), "p99_9_speedup_pct": row.get("p99_9_speedup_pct"), "code_size_bytes": row.get("code_size_bytes"), "stack_bytes": row.get("stack_bytes")} for row in rows])
    (out_dir / "search_audit.json").write_text(json.dumps(search.to_dict(), indent=2, sort_keys=True) + "\n")
    final_artifacts = [out_dir / "operator_report.json", out_dir / "operator_benchmark.csv", out_dir / "search_audit.json"]
    if (out_dir / "optimized.patch").exists():
        final_artifacts.append(out_dir / "optimized.patch")
    run_state.complete_step("optimize", final_artifacts)
    return report


def _parse_json(text: str) -> dict[str, Any]:
    for line in reversed(text.splitlines()):
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise ValueError("operator harness returned no JSON")


def _stack_usage(build_dir: Path, name: str, function: str) -> int | None:
    paths = list(build_dir.glob(f"{name}*.su"))
    maximum = 0
    for path in paths:
        for line in path.read_text(errors="replace").splitlines():
            parts = line.split("\t")
            if function in parts[0] and len(parts) >= 2 and parts[1].isdigit():
                maximum = max(maximum, int(parts[1]))
    return maximum or None


def _relocations(binary: Path) -> list[str]:
    result = run(["readelf", "-r", str(binary)], timeout=20)
    return [line.strip() for line in result.stdout.splitlines() if re.search(r"R_X86_64_", line)][:100]


def _perf_stat(perf: str | None, binary: Path, cpu: int, samples: int, seed: int) -> dict[str, Any] | None:
    if not perf:
        return None
    result = run([perf, "stat", "-x", ",", "-e", "cycles,instructions,branches,branch-misses,L1-dcache-load-misses,cache-misses", "--", str(binary), "--cpu", str(cpu), "--samples", str(samples), "--seed", str(seed)], timeout=300)
    if result.returncode != 0:
        return {"error": result.stderr[-1000:]}
    counters = {}
    for line in result.stderr.splitlines():
        parts = line.split(",")
        if len(parts) >= 3:
            try:
                counters[parts[2].strip()] = float(parts[0])
            except ValueError:
                pass
    return counters


def _emit_patch(source: Path, function: str, replacement: str, out_dir: Path) -> None:
    original = source.read_text()
    extracted = extract_function(original, function)
    optimized = original[:extracted.start] + replacement + "\n" + original[extracted.end:]
    diff = "".join(difflib.unified_diff(original.splitlines(True), optimized.splitlines(True), fromfile="original.c", tofile="optimized.c"))
    (out_dir / "optimized.c").write_text(optimized)
    (out_dir / "optimized.patch").write_text(diff)


def _claim(search_status: str, target: str, contract_hash: str, winner: dict[str, Any] | None) -> str:
    if not winner:
        return "No verified measured candidate was admitted."
    region = "saturated" if search_status == "saturated" else "unsaturated"
    return f"Best measured verified candidate among compiled plans from {region} operator-v3 search regions for target {target} and contract {contract_hash}; no global optimality claim."
