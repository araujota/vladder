from __future__ import annotations

import argparse
import difflib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from textwrap import dedent
import time
import yaml

from . import __version__
from .consent import (
    AGENT_EXPERIENCE_REVIEW, CANONICAL_TRAINING_DATA, CONSENT_SCOPES,
    load_consent, record_review_request, require_consent, set_consent,
)
from .contribution_transport import DEFAULT_CONTRIBUTION_BASE, probe_contribution_service
from .candidates import Candidate, generate_candidates
from .automatic import inspect_automatic_region
from .cpp_regions import inspect_cpp_matrix, inspect_cpp_region, isolate_cpp_region, optimize_cpp_region
from .cpp_adapters import generate_cpp_adapter_bundle
from .agent_workflow import initialize_workflow_manifest, query_lineage, run_agent_workflow, summarize_report
from .capabilities import load_registry
from .diagnostics import doctor_report
from .extractor import extract_function
from .flow import analyze_ir, build_flow_graph, emit_function_ir, emit_target_ir, write_flow_artifacts
from .grammar_search import search_candidates
from .llvm_ir import extract_output_slice
from .llm_lifter import zero_trust_llm_lift
from .lifetime_workflow import analyze_lifetime_flow, evaluate_lifetime_corpus, synthesize_lifetime_flow
from .lowering import LoweringEngine, LoweringMode, LoweringRequest, validate_lowering_registry
from .kernel_lab_v6 import run_quantized_kernel_lab
from .memory_proofs import prove_memory_safety
from .semantic_smt import emit_semantic_smt
from .operator_analysis import analyze_operator
from .operator_optimize import optimize_operator
from .hft_optimize import optimize_hft_pipeline
from .llama_integration import benchmark_llama_integration, benchmark_llama_model, extract_llama_decode_graph, profile_llama_decode_graph, profile_llama_projection_path
from .pipeline_v4 import analyze_pipeline_v4, optimize_pipeline_v4
from .projection_v5 import analyze_projection_v5, synthesize_projection_v5, transform_projection_layout_v5
from .q4k_capture import capture_active_q4k_path
from .q4k_v7 import reconstruct_q4k_v7
from .q4k_parity import run_q4k_parity
from .q4k_sibling import synthesize_q4k_siblings
from .q4k_model_verify import verify_regenerated_q4k_model
from .q4k_v8 import run_q4k_v8
from .weight_traversal_v9 import run_weight_traversal_v9
from .portfolio_v6 import rank_portfolio
from .paired_benchmark import compose_application_cost, compose_benchmark_effects, run_paired_benchmark
from .proofs import proof_to_dict, prove_candidate, write_smt2_stub
from .report import write_csv, write_html, write_json
from .replacement import verify_applied_replacement
from .review_workflow import create_campaign_review_template, create_review_template, submit_review, validate_review
from .training_workflow import (
    create_training_bundle_from_prior, create_training_template, export_all_training_bundles_from_prior,
    submit_training_bundle, sync_all_training_bundles_from_prior, validate_training_bundle,
)
from .model_training_data import ingest_model_training_bundle, write_graph_learning_jsonl
from .schema_registry import list_artifact_schemas, validate_artifact
from .toolchain import alive2_check, compile_c, compiler_version, cpu_flags, cpu_model, discover_toolchain, emit_alive2_ir, run, static_estimates, tool_version
from .sksf_workflow import synthesize_kernel_v6, validate_attribution_v6
from .skill_tools import install_skill, validate_skill
from .verification_policy import VerificationPolicy, evaluate_promotion
from .shader_workflow import gpu_support_matrix, inspect_shader, synthesize_shader
from .gpu_workflow import (
    capture_gpu_workflow,
    gpu_support_matrix as heterogeneous_gpu_support_matrix,
    rank_gpu_workflow,
    synthesize_gpu_workflow,
    verify_gpu_workflow,
)
from .cuda_runtime import probe_cuda_architecture, run_cuda_artifact
from .cuda_synthesis import optimize_cuda_pointwise, synthesize_cuda_pointwise
from .device_topology import (
    emit_dma_protocol_template,
    emit_presentation_protocol_template,
    emit_vulkan_queue_protocol_template,
    probe_device_topology,
    probe_drm_presentation,
    probe_vulkan_capabilities,
)
from .device_protocol import verify_device_protocol
from .gpu_ir import load_gpu_architecture
from .heterogeneous_plan import audit_heterogeneous_project, rank_heterogeneous_plans, synthesize_heterogeneous_plans
from .prior_workflow import (
    evaluate_prior, evaluate_prior_generalization, generate_prior_dataset, ingest_prior_dataset, prior_support,
    initialize_prior_manifest, initialize_prior_training_template, materialize_prior_dataset_template,
    recommend_prior, run_prior_workflow, select_prior,
    split_prior_dataset, train_prior, validate_prior_dataset,
)
from .state_protocol import verify_state_protocol
from .resource_protocol import protocol_template
from .system_closure import run_system_closure
from .whole_build import WholeBuildIndex, run_cross_tu_closure
from .orchestrator import (
    OptimizationRequest as OrchestratorRequest,
    execute_remote_adapter,
    format_terminal,
    run_optimization,
    run_portfolio,
    resume_optimization,
    verify_remote_result,
    write_plan,
)
from .rust_adapter import (
    RustRegionRequest,
    audit_rust_regions,
    inspect_rust_region,
    isolate_rust_region,
    optimize_rust_region,
    rust_support_report,
    synthesize_rust_region,
)
from .zig_adapter import (
    ZigRegionRequest, audit_zig_regions, inspect_zig_region, isolate_zig_region,
    optimize_zig_region, synthesize_zig_region, zig_support_report,
)
from .julia_adapter import (
    JuliaRegionRequest, audit_julia_regions, inspect_julia_region, isolate_julia_region,
    optimize_julia_region, synthesize_julia_region, julia_support_report,
)
from .deep_audit import audit_expert_manifest, audit_neuralfusion_evidence_readonly
from .deep_benchmark import benchmark_deep_candidate, rank_deep_grammar
from .deep_grammar import load_deep_grammar, search_deep_grammar
from .deep_ir import DeepKernelContract, build_deep_realization_graph
from .deep_lowering import emit_deep_candidate
from .deep_proof import prove_deep_candidate
from .dataflow_audit import audit_dataflow_manifest
from .dataflow_grammar import load_bounded_dataflow_grammar
from .dataflow_ir import BoundedDataflowContract, build_bounded_dataflow_graph
from .dataflow_lowering import emit_dataflow_cpp
from .dataflow_multilang import emit_dataflow_native
from .dataflow_proof import prove_dataflow_candidate


HARNESS = r"""
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <stddef.h>
#include <immintrin.h>

__attribute__((noinline))
void transform_ref(float *dst, const float *src, size_t n);

__CANDIDATE_SOURCE__

static uint64_t rng_state = 0x9e3779b97f4a7c15ull;

static uint32_t next_u32(void) {
    uint64_t x = rng_state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    rng_state = x;
    return (uint32_t)((x * 2685821657736338717ull) >> 32);
}

static float next_float(void) {
    uint32_t r = next_u32();
    int bucket = (int)(r & 15u);
    if (bucket == 0) return -2.0f;
    if (bucket == 1) return -1.0f;
    if (bucket == 2) return 0.0f;
    if (bucket == 3) return 1.0f;
    if (bucket == 4) return 2.0f;
    float unit = (float)((int)(r & 0xffffu) - 32768) / 8192.0f;
    return unit;
}

static void fill_src(float *src, size_t n) {
    rng_state = 0x123456789abcdef0ull ^ (uint64_t)n;
    for (size_t i = 0; i < n; ++i) src[i] = next_float();
}

static void fill_dst(float *dst, size_t n) {
    for (size_t i = 0; i < n; ++i) dst[i] = -777.0f;
}

static uint32_t bits(float x) {
    uint32_t out;
    memcpy(&out, &x, sizeof(out));
    return out;
}

static int same_float(float a, float b) {
    if (isnan(a) && isnan(b)) return 1;
    return bits(a) == bits(b);
}

static int pin_cpu(int cpu) {
    if (cpu < 0) return 0;
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    return sched_setaffinity(0, sizeof(set), &set);
}

static double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (double)ts.tv_sec * 1000000000.0 + (double)ts.tv_nsec;
}

static void flush_cache(char *buf, size_t len) {
    volatile char sink = 0;
    for (size_t i = 0; i < len; i += 64) sink ^= buf[i];
    if (sink == 123) fprintf(stderr, "cache sink: %d\n", sink);
}

static double checksum(const float *dst, size_t n) {
    double sum = 0.0;
    for (size_t i = 0; i < n; i += 97) sum += dst[i];
    return sum;
}

static int compare_double(const void *lhs, const void *rhs) {
    double a = *(const double *)lhs;
    double b = *(const double *)rhs;
    return (a > b) - (a < b);
}

static int verify_nonoverlap(size_t n) {
    float *src = aligned_alloc(64, (n + 32) * sizeof(float));
    float *ref = aligned_alloc(64, (n + 32) * sizeof(float));
    float *cand = aligned_alloc(64, (n + 32) * sizeof(float));
    if (!src || !ref || !cand) return 100;
    fill_src(src, n + 32);
    fill_dst(ref, n + 32);
    fill_dst(cand, n + 32);
    transform_ref(ref, src, n);
    transform_candidate(cand, src, n);
    for (size_t i = 0; i < n; ++i) {
        if (!same_float(ref[i], cand[i])) {
            fprintf(stderr, "mismatch nonoverlap n=%zu i=%zu ref=%a cand=%a\n", n, i, ref[i], cand[i]);
            free(src); free(ref); free(cand);
            return 101;
        }
    }
    free(src); free(ref); free(cand);
    return 0;
}

static int verify_inplace(size_t n) {
    float *ref = aligned_alloc(64, (n + 32) * sizeof(float));
    float *cand = aligned_alloc(64, (n + 32) * sizeof(float));
    if (!ref || !cand) return 102;
    fill_src(ref, n + 32);
    memcpy(cand, ref, (n + 32) * sizeof(float));
    transform_ref(ref, ref, n);
    transform_candidate(cand, cand, n);
    for (size_t i = 0; i < n; ++i) {
        if (!same_float(ref[i], cand[i])) {
            fprintf(stderr, "mismatch inplace n=%zu i=%zu ref=%a cand=%a\n", n, i, ref[i], cand[i]);
            free(ref); free(cand);
            return 103;
        }
    }
    free(ref); free(cand);
    return 0;
}

static int verify_overlap(size_t n) {
    float *refbuf = aligned_alloc(64, (n + 64) * sizeof(float));
    float *candbuf = aligned_alloc(64, (n + 64) * sizeof(float));
    if (!refbuf || !candbuf) return 104;
    fill_src(refbuf, n + 64);
    memcpy(candbuf, refbuf, (n + 64) * sizeof(float));
    transform_ref(refbuf + 1, refbuf, n);
    transform_candidate(candbuf + 1, candbuf, n);
    for (size_t i = 0; i < n + 1; ++i) {
        if (!same_float(refbuf[i], candbuf[i])) {
            fprintf(stderr, "mismatch overlap n=%zu i=%zu ref=%a cand=%a\n", n, i, refbuf[i], candbuf[i]);
            free(refbuf); free(candbuf);
            return 105;
        }
    }
    free(refbuf); free(candbuf);
    return 0;
}

static int verify_all(int assume_no_alias) {
    const size_t sizes[] = {0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 63, 64, 127, 257, 1024, 4099};
    const size_t count = sizeof(sizes) / sizeof(sizes[0]);
    for (size_t i = 0; i < count; ++i) {
        int rc = verify_nonoverlap(sizes[i]);
        if (rc) return rc;
        if (!assume_no_alias) {
            rc = verify_inplace(sizes[i]);
            if (rc) return rc;
            rc = verify_overlap(sizes[i]);
            if (rc) return rc;
        }
    }
    return 0;
}

static int bench(size_t n, int reps, int inner, int cpu, int flush) {
    if (pin_cpu(cpu) != 0) {
        fprintf(stderr, "warning: sched_setaffinity failed: %s\n", strerror(errno));
    }
    float *src = aligned_alloc(64, (n + 64) * sizeof(float));
    float *dst = aligned_alloc(64, (n + 64) * sizeof(float));
    char *cache = aligned_alloc(64, 64 * 1024 * 1024);
    if (!src || !dst || !cache) return 111;
    fill_src(src, n + 64);
    fill_dst(dst, n + 64);
    memset(cache, 1, 64 * 1024 * 1024);
    for (int i = 0; i < 8; ++i) transform_candidate(dst, src, n);

    double *samples = calloc((size_t)reps, sizeof(double));
    if (!samples) return 112;
    double guard = 0.0;
    for (int r = 0; r < reps; ++r) {
        if (flush) flush_cache(cache, 64 * 1024 * 1024);
        double start = now_ns();
        for (int k = 0; k < inner; ++k) {
            transform_candidate(dst, src, n);
        }
        double end = now_ns();
        samples[r] = (end - start) / ((double)n * (double)inner);
        guard += checksum(dst, n);
    }
    double mean = 0.0;
    for (int r = 0; r < reps; ++r) mean += samples[r];
    mean /= (double)reps;
    double var = 0.0;
    for (int r = 0; r < reps; ++r) {
        double d = samples[r] - mean;
        var += d * d;
    }
    double stdev = reps > 1 ? sqrt(var / (double)(reps - 1)) : 0.0;
    double ci95 = reps > 1 ? 1.96 * stdev / sqrt((double)reps) : 0.0;
    qsort(samples, (size_t)reps, sizeof(double), compare_double);
    double median = reps % 2 ? samples[reps / 2] : (samples[reps / 2 - 1] + samples[reps / 2]) * 0.5;
    int trim = reps >= 10 ? reps / 10 : 0;
    double trimmed = 0.0;
    for (int r = trim; r < reps - trim; ++r) trimmed += samples[r];
    trimmed /= (double)(reps - 2 * trim);
    printf("{\"verify\":\"PASS\",\"n\":%zu,\"reps\":%d,\"inner\":%d,\"ns_per_item\":%.9f,\"mean_ns_per_item\":%.9f,\"median_ns_per_item\":%.9f,\"trimmed_mean_ns_per_item\":%.9f,\"stdev_ns_per_item\":%.9f,\"ci95_ns_per_item\":%.9f,\"checksum\":%.17g}\n",
           n, reps, inner, median, mean, median, trimmed, stdev, ci95, guard);
    free(samples); free(src); free(dst); free(cache);
    return 0;
}

int main(int argc, char **argv) {
    size_t n = 1048576;
    int reps = 25;
    int inner = 8;
    int cpu = 0;
    int assume_no_alias = 0;
    int flush = 0;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--n") && i + 1 < argc) n = (size_t)strtoull(argv[++i], 0, 10);
        else if (!strcmp(argv[i], "--reps") && i + 1 < argc) reps = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--inner") && i + 1 < argc) inner = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--cpu") && i + 1 < argc) cpu = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--assume-no-alias")) assume_no_alias = 1;
        else if (!strcmp(argv[i], "--flush-cache")) flush = 1;
    }
    int rc = verify_all(assume_no_alias);
    if (rc) {
        printf("{\"verify\":\"FAIL\",\"code\":%d}\n", rc);
        return rc;
    }
    return bench(n, reps, inner, cpu, flush);
}
"""


def _write_candidate_source(path: Path, ref_source: str, candidate: Candidate) -> None:
    source = HARNESS.replace("__CANDIDATE_SOURCE__", ref_source + "\n\n" + candidate.source)
    path.write_text(source)


def _parse_json_line(text: str) -> dict[str, object]:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise ValueError("benchmark output did not contain a JSON result")


def _candidate_patch(original_source: str, function_start: int, function_end: int, replacement_fn: str, function: str) -> tuple[str, str]:
    replacement = replacement_fn.replace("transform_candidate", function)
    optimized = original_source[:function_start] + replacement.strip() + "\n" + original_source[function_end:]
    if "__m256" in replacement or "__m512" in replacement:
        if "#include <immintrin.h>" not in optimized:
            include_match = list(re.finditer(r"^\s*#\s*include\s+[<\"].*[>\"]\s*$", optimized, re.MULTILINE))
            insert_at = include_match[-1].end() if include_match else 0
            optimized = optimized[:insert_at] + "\n#include <immintrin.h>" + optimized[insert_at:]
    diff = "".join(
        difflib.unified_diff(
            original_source.splitlines(keepends=True),
            optimized.splitlines(keepends=True),
            fromfile="original.c",
            tofile="optimized.c",
        )
    )
    return optimized, diff


def _run_perf(perf: str | None, binary: Path, args: list[str]) -> dict[str, object] | None:
    if not perf:
        return None
    cmd = [
        perf,
        "stat",
        "-x",
        ",",
        "-e",
        "cycles,instructions,branches,branch-misses,cache-misses",
        "--",
        str(binary),
        *args,
    ]
    result = run(cmd, timeout=180)
    if result.returncode != 0:
        return {"error": result.stderr.strip()[:1000]}
    counters: dict[str, object] = {}
    for line in result.stderr.splitlines():
        parts = line.split(",")
        if len(parts) >= 3 and parts[0].strip():
            try:
                counters[parts[2].strip()] = float(parts[0].strip())
            except ValueError:
                pass
    return counters


def _flatten_report_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    flattened = []
    for row in rows:
        item = dict(row)
        proof = item.get("proof")
        if isinstance(proof, dict):
            item["proof_status"] = proof.get("status")
        flattened.append(item)
    return flattened


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _static_prune(rows: list[dict[str, object]], binaries: dict[str, Path], graph_mode: bool) -> None:
    if not graph_mode:
        return
    baseline = next((r for r in rows if r.get("candidate") == "baseline_o3"), None)
    base_rt = _as_float((baseline or {}).get("llvm_mca_block_rthroughput"))
    if not base_rt or base_rt <= 0:
        return
    for row in rows:
        name = str(row.get("candidate", ""))
        if name == "baseline_o3" or row.get("status") != "COMPILED":
            continue
        if "automatic-region" in row.get("tags", []):
            continue
        rt = _as_float(row.get("llvm_mca_block_rthroughput"))
        if rt and rt > base_rt * 1.35:
            row["status"] = "STATIC_PRUNED"
            row["prune_reason"] = f"llvm-mca throughput {rt:.3f} > 1.35x baseline {base_rt:.3f}"
            binaries.pop(name, None)


def optimize_c_kernel(args: argparse.Namespace) -> int:
    policy = VerificationPolicy(args.verification_policy)
    if policy is VerificationPolicy.STRICT:
        args.alive2 = True
    source_path = Path(args.source).resolve()
    out_dir = Path(args.out_dir).resolve()
    build_dir = out_dir / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    proof_dir = out_dir / "proofs"
    alive2_dir = out_dir / "alive2"
    proof_dir.mkdir(parents=True, exist_ok=True)

    original_source = source_path.read_text()
    extracted = extract_function(original_source, args.function)
    registry = load_registry()
    tc = discover_toolchain()
    flags = cpu_flags()
    ir_info = emit_target_ir(tc, source_path, out_dir / "analysis", args.function)
    ir_slice = analyze_ir(ir_info, args.function)
    graph = build_flow_graph(extracted, (ir_info.get("stats") if isinstance(ir_info, dict) else {}) or {}, ir_slice)
    write_flow_artifacts(out_dir, graph, ir_info, ir_slice)
    semantic_smt = emit_semantic_smt(graph, out_dir / "analysis" / "semantic_model.smt2")
    search = None
    llm_lift = None
    if args.graph_inner_loop:
        grammar_dir = Path(__file__).resolve().parent / "grammars"
        search = search_candidates(extracted, graph, flags, args.assume_no_alias, grammar_dir, args.search_nodes, args.search_ms)
        candidates = search.candidates
        if args.llm_lift:
            llm_lift = zero_trust_llm_lift(extracted.source, graph, tc, out_dir / "llm_lift", args.llm_rounds)
            if llm_lift.candidate is not None:
                candidates.append(llm_lift.candidate)
    else:
        candidates = generate_candidates(extracted, flags, args.assume_no_alias)
    ref_source = extracted.renamed("transform_ref")
    command = " ".join(shlex.quote(part) for part in sys.argv)

    rows: list[dict[str, object]] = []
    compiled: dict[str, tuple[Candidate, Path]] = {}
    baseline_ns = None

    print(f"vLadder: compiler={compiler_version(tc.compiler)}")
    print(f"vLadder: generated {len(candidates)} candidates")

    bench_args = [
        "--n",
        str(args.n),
        "--reps",
        str(args.reps),
        "--inner",
        str(args.inner),
        "--cpu",
        str(args.cpu),
    ]
    if args.assume_no_alias:
        bench_args.append("--assume-no-alias")
    if args.flush_cache:
        bench_args.append("--flush-cache")

    binaries: dict[str, Path] = {}
    row_by_name: dict[str, dict[str, object]] = {}

    for candidate in candidates:
        c_path = build_dir / f"{candidate.name}.c"
        bin_path = build_dir / candidate.name
        asm_path = build_dir / f"{candidate.name}.s"
        ir_path = build_dir / f"{candidate.name}.ll"
        _write_candidate_source(c_path, ref_source, candidate)
        ok, build_output = compile_c(tc, c_path, bin_path, candidate.cflags, asm_path, ir_path)
        row: dict[str, object] = {
            "candidate": candidate.name,
            "tags": list(candidate.tags),
            "requires_no_alias": candidate.requires_no_alias,
            "cflags": list(candidate.cflags),
        }
        proof = prove_candidate(extracted, candidate)
        row["proof"] = proof_to_dict(proof)
        memory_proof = prove_memory_safety(graph, candidate, args.assume_no_alias)
        row["memory_proof"] = memory_proof.to_dict()
        write_smt2_stub(proof_dir / f"{candidate.name}.smt2", proof)
        (proof_dir / f"{candidate.name}.memory.smt2").write_text(memory_proof.smt2)
        if memory_proof.status != "proved":
            row.update({"status": "MEMORY_PROOF_FAIL"})
            rows.append(row)
            continue
        if proof.status != "PROVED" and not args.allow_unproved:
            row.update({"status": "PROOF_FAIL"})
            rows.append(row)
            continue
        if not ok:
            row.update({"status": "COMPILE_FAIL", "error": build_output[-2000:]})
            rows.append(row)
            continue

        candidate_ir = build_dir / "candidate_ir" / f"{candidate.name}.ll"
        emit_function_ir(ir_path, candidate_ir, "transform_candidate")
        candidate_slice = extract_output_slice(candidate_ir, "transform_candidate")
        candidate_slice_path = build_dir / "candidate_slices" / f"{candidate.name}.json"
        candidate_slice_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(candidate_slice_path, candidate_slice.to_dict())
        row["target_ir"] = str(candidate_ir)
        row["semantic_slice"] = str(candidate_slice_path)

        estimates = static_estimates(tc, bin_path, asm_path)
        row.update(estimates)
        if args.alive2:
            proof_ir = build_dir / "alive2_ir" / f"{candidate.name}.ll"
            proof_flags = candidate.cflags + (("-DVLADDER_PROOF",) if candidate.proof == "structural_loop_hint" else ())
            proof_ir_ok, proof_ir_output = emit_alive2_ir(tc, c_path, proof_ir, proof_flags)
            if proof_ir_ok:
                row["alive2"] = alive2_check(tc, proof_ir, alive2_dir, candidate.name)
                row["alive2"]["proof_ir"] = str(proof_ir)
                row["alive2"]["proof_ir_policy"] = "-O1 -fno-vectorize -fno-slp-vectorize -fno-unroll-loops; candidate arithmetic flags preserved" + ("; VLADDER_PROOF suppresses the nonsemantic source scheduling directive" if candidate.proof == "structural_loop_hint" else "")
            else:
                row["alive2"] = {"status": "error", "reason": proof_ir_output[-2000:]}
        row["status"] = "COMPILED"
        rows.append(row)
        row_by_name[candidate.name] = row
        compiled[candidate.name] = (candidate, c_path)
        binaries[candidate.name] = bin_path

    _static_prune(rows, binaries, args.graph_inner_loop)

    warmup_args = [
        "--n",
        str(args.n),
        "--reps",
        "3",
        "--inner",
        str(max(1, min(args.inner, 4))),
        "--cpu",
        str(args.cpu),
    ]
    if args.assume_no_alias:
        warmup_args.append("--assume-no-alias")
    for name, bin_path in binaries.items():
        subprocess.run([str(bin_path), *warmup_args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)

    for candidate in candidates:
        if candidate.name not in binaries:
            continue
        bin_path = binaries[candidate.name]
        row = row_by_name[candidate.name]
        result = subprocess.run([str(bin_path), *bench_args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240)
        if result.returncode != 0:
            row.update({"status": "VERIFY_OR_BENCH_FAIL", "error": (result.stdout + result.stderr)[-2000:]})
            continue
        try:
            data = _parse_json_line(result.stdout)
        except Exception as exc:
            row.update({"status": "PARSE_FAIL", "error": str(exc), "raw": result.stdout[-1000:]})
            continue
        row.update(data)
        row["status"] = "PASS"
        if args.perf:
            perf_data = _run_perf(tc.perf, bin_path, bench_args)
            if perf_data:
                row["perf"] = perf_data
        if candidate.name == "baseline_o3":
            baseline_ns = float(row["ns_per_item"])
        formal = ((row.get("proof") or {}).get("status") if isinstance(row.get("proof"), dict) else None)
        alive_status = ((row.get("alive2") or {}).get("status") if isinstance(row.get("alive2"), dict) else None)
        row["verification_tier"] = "proved" if formal == "PROVED" or alive_status == "correct" else "tested"
        print(f"  {candidate.name}: {row['status']} {float(row['ns_per_item']):.6f} ns/item")

    if baseline_ns is None:
        raise RuntimeError("baseline_o3 did not compile and pass verification")

    for row in rows:
        if row.get("status") == "PASS" and "ns_per_item" in row:
            speedup = (baseline_ns / float(row["ns_per_item"]) - 1.0) * 100.0
            row["speedup_vs_baseline_pct"] = round(speedup, 3)
            row["ns_per_item"] = round(float(row["ns_per_item"]), 9)
            row["ci95_ns_per_item"] = round(float(row.get("ci95_ns_per_item", 0.0)), 9)

    passing = [r for r in rows if r.get("status") == "PASS"]
    passing.sort(key=lambda r: (float(r["ns_per_item"]), int(r.get("code_size_bytes", 1 << 30)), int(r.get("instruction_count", 1 << 30))))
    winner = passing[0] if passing else None
    promotion = evaluate_promotion(winner, policy, args.min_speedup_pct)
    promoted_patch = None

    if winner:
        if str(winner["candidate"]) == "baseline_o3":
            winner["optimality"] = "baseline_best"
        elif search and search.status == "saturated_optimal":
            winner["optimality"] = "best_measured_saturated_grammar"
        else:
            winner["optimality"] = "best_found"
        winner["promotion"] = promotion.to_dict()
        if promotion.promotable:
            winner_candidate, _winner_c_path = compiled[str(winner["candidate"])]
            optimized, patch = _candidate_patch(original_source, extracted.start, extracted.end, winner_candidate.source, args.function)
            (out_dir / "optimized.c").write_text(optimized)
            (out_dir / "optimized.patch").write_text(patch)
            winner["patch"] = "optimized.patch"
            promoted_patch = "optimized.patch"

    report = {
        "source": str(source_path),
        "function": args.function,
        "generated_at_unix": int(time.time()),
        "command": command,
        "cpu_model": cpu_model(),
        "cpu_flags_subset": sorted(f for f in flags if f in {"avx2", "avx512f", "avx512vl", "fma", "sse4_2"}),
        "compiler": compiler_version(tc.compiler),
        "vladder": {
            "grammar_version": registry.version,
            "grammar_sha256": registry.sha256,
            "verification_policy": policy.value,
            "minimum_speedup_pct": args.min_speedup_pct,
        },
        "toolchain": {
            "compiler": tc.compiler,
            "llvm_mca": tc.llvm_mca,
            "alive_tv": tc.alive_tv,
            "perf": tc.perf,
        },
        "tool_versions": {
            "alive_tv": tool_version(tc.alive_tv),
            "llvm_mca": tool_version(tc.llvm_mca),
        },
        "assume_no_alias": args.assume_no_alias,
        "inner_loop": "information_flow_graph" if args.graph_inner_loop else "source_template",
        "flow_shape": {
            "family": graph.family,
            "canonical": graph.canonical,
            "invariants": graph.invariants,
            "grammar": graph.grammar,
        },
        "semantic_smt": semantic_smt.to_dict(),
        "grammar_search": search.metadata() if search else None,
        "llm_lift": llm_lift.metadata() if llm_lift else {"status": "disabled"},
        "benchmark": {
            "n": args.n,
            "reps": args.reps,
            "inner": args.inner,
            "cpu": args.cpu,
            "flush_cache": args.flush_cache,
        },
        "baseline_ns_per_item": round(baseline_ns, 9),
        "winner": winner,
        "promotion": promotion.to_dict(),
        "promoted_patch": promoted_patch,
        "candidates": rows,
        "verification_summary": "All ranked candidates passed randomized, edge-size, and differential output checks.",
        "proof_summary": "Ranked candidates have schema-level equivalence proofs where supported; proof records are stored per candidate.",
        "notes": [
            "LLVM IR and llvm-mca output are produced when Clang/llvm-mca are installed.",
            "Proofs are schema-level for the implemented rewrite families, not general C/LLVM equivalence proofs.",
            "SIMD restrict candidates are generated only with --assume-no-alias.",
        ],
    }
    write_json(out_dir / "perf.json", report)
    write_csv(out_dir / "benchmark.csv", _flatten_report_rows(rows))
    write_html(out_dir / "report.html", report)
    print(f"vLadder: winner={winner['candidate'] if winner else 'none'} promoted={promotion.promotable}")
    print(f"vLadder: wrote {out_dir}")
    return 0


def doctor_command(args: argparse.Namespace) -> int:
    report = doctor_report(strict=args.strict)
    output = json.dumps(report, indent=2, sort_keys=True)
    print(output)
    if args.out:
        Path(args.out).resolve().write_text(output + "\n")
    return 0 if report["status"] == "pass" else 1


def release_command(args: argparse.Namespace) -> int:
    from .release_readiness import evaluate_release_readiness, refresh_online_release_readiness, write_release_readiness

    if args.reuse_local_report:
        if not args.online:
            raise ValueError("--reuse-local-report requires --online")
        report = refresh_online_release_readiness(json.loads(Path(args.reuse_local_report).read_text()), Path(args.root))
    else:
        report = evaluate_release_readiness(
            Path(args.root), execute=args.execute, online=args.online,
            work_directory=Path(args.work_dir) if args.work_dir else None,
        )
    output = Path(args.out)
    write_release_readiness(report, output)
    target = report["targets"][args.require_target]
    print(
        "vLadder release: "
        f"target={args.require_target} ready={str(target['ready']).lower()} "
        f"blockers={target['blocker_count']}"
    )
    for blocker in target["blockers"]:
        print(f"  - {blocker}")
    print(f"vLadder release: wrote {output.resolve()}")
    return 0 if target["ready"] else 1


def grammar_command(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    if args.family:
        try:
            result: dict[str, object] = {
                "version": registry.version,
                "sha256": registry.sha256,
                "family": registry.family(args.family),
            }
        except KeyError as exc:
            print(f"vladder: error: {exc}", file=sys.stderr)
            return 2
    else:
        result = registry.to_dict()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _key_values(values: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in values:
        if "=" not in value:
            result[value] = True
            continue
        key, raw = value.split("=", 1)
        if not key:
            raise ValueError(f"empty key in {value!r}")
        try:
            result[key] = json.loads(raw)
        except json.JSONDecodeError:
            result[key] = raw
    return result


def lower_command(args: argparse.Namespace) -> int:
    engine = LoweringEngine(load_registry(args.registry))
    if args.lower_command == "validate":
        result = validate_lowering_registry(engine.registry)
    elif args.lower_command == "list":
        coverage = engine.coverage()
        result = {
            "schema_version": coverage["schema_version"],
            "status": coverage["status"],
            "grammar_version": coverage["grammar_version"],
            "grammar_sha256": coverage["grammar_sha256"],
            "family_count": coverage["family_count"],
            "rule_count": coverage["rule_count"],
            "plan_coverage": coverage["plan_coverage"],
            "source_route_coverage": coverage["source_route_coverage"],
            "families": coverage["families"],
        }
    elif args.lower_command == "show":
        try:
            family = engine.registry.family(args.family)
        except KeyError as error:
            print(f"vladder: error: {error}", file=sys.stderr)
            return 2
        rules = [args.rule] if args.rule else list(family["rules"])
        unknown = [rule for rule in rules if rule not in family["rules"]]
        if unknown:
            print(f"vladder: error: unknown rules for {args.family}: {unknown}", file=sys.stderr)
            return 2
        result = engine.inspect(args.family, args.rule)
    else:
        facts: dict[str, object] = {}
        if args.contract:
            loaded = json.loads(Path(args.contract).read_text())
            if not isinstance(loaded, dict):
                raise ValueError("lowering contract must be a JSON object")
            facts.update(loaded)
        facts.update(_key_values(args.fact))
        parameters = _key_values(args.parameter)
        lowered = engine.lower(
            LoweringRequest(
                args.family,
                args.rule,
                facts,
                parameters,
                LoweringMode(args.mode),
                Path(args.source).resolve() if args.source else None,
                args.function,
                args.input_identity,
            )
        )
        result = lowered.to_dict()
    output = json.dumps(result, indent=2, sort_keys=True)
    print(output)
    if args.out:
        Path(args.out).resolve().write_text(output + "\n")
    return 0 if result.get("status") in {"pass", "planned", "routed"} else 1


def deep_command(args: argparse.Namespace) -> int:
    grammar = load_deep_grammar(Path(args.grammar).resolve() if getattr(args, "grammar", None) else None)
    output: Path | None = None
    if args.deep_command == "coverage":
        report = grammar.coverage()
        output = Path(args.out).resolve() if args.out else None
    elif args.deep_command == "audit":
        report = audit_expert_manifest(Path(args.manifest), Path(args.out_dir), run_benchmarks=True if args.benchmark else None)
        output = Path(args.out_dir).resolve() / "expert-grammar-audit.json"
    elif args.deep_command == "neuralfusion-audit":
        output = Path(args.out).resolve()
        report = audit_neuralfusion_evidence_readonly(Path(args.repository_root), Path(args.evidence_root), output)
    elif args.deep_command == "rank":
        contract = DeepKernelContract(
            "exact-byte-predicate-reduction",
            args.predicate,
            input_min=args.input_min,
            input_max=args.input_max,
        )
        output_directory = Path(args.out_dir).resolve()
        report = rank_deep_grammar(
            contract,
            grammar,
            args.language,
            output_directory,
            processes=args.processes,
            repetitions_per_process=args.repetitions,
            n=args.n,
            inner=args.inner,
            cpu=args.cpu,
            minimum_effect_percent=args.min_speedup_pct,
        )
        output = output_directory / "deep-ranking.json"
    else:
        contract = DeepKernelContract(
            "exact-byte-predicate-reduction",
            args.predicate,
            input_min=args.input_min,
            input_max=args.input_max,
        )
        if args.deep_command == "graph":
            graph = build_deep_realization_graph(contract, args.realization, source_language=args.language, function_identity=args.function)
            report = graph.to_dict()
            output = Path(args.out).resolve() if args.out else None
        else:
            search = search_deep_grammar(
                contract,
                grammar,
                source=args.source_realization,
                targets=(args.target,) if args.target else None,
                state_budget=args.search_states,
                time_budget_ms=args.search_ms,
            )
            if args.deep_command == "search":
                report = search.to_dict()
                output = Path(args.out).resolve() if args.out else None
            else:
                derivation = next((item for item in search.derivations if item.target == args.target), None)
                if derivation is None:
                    raise ValueError(f"deep grammar cannot derive {args.target} from {args.source_realization}")
                candidate = emit_deep_candidate(contract, derivation, args.language, args.function, grammar)
                out_dir = Path(args.out_dir).resolve()
                out_dir.mkdir(parents=True, exist_ok=True)
                extensions = {"c": "c", "cpp": "cpp", "rust": "rs", "zig": "zig", "julia": "jl"}
                source_path = out_dir / f"candidate.{extensions[args.language]}"
                source_path.write_text(candidate.source)
                proof = prove_deep_candidate(contract, derivation, candidate, out_dir / "proofs")
                report = {
                    "schema_version": "vladder-deep-workflow-v1",
                    "status": "pass" if proof["status"] == "PASS" else "verification_failed",
                    "contract": contract.to_dict(),
                    "search": search.to_dict(),
                    "candidate": candidate.to_dict(),
                    "proof": proof,
                    "source": str(source_path),
                }
                if args.deep_command == "benchmark":
                    if proof["status"] != "PASS":
                        report["benchmark"] = {"status": "NOT_RUN", "reason": "proof did not pass"}
                    else:
                        report["benchmark"] = benchmark_deep_candidate(
                            contract,
                            derivation,
                            candidate,
                            out_dir / "benchmark",
                            processes=args.processes,
                            repetitions_per_process=args.repetitions,
                            n=args.n,
                            inner=args.inner,
                            cpu=args.cpu,
                            minimum_effect_percent=args.min_speedup_pct,
                        )
                output = out_dir / "deep-workflow.json"
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists() or output.read_text() != encoded:
            output.write_text(encoded)
    print(encoded, end="")
    status = str(report.get("status", "pass"))
    return 0 if status in {"pass", "supported"} else 2


def dataflow_command(args: argparse.Namespace) -> int:
    grammar = load_bounded_dataflow_grammar(Path(args.grammar).resolve() if getattr(args, "grammar", None) else None)
    output: Path | None = None
    if args.dataflow_command == "coverage":
        report = grammar.coverage()
        output = Path(args.out).resolve() if args.out else None
    elif args.dataflow_command == "audit":
        output_directory = Path(args.out_dir).resolve()
        report = audit_dataflow_manifest(Path(args.manifest).resolve(), output_directory, grammar)
        output = output_directory / "bounded-dataflow-audit.json"
    else:
        payload = json.loads(Path(args.contract).read_text())
        if not isinstance(payload, dict):
            raise ValueError("bounded dataflow contract must be a JSON object")
        contract = BoundedDataflowContract.from_dict(payload)
        derivation = grammar.derive(contract, args.target)
        if args.dataflow_command == "graph":
            report = build_bounded_dataflow_graph(
                contract, args.target, source_language=args.language, function_identity=args.function
            ).to_dict()
            report["status"] = "pass"
            output = Path(args.out).resolve() if args.out else None
        else:
            output_directory = Path(args.out_dir).resolve()
            output_directory.mkdir(parents=True, exist_ok=True)
            candidate = emit_dataflow_native(contract, derivation, args.language, args.function, grammar)
            suffix = {"c": ".c", "cpp": ".cpp", "zig": ".zig", "julia": ".jl"}[args.language]
            source = output_directory / ("candidate" + suffix)
            source.write_text(candidate.source)
            proof = prove_dataflow_candidate(
                contract,
                derivation,
                candidate,
                output_directory / "proofs",
                run_differential=args.dataflow_command == "verify",
            )
            report = {
                "schema_version": "vladder-bounded-dataflow-workflow-v1",
                "status": "pass" if proof["status"] == "PASS" else "verification_failed",
                "contract": contract.to_dict(),
                "derivation": derivation.to_dict(),
                "candidate": candidate.to_dict(),
                "candidate_source": str(source),
                "proof": proof,
                "source_changes_performed": False,
                "production_promotion": False,
            }
            output = output_directory / "bounded-dataflow-workflow.json"
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists() or output.read_text() != encoded:
            output.write_text(encoded)
    print(encoded, end="")
    return 0 if report.get("status") == "pass" else 2


def automatic_region_command(args: argparse.Namespace) -> int:
    source = Path(args.source).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    support = inspect_automatic_region(source, args.function, out_dir / "automatic-analysis")
    support_path = out_dir / "automatic-support.json"
    write_json(support_path, support.to_dict())
    if args.region_command == "inspect":
        print(json.dumps(support.to_dict(), indent=2, sort_keys=True))
        return 0 if support.supported else 2
    if not support.supported:
        print(json.dumps(support.to_dict(), indent=2, sort_keys=True))
        print(f"vLadder region: adapter required; wrote {support_path}", file=sys.stderr)
        return 2

    args.graph_inner_loop = True
    args.alive2 = True
    args.allow_unproved = False
    args.verification_policy = VerificationPolicy.STRICT.value
    args.llm_lift = False
    args.llm_rounds = 0
    result = optimize_c_kernel(args)
    report_path = out_dir / "perf.json"
    report = json.loads(report_path.read_text())
    report["automatic_region"] = support.to_dict()
    automatic_names = [
        row["candidate"] for row in report.get("candidates", [])
        if "automatic-region" in row.get("tags", [])
    ]
    report["automatic_region"]["generated_candidates"] = automatic_names
    applied = None
    optimized_source = out_dir / "optimized.c"
    if report.get("promotion", {}).get("promotable") and optimized_source.exists():
        applied = verify_applied_replacement(report_path, optimized_source, args.function)
        write_json(out_dir / "automatic-applied-verification.json", applied)
    report["automatic_region"]["applied_verification"] = applied
    write_json(report_path, report)
    print(f"vLadder region: support={support.family}/{support.canonical} generated={len(automatic_names)}")
    return result


def cpp_region_command(args: argparse.Namespace) -> int:
    if args.cpp_command == "adapter":
        report = generate_cpp_adapter_bundle(Path(args.report), Path(args.out_dir))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.cpp_command == "audit":
        report = inspect_cpp_matrix(
            Path(args.manifest), Path(args.out_dir), materialize_isolation=args.materialize_isolation
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    source = Path(args.source).resolve()
    compilation_database = Path(args.compile_commands).resolve()
    out_dir = Path(args.out_dir).resolve()
    if args.cpp_command == "inspect":
        report = inspect_cpp_region(
            source,
            args.function,
            compilation_database,
            out_dir,
            symbol=args.symbol,
            command_index=args.command_index,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report.get("status") == "supported" else 2
    if args.cpp_command in {"isolate", "synthesize"}:
        return_code, report = isolate_cpp_region(
            source,
            args.function,
            compilation_database,
            out_dir,
            symbol=args.symbol,
            command_index=args.command_index,
        )
        if args.cpp_command == "synthesize":
            report["requested_operation"] = "synthesize"
            write_json(out_dir / "cpp-support.json", report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return return_code
    return_code, report = optimize_cpp_region(
        source,
        args.function,
        compilation_database,
        out_dir,
        symbol=args.symbol,
        command_index=args.command_index,
        n=args.n,
        reps=args.reps,
        inner=args.inner,
        cpu=args.cpu,
        minimum_speedup_pct=args.min_speedup_pct,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return return_code


def rust_region_command(args: argparse.Namespace) -> int:
    if args.rust_command == "support":
        report = rust_support_report()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.rust_command == "audit":
        report = audit_rust_regions(Path(args.manifest), Path(args.out_dir))
        print(f"vLadder Rust: audited={report['region_count']} supported={report['supported_count']}")
        return 0
    request = RustRegionRequest(
        manifest_path=Path(args.manifest_path),
        source=Path(args.source),
        function=args.function,
        output_directory=Path(args.out_dir),
        package=args.package,
        target_kind=args.target_kind,
        target_name=args.target_name,
        profile=args.profile,
        features=tuple(args.feature),
        proof_bound=args.proof_bound,
        minimum_speedup_pct=getattr(args, "min_speedup_pct", 1.0),
        benchmark_elements=getattr(args, "n", 1 << 20),
        benchmark_inner=getattr(args, "inner", 128),
        benchmark_processes=getattr(args, "processes", 8),
        benchmark_repetitions=getattr(args, "repetitions", 2),
        cpu=getattr(args, "cpu", None),
    )
    actions = {
        "inspect": inspect_rust_region,
        "isolate": isolate_rust_region,
        "synthesize": synthesize_rust_region,
        "optimize": optimize_rust_region,
    }
    report = actions[args.rust_command](request)
    print(f"vLadder Rust: action={args.rust_command} status={report['status']}")
    if args.rust_command == "optimize":
        return 0 if report.get("promotion", {}).get("promotable") else 1
    return 0 if report["status"] in {"pass", "supported"} else 1


def zig_region_command(args: argparse.Namespace) -> int:
    if args.zig_command == "support":
        print(json.dumps(zig_support_report(), indent=2, sort_keys=True)); return 0
    if args.zig_command == "audit":
        report = audit_zig_regions(Path(args.manifest), Path(args.out_dir))
        print(f"vLadder Zig: audited={len(report['regions'])} supported={report['supported_count']}"); return 0
    request = ZigRegionRequest(
        source=Path(args.source), function=args.function, output_directory=Path(args.out_dir),
        build_root=Path(args.build_root) if args.build_root else None,
        optimize_mode=args.optimize_mode, target=args.target, proof_bound=args.proof_bound,
        minimum_speedup_pct=getattr(args, "min_speedup_pct", 1.0),
        benchmark_elements=getattr(args, "n", 1 << 20), benchmark_inner=getattr(args, "inner", 128),
        benchmark_processes=getattr(args, "processes", 8), benchmark_repetitions=getattr(args, "repetitions", 2),
        cpu=getattr(args, "cpu", None), specialization=getattr(args, "specialization", None),
    )
    actions = {"inspect": inspect_zig_region, "isolate": isolate_zig_region, "synthesize": synthesize_zig_region, "optimize": optimize_zig_region}
    report = actions[args.zig_command](request)
    print(f"vLadder Zig: action={args.zig_command} status={report['status']}")
    return 0 if report["status"] in {"pass", "supported"} else 1


def julia_region_command(args: argparse.Namespace) -> int:
    if args.julia_command == "support":
        print(json.dumps(julia_support_report(), indent=2, sort_keys=True)); return 0
    if args.julia_command == "audit":
        report = audit_julia_regions(Path(args.manifest), Path(args.out_dir))
        print(f"vLadder Julia: audited={len(report['regions'])} supported={report['supported_count']}"); return 0
    request = JuliaRegionRequest(
        project=Path(args.project), source=Path(args.source), module=args.module, function=args.function,
        signature=args.signature, output_directory=Path(args.out_dir), proof_bound=args.proof_bound,
        minimum_speedup_pct=getattr(args, "min_speedup_pct", 1.0),
        benchmark_elements=getattr(args, "n", 1 << 20), benchmark_inner=getattr(args, "inner", 128),
        benchmark_processes=getattr(args, "processes", 8), benchmark_repetitions=getattr(args, "repetitions", 2),
        cpu=getattr(args, "cpu", None), cpu_target=args.cpu_target,
    )
    actions = {"inspect": inspect_julia_region, "isolate": isolate_julia_region, "synthesize": synthesize_julia_region, "optimize": optimize_julia_region}
    report = actions[args.julia_command](request)
    print(f"vLadder Julia: action={args.julia_command} status={report['status']}")
    return 0 if report["status"] in {"pass", "supported"} else 1


def workflow_command(args: argparse.Namespace) -> int:
    if args.workflow_command == "init":
        report = initialize_workflow_manifest(args.kind, Path(args.out).resolve())
    elif args.workflow_command == "run":
        report = run_agent_workflow(Path(args.manifest), Path(args.out_dir), force=args.force)
    elif args.workflow_command == "summarize":
        report = summarize_report(Path(args.report), Path(args.out).resolve() if args.out else None)
    else:
        report = query_lineage(Path(args.summary), args.artifact)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _orchestrator_request(args: argparse.Namespace, *, plan_only: bool | None = None) -> OrchestratorRequest:
    project = Path(getattr(args, "project", ".")).resolve()
    source_value = getattr(args, "source", None)
    source = Path(source_value).resolve() if source_value else None
    compile_value = getattr(args, "compile_commands", None)
    compile_commands = Path(compile_value).resolve() if compile_value else None
    if compile_commands is None:
        for candidate in (project / "build/compile_commands.json", project / "compile_commands.json"):
            if candidate.exists():
                compile_commands = candidate
                break
    contract_value = getattr(args, "contract", None)
    workload_value = getattr(args, "workload", None)
    profile_value = getattr(args, "profile", None)
    return OrchestratorRequest(
        project=project,
        source=source,
        symbol=getattr(args, "function", None) or getattr(args, "symbol", None),
        compile_commands=compile_commands,
        contract=Path(contract_value).resolve() if contract_value else None,
        workload=Path(workload_value).resolve() if workload_value else None,
        profile=Path(profile_value).resolve() if profile_value else None,
        output_directory=Path(args.out_dir).resolve(),
        minimum_effect_percent=float(getattr(args, "min_speedup_pct", 1.0)),
        plan_only=bool(getattr(args, "plan_only", False) if plan_only is None else plan_only),
        force=bool(getattr(args, "force", False)),
        verbose=bool(getattr(args, "verbose", False)),
    )


def can_optimize_command(args: argparse.Namespace) -> int:
    request = _orchestrator_request(args, plan_only=True)
    if request.source is None or request.symbol is None:
        raise ValueError("can-optimize requires --source and a symbol")
    plan = write_plan(request, emit_progress=not args.quiet)
    forecast = plan["forecast"]
    print(
        "vLadder feasibility: "
        f"kind={plan['classification']['kind']} "
        f"first-unreachable={forecast['first_unreachable_state'] or 'none'} "
        f"cost={forecast['estimated_runtime_seconds']['low']}-{forecast['estimated_runtime_seconds']['high']}s "
        f"decision={plan['economic_decision']['recommendation']}"
    )
    print(f"vLadder feasibility: plan={request.output_directory / 'optimization-plan.json'}")
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def orchestrated_optimize_command(args: argparse.Namespace) -> int:
    if args.portfolio:
        report = run_portfolio(
            Path(args.project), Path(args.out_dir), max_regions=args.max_regions,
            execute=args.execute_portfolio,
            compile_commands=Path(args.compile_commands) if args.compile_commands else None,
            workers=args.workers,
        )
        print(
            "vLadder portfolio: "
            f"regions={report['region_count']} unique={report['unique_semantic_roots']} "
            f"continue={report['summary']['continue']} stop={report['summary']['stop']} "
            f"escalate={report['summary']['escalate']}"
        )
        print(f"vLadder portfolio: report={Path(args.out_dir).resolve() / 'portfolio-summary.json'}")
        return 0
    request = _orchestrator_request(args)
    if request.source is None or request.symbol is None:
        raise ValueError("optimize requires a source path and --function/--symbol, or --portfolio")
    is_legacy_c = request.source.suffix.lower() == ".c"
    report = run_optimization(
        request,
        c_executor=(lambda: optimize_c_kernel(args)) if is_legacy_c else None,
        emit_progress=not args.quiet,
    )
    if request.plan_only:
        plan = report["plan"]
        print(
            "vLadder plan: "
            f"kind={plan['classification']['kind']} "
            f"first-unreachable={plan['forecast']['first_unreachable_state'] or 'none'} "
            f"decision={plan['economic_decision']['recommendation']}"
        )
        print(f"vLadder plan: wrote {request.output_directory / 'optimization-plan.json'}")
        if args.json:
            print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    disposition = report["disposition"]
    print(format_terminal(disposition))
    if args.json:
        print(json.dumps(disposition, indent=2, sort_keys=True))
    if not args.strict_progress_exit:
        return 0
    return {
        "PROMOTABLE": 0,
        "VERIFIED_REJECTION": 10,
        "INTEGRATION_REQUIRED": 11,
        "NO_BENCHMARK": 12,
        "NO_PROOF": 13,
        "NO_CANDIDATE": 14,
        "NO_COVERAGE": 15,
    }[disposition["terminal_status"]]


def resume_command(args: argparse.Namespace) -> int:
    report = resume_optimization(Path(args.out_dir), force=args.force, emit_progress=not args.quiet)
    disposition = report.get("disposition")
    if disposition:
        print(format_terminal(disposition))
    return 0


def runner_command(args: argparse.Namespace) -> int:
    if args.runner_command == "execute":
        report = execute_remote_adapter(Path(args.manifest), Path(args.out_dir))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "pass" else 2
    result = json.loads(Path(args.result).read_text())
    request = json.loads(Path(args.request).read_text()) if Path(args.request).suffix == ".json" else yaml.safe_load(Path(args.request).read_text())
    key = os.environ.get(args.key_environment) if args.key_environment else None
    report = verify_remote_result(result, request, key)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.out:
        Path(args.out).resolve().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "pass" else 2


def benchmark_command(args: argparse.Namespace) -> int:
    if args.benchmark_command == "paired":
        report = run_paired_benchmark(Path(args.manifest), Path(args.out_dir))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report.get("status") == "pass" else 2
    report = (
        compose_application_cost(Path(args.manifest), Path(args.out))
        if args.benchmark_command == "compose-application" else
        compose_benchmark_effects(Path(args.manifest), Path(args.out))
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "pass" else 2


def protocol_command(args: argparse.Namespace) -> int:
    if args.protocol_command == "template":
        report = protocol_template(args.kind)
        destination = Path(args.out).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(yaml.safe_dump(report, sort_keys=False))
        print(json.dumps({"status": "PASS", "template": args.kind, "artifact": str(destination)}, indent=2, sort_keys=True))
        return 0
    report = verify_state_protocol(Path(args.manifest), Path(args.out_dir))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


def shader_command(args: argparse.Namespace) -> int:
    if args.shader_command == "support":
        report = gpu_support_matrix()
    elif args.shader_command == "inspect":
        report = inspect_shader(Path(args.source), Path(args.out_dir), target_env=args.target_env)
    else:
        report = synthesize_shader(
            Path(args.source), Path(args.out_dir), target_env=args.target_env,
            runner_manifest=Path(args.runner_manifest) if args.runner_manifest else None,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "pass" or args.shader_command == "support" else 2


def gpu_command(args: argparse.Namespace) -> int:
    if args.gpu_command == "support":
        report = heterogeneous_gpu_support_matrix()
    elif args.gpu_command == "probe":
        report = probe_cuda_architecture(
            Path(args.out),
            device=args.device,
            measure_bandwidth=not args.no_bandwidth,
            bandwidth_extent=args.bandwidth_n,
        )
    elif args.gpu_command == "topology":
        report = probe_device_topology(
            Path(args.out), cuda_device=args.device, transfer_bytes=args.transfer_bytes
        )
    elif args.gpu_command == "vulkan-probe":
        report = probe_vulkan_capabilities(Path(args.out))
    elif args.gpu_command == "presentation-probe":
        report = probe_drm_presentation(Path(args.out))
    elif args.gpu_command == "dma-template":
        topology_path = Path(args.topology).resolve()
        topology = json.loads(topology_path.read_text())
        report = emit_dma_protocol_template(
            topology, args.destination, Path(args.out), transfer_bytes=args.transfer_bytes
        )
    elif args.gpu_command == "queue-template":
        topology = json.loads(Path(args.topology).resolve().read_text())
        report = emit_vulkan_queue_protocol_template(topology, Path(args.out))
    elif args.gpu_command == "presentation-template":
        topology = json.loads(Path(args.topology).resolve().read_text())
        report = emit_presentation_protocol_template(topology, Path(args.out))
    elif args.gpu_command == "protocol-verify":
        report = verify_device_protocol(Path(args.manifest), Path(args.out_dir)).to_dict()
    elif args.gpu_command == "cuda-run":
        report = run_cuda_artifact(Path(args.artifact))
    elif args.gpu_command == "plan-synthesize":
        report = synthesize_heterogeneous_plans(Path(args.manifest), Path(args.out_dir))
    elif args.gpu_command == "plan-rank":
        report = rank_heterogeneous_plans(Path(args.manifest), Path(args.out_dir))
    elif args.gpu_command == "project-audit":
        report = audit_heterogeneous_project(Path(args.project), Path(args.out_dir))
    elif args.gpu_command in {"cuda-synthesize", "cuda-optimize"}:
        output_directory = Path(args.out_dir).resolve()
        if args.architecture:
            architecture = load_gpu_architecture(Path(args.architecture))
        else:
            probe = probe_cuda_architecture(
                output_directory / "architecture.yaml",
                device=args.device,
                measure_bandwidth=True,
                bandwidth_extent=args.bandwidth_n,
            )
            architecture = load_gpu_architecture(probe["architecture"])
        shared = {
            "logical_extent": args.n,
            "thread_sizes": tuple(int(item) for item in args.threads.split(",") if item),
            "unroll_factors": tuple(int(item) for item in args.unroll.split(",") if item),
            "baseline_threads": args.baseline_threads,
            "warmup": args.warmup,
            "iterations": args.iterations,
            "static_finalists": args.finalists,
        }
        if args.gpu_command == "cuda-synthesize":
            report = synthesize_cuda_pointwise(
                Path(args.source), args.function, architecture, output_directory, **shared
            )
        else:
            report = optimize_cuda_pointwise(
                Path(args.source), args.function, architecture, output_directory,
                **shared,
                processes=args.processes,
                minimum_effect_percent=args.min_effect,
                bootstrap_rounds=args.bootstrap_rounds,
                seed=args.seed,
                collect_counters=not args.no_counters,
            )
    else:
        actions = {
            "capture": capture_gpu_workflow,
            "synthesize": synthesize_gpu_workflow,
            "verify": verify_gpu_workflow,
            "rank": rank_gpu_workflow,
        }
        report = actions[args.gpu_command](Path(args.manifest), Path(args.out_dir))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status", "PASS") in {"pass", "PASS", "partial", "INCOMPLETE"} or args.gpu_command == "support" else 2


def prior_command(args: argparse.Namespace) -> int:
    if args.prior_command == "support":
        report = prior_support()
    elif args.prior_command == "init":
        report = initialize_prior_manifest(Path(args.out))
        report = {"schema_version": "vladder-prior-workflow-init-v0", "status": "pass", "manifest": str(Path(args.out).resolve()), "configuration": report}
    elif args.prior_command == "run":
        report = run_prior_workflow(Path(args.manifest), Path(args.out_dir))
    elif args.prior_command == "template":
        report = initialize_prior_training_template(Path(args.out))
        report = {"schema_version": "vladder-prior-template-init-v1", "status": "pass", "template": str(Path(args.out).resolve()), "configuration": report}
    elif args.prior_command == "materialize":
        report = materialize_prior_dataset_template(Path(args.manifest), Path(args.store))
    elif args.prior_command == "evaluate-matrix":
        report = evaluate_prior_generalization(
            Path(args.store), Path(args.out_dir), methods=tuple(args.methods.split(",")),
            ensemble_size=args.ensemble_size, epochs=args.epochs, learning_rate=args.learning_rate,
            seed=args.seed, budget_fraction=args.budget_fraction,
            exploration_fraction=args.exploration_fraction,
        )
    elif args.prior_command == "generate":
        report = generate_prior_dataset(Path(args.out_dir), args.roots)
    elif args.prior_command == "ingest":
        report = ingest_prior_dataset(Path(args.manifest), Path(args.store))
    elif args.prior_command == "validate":
        report = validate_prior_dataset(Path(args.store), Path(args.split) if args.split else None)
    elif args.prior_command == "split":
        report = split_prior_dataset(
            Path(args.store), Path(args.out), method=args.method, seed=args.seed,
            test_fraction=args.test_fraction, calibration_fraction=args.calibration_fraction,
            holdout=args.holdout,
        )
    elif args.prior_command == "train":
        report = train_prior(
            Path(args.store), Path(args.split), Path(args.out_dir), ensemble_size=args.ensemble_size,
            epochs=args.epochs, learning_rate=args.learning_rate, seed=args.seed,
        )
    elif args.prior_command == "recommend":
        report = recommend_prior(Path(args.model), Path(args.store), args.root_id, Path(args.out))
    elif args.prior_command == "select":
        report = select_prior(
            Path(args.recommendation), Path(args.store), args.root_id, Path(args.out),
            budget=args.budget, exploration_fraction=args.exploration_fraction, seed=args.seed,
        )
    else:
        report = evaluate_prior(
            Path(args.model), Path(args.store), Path(args.split), Path(args.out),
            partition=args.partition, budget_fraction=args.budget_fraction,
            exploration_fraction=args.exploration_fraction, seed=args.seed,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"pass", "insufficient_evaluation_roots"} else 2


def verify_application_command(args: argparse.Namespace) -> int:
    report = verify_applied_replacement(
        Path(args.report),
        Path(args.source),
        args.function,
        tuple(args.compile_arg),
    )
    output = json.dumps(report, indent=2, sort_keys=True)
    print(output)
    if args.out:
        Path(args.out).resolve().write_text(output + "\n")
    return 0 if report["status"] == "pass" else 1


def skill_command(args: argparse.Namespace) -> int:
    if args.skill_command == "validate":
        report = validate_skill(Path(args.path) if args.path else None)
    else:
        report = install_skill(Path(args.target), force=args.force)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


def schema_command(args: argparse.Namespace) -> int:
    if args.schema_command == "list":
        report = list_artifact_schemas()
    else:
        report = validate_artifact(args.kind, Path(args.artifact))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status", "pass") == "pass" else 2


def consent_command(args: argparse.Namespace) -> int:
    consent_path = Path(args.consent_file).expanduser() if args.consent_file else None
    if args.consent_command == "show":
        report = load_consent(consent_path)
    elif args.consent_command == "review-requested":
        report = record_review_request(
            path=consent_path, confirmed_user_prompt=args.confirmed_user_prompt,
        )
    else:
        report = set_consent(
            args.scope.replace("-", "_"),
            args.decision.replace("-", "_"),
            path=consent_path,
            confirmed_user_choice=args.confirmed_user_choice,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def contribution_command(args: argparse.Namespace) -> int:
    require_consent(CANONICAL_TRAINING_DATA)
    require_consent(AGENT_EXPERIENCE_REVIEW)
    report = probe_contribution_service(base_url=args.base_url, timeout_seconds=args.timeout)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


def review_command(args: argparse.Namespace) -> int:
    if args.review_command == "template":
        report = create_review_template(
            Path(args.promotion_summary), Path(args.out), project_name=args.project,
            project_revision=args.revision, repository=args.repository,
        )
    elif args.review_command == "campaign-template":
        report = create_campaign_review_template(
            [Path(item) for item in args.promotion_summary], Path(args.out),
            project_name=args.project, project_revision=args.revision, repository=args.repository,
        )
    elif args.review_command == "validate":
        report = validate_review(Path(args.review))
    else:
        report = submit_review(
            Path(args.review), endpoint=args.endpoint, token=None,
            confirm_upload=args.confirm_upload, validate_only=args.validate_only,
            timeout_seconds=args.timeout,
            consent_path=Path(args.consent_file).expanduser() if args.consent_file else None,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"pass", "submitted", "validated_remotely"} or args.review_command in {"template", "campaign-template"} else 2


def training_command(args: argparse.Namespace) -> int:
    if args.training_command == "template":
        report = create_training_template(Path(args.out))
    elif args.training_command == "from-prior":
        report = create_training_bundle_from_prior(
            Path(args.store), Path(args.out), project_id=args.project_id,
            producer_agent=args.agent, producer_model=args.model, producer_provider=args.provider,
            maximum_examples=args.maximum_examples,
            apply_durable_consent=args.apply_durable_consent,
            consent_path=Path(args.consent_file).expanduser() if args.consent_file else None,
        )
    elif args.training_command == "export-prior":
        report = export_all_training_bundles_from_prior(
            Path(args.store), Path(args.out_dir), project_id=args.project_id,
            producer_agent=args.agent, producer_model=args.model, producer_provider=args.provider,
            examples_per_bundle=args.examples_per_bundle,
            apply_durable_consent=args.apply_durable_consent,
            consent_path=Path(args.consent_file).expanduser() if args.consent_file else None,
        )
    elif args.training_command == "sync-prior":
        report = sync_all_training_bundles_from_prior(
            Path(args.store), Path(args.out_dir), project_id=args.project_id,
            producer_agent=args.agent, producer_model=args.model, producer_provider=args.provider,
            examples_per_bundle=args.examples_per_bundle, endpoint=args.endpoint, token=None,
            validate_only=args.validate_only, timeout_seconds=args.timeout,
            consent_path=Path(args.consent_file).expanduser() if args.consent_file else None,
        )
    elif args.training_command == "validate":
        report = validate_training_bundle(Path(args.bundle))
    elif args.training_command == "ingest-model":
        report = ingest_model_training_bundle(Path(args.bundle), Path(args.store))
    elif args.training_command == "graph-examples":
        report = write_graph_learning_jsonl(Path(args.bundle), Path(args.out))
    else:
        report = submit_training_bundle(
            Path(args.bundle), endpoint=args.endpoint, token=None,
            confirm_upload=args.confirm_upload, validate_only=args.validate_only,
            timeout_seconds=args.timeout,
            consent_path=Path(args.consent_file).expanduser() if args.consent_file else None,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    accepted = {"pass", "submitted", "validated_remotely"}
    return 0 if report.get("status") in accepted or args.training_command in {"template", "from-prior", "export-prior"} else 2


def lifetime_command(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest).resolve()
    trace = Path(args.trace).resolve()
    output_directory = Path(args.out_dir).resolve()
    if args.lifetime_command == "analyze":
        report = analyze_lifetime_flow(manifest, trace, output_directory)
        report_path = output_directory / "lifetime-analysis.json"
    elif args.lifetime_command == "synthesize":
        report = synthesize_lifetime_flow(manifest, trace, output_directory)
        report_path = output_directory / "lifetime-report.json"
    else:
        report = evaluate_lifetime_corpus(manifest, trace, output_directory)
        report_path = output_directory / "lifetime-evaluation.json"
    if not report_path.exists():
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"vLadder lifetime: action={args.lifetime_command} status={report['status']}")
    print(f"vLadder lifetime: wrote {report_path}")
    return 0 if report["status"] == "pass" else 1


def system_closure_command(args: argparse.Namespace) -> int:
    report = run_system_closure(Path(args.manifest), Path(args.out_dir))
    graph = report["system_graph"]
    print(
        "vLadder system-closure: "
        f"status={report['status']} functions={len(graph['functions'])} "
        f"boundaries={len(graph['boundaries'])} candidates={graph['computational_candidate_count']}"
    )
    print(f"vLadder system-closure: wrote {Path(args.out_dir).resolve() / 'system-closure-report.json'}")
    return 0 if report["status"] == "pass" else 2


def whole_build_command(args: argparse.Namespace) -> int:
    if args.build_command == "index":
        index = WholeBuildIndex.from_compilation_database(Path(args.compile_commands))
        path = index.write(Path(args.out).resolve())
        counts = index.to_dict()["counts"]
        print(
            "vLadder whole-build: "
            f"translation_units={counts['translation_units']} symbols={counts['defined_symbols']} "
            f"ambiguous={counts['ambiguous_definitions']}"
        )
        print(f"vLadder whole-build: wrote {path}")
        return 0
    report = run_cross_tu_closure(
        Path(args.compile_commands),
        args.seed,
        Path(args.out_dir),
        max_upstream=args.max_upstream,
        max_downstream=args.max_downstream,
        max_nodes=args.max_nodes,
    )
    graph = report["slice"]
    print(
        "vLadder cross-tu-closure: "
        f"status={report['status']} functions={len(graph['functions'])} "
        f"edges={len(graph['edges'])} boundaries={len(graph['boundaries'])}"
    )
    print(f"vLadder cross-tu-closure: wrote {Path(args.out_dir).resolve() / 'cross-tu-closure-report.json'}")
    return 0 if report["status"] == "pass" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vladder",
        description="Verified hardware-aware information-flow superoptimizer for bounded systems-language regions",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    workflow = sub.add_parser("workflow", help="run and summarize the canonical agent optimization workflow")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_init = workflow_sub.add_parser("init", help="create a canonical workflow manifest")
    workflow_init.add_argument("--kind", choices=("c", "cpp", "rust", "zig", "julia", "system", "lifetime", "shader", "gpu", "protocol"), required=True)
    workflow_init.add_argument("--out", default="vladder-workflow.yaml")
    workflow_init.set_defaults(func=workflow_command)
    workflow_run = workflow_sub.add_parser("run", help="route one manifest and emit a promotion summary")
    workflow_run.add_argument("--manifest", required=True)
    workflow_run.add_argument("--out-dir", default="vladder-workflow-out")
    workflow_run.add_argument("--force", action="store_true", help="ignore a matching resumable stage record")
    workflow_run.set_defaults(func=workflow_command)
    workflow_summary = workflow_sub.add_parser("summarize", help="summarize an existing stage report")
    workflow_summary.add_argument("--report", required=True)
    workflow_summary.add_argument("--out")
    workflow_summary.set_defaults(func=workflow_command)
    workflow_query = workflow_sub.add_parser("query", help="query artifact ancestors and descendants")
    workflow_query.add_argument("--summary", required=True)
    workflow_query.add_argument("--artifact", required=True)
    workflow_query.set_defaults(func=workflow_command)
    system = sub.add_parser("system", help="compose function summaries without expanding implementation search")
    system_sub = system.add_subparsers(dest="system_command", required=True)
    system_closure = system_sub.add_parser("closure", help="build and prove a bounded system-of-functions closure graph")
    system_closure.add_argument("--manifest", required=True)
    system_closure.add_argument("--out-dir", default="vladder-system-closure")
    system_closure.set_defaults(func=system_closure_command)
    build = sub.add_parser("build", help="index and close semantic flow across a compiled multi-TU build")
    build_sub = build.add_subparsers(dest="build_command", required=True)
    build_index = build_sub.add_parser("index", help="create a deterministic whole-build definition/reference index")
    build_index.add_argument("--compile-commands", required=True)
    build_index.add_argument("--out", default="vladder-whole-build-index.json")
    build_index.set_defaults(func=whole_build_command)
    build_closure = build_sub.add_parser("closure", help="materialize and prove one bounded bidirectional cross-TU slice")
    build_closure.add_argument("--compile-commands", required=True)
    build_closure.add_argument("--seed", action="append", required=True, help="mangled seed symbol; repeatable")
    build_closure.add_argument("--max-upstream", type=int, default=1)
    build_closure.add_argument("--max-downstream", type=int, default=3)
    build_closure.add_argument("--max-nodes", type=int, default=128)
    build_closure.add_argument("--out-dir", default="vladder-cross-tu-closure")
    build_closure.set_defaults(func=whole_build_command)
    doctor = sub.add_parser("doctor", help="validate compilers, solvers, validators, and performance tools")
    doctor.add_argument("--strict", action="store_true", help="require Alive2 and perf in addition to the core toolchain")
    doctor.add_argument("--out", help="also write the JSON report to this path")
    doctor.set_defaults(func=doctor_command)
    release = sub.add_parser("release", help="evaluate source, tests, artifacts, access paths, and publication channels")
    release_sub = release.add_subparsers(dest="release_command", required=True)
    release_check = release_sub.add_parser("check", help="emit one target-aware release-readiness report")
    release_check.add_argument("--root", default=".", help="vLadder source checkout")
    release_check.add_argument("--execute", action="store_true", help="run tests, builds, clean installs, and service builds")
    release_check.add_argument("--online", action="store_true", help="inspect GitHub, PyPI, Homebrew, and hosted service state")
    release_check.add_argument(
        "--require-target", choices=("local_development", "release_candidate", "github_release", "pypi", "homebrew", "formal_release"),
        default="local_development",
    )
    release_check.add_argument("--work-dir", help="retain generated build/install evidence in this directory")
    release_check.add_argument("--reuse-local-report", help="refresh online state on a matching report produced with --execute")
    release_check.add_argument("--out", default="build/release-readiness.json")
    release_check.set_defaults(func=release_command)
    grammar = sub.add_parser("grammar", help="inspect the versioned C/C++ capability registry")
    grammar.add_argument("--family", help="show one grammar family")
    grammar.add_argument("--registry", help="load an alternate capabilities.json")
    grammar.set_defaults(func=grammar_command)
    lower = sub.add_parser("lower", help="validate, inspect, or execute registry-driven grammar lowering")
    lower.add_argument("--registry", help="load an alternate capabilities.json")
    lower_sub = lower.add_subparsers(dest="lower_command", required=True)
    lower_validate = lower_sub.add_parser("validate", help="validate callable lowerers and complete rule ownership")
    lower_validate.add_argument("--out", help="also write the JSON coverage report")
    lower_validate.set_defaults(func=lower_command)
    lower_list = lower_sub.add_parser("list", help="list plan and source-route lowering coverage")
    lower_list.add_argument("--out", help="also write the JSON coverage report")
    lower_list.set_defaults(func=lower_command)
    lower_show = lower_sub.add_parser("show", help="inspect rule facts, maturity, and source route")
    lower_show.add_argument("--family", required=True)
    lower_show.add_argument("--rule")
    lower_show.add_argument("--out", help="also write the JSON inspection report")
    lower_show.set_defaults(func=lower_command)
    lower_plan = lower_sub.add_parser("plan", help="lower one grammar rule into a deterministic information-flow plan")
    lower_plan.add_argument("--family", required=True)
    lower_plan.add_argument("--rule", required=True)
    lower_plan.add_argument("--contract", help="JSON object containing established contract facts")
    lower_plan.add_argument("--fact", action="append", default=[], help="established fact as name or name=JSON; repeatable")
    lower_plan.add_argument("--parameter", action="append", default=[], help="rule parameter as name=JSON; repeatable")
    lower_plan.add_argument("--mode", choices=tuple(item.value for item in LoweringMode), default="plan")
    lower_plan.add_argument("--source", help="optional source identity for a specialized backend")
    lower_plan.add_argument("--function", help="optional source function identity")
    lower_plan.add_argument("--input-identity", default="unbound-region")
    lower_plan.add_argument("--out", help="also write the JSON lowering result")
    lower_plan.set_defaults(func=lower_command)
    deep = sub.add_parser("deep", help="derive, regenerate, prove, and audit deep shared information-flow realizations")
    deep.add_argument("--grammar", help="alternate deep-v2 grammar JSON")
    deep_sub = deep.add_subparsers(dest="deep_command", required=True)
    deep_coverage = deep_sub.add_parser("coverage", help="report graph, source, proof, and benchmark bindings for every deep family")
    deep_coverage.add_argument("--out")
    deep_coverage.set_defaults(func=deep_command)
    deep_audit = deep_sub.add_parser("audit", help="audit scalar/expert pairs through representation, derivation, lowering, proof, and performance")
    deep_audit.add_argument("--manifest", required=True)
    deep_audit.add_argument("--out-dir", default="vladder-deep-audit")
    deep_audit.add_argument("--benchmark", action="store_true", help="override case settings and physically rank every proved case")
    deep_audit.set_defaults(func=deep_command)
    deep_neural = deep_sub.add_parser("neuralfusion-audit", help="inspect existing NeuralFusion semantic evidence without modifying or rebuilding it")
    deep_neural.add_argument("--repository-root", required=True)
    deep_neural.add_argument("--evidence-root", required=True)
    deep_neural.add_argument("--out", default="neuralfusion-deep-readonly.json")
    deep_neural.set_defaults(func=deep_command)
    deep_rank = deep_sub.add_parser("rank", help="prove, assembly-deduplicate, and physically rank every reachable terminal realization")
    deep_rank.add_argument("--predicate", choices=("equal-u8", "utf8-leading-byte"), default="equal-u8")
    deep_rank.add_argument("--language", choices=("c", "cpp", "rust", "zig", "julia"), default="c")
    deep_rank.add_argument("--input-min", type=int, default=0)
    deep_rank.add_argument("--input-max", type=int, default=1 << 30)
    deep_rank.add_argument("--processes", type=int, default=10)
    deep_rank.add_argument("--repetitions", type=int, default=3)
    deep_rank.add_argument("--n", type=int, default=1 << 20)
    deep_rank.add_argument("--inner", type=int, default=128)
    deep_rank.add_argument("--cpu", type=int)
    deep_rank.add_argument("--min-speedup-pct", type=float, default=1.0)
    deep_rank.add_argument("--out-dir", default="vladder-deep-ranking")
    deep_rank.set_defaults(func=deep_command)
    for action, help_text in (
        ("graph", "construct one shared physical realization graph"),
        ("search", "derive reachable terminal realizations from a scalar graph"),
        ("emit", "derive and emit a native C/C++/Rust/Zig/Julia candidate with proof"),
        ("benchmark", "derive, prove, differentially execute, and physically rank one candidate"),
    ):
        command = deep_sub.add_parser(action, help=help_text)
        command.add_argument("--predicate", choices=("equal-u8", "utf8-leading-byte"), default="equal-u8")
        command.add_argument("--language", choices=("c", "cpp", "rust", "zig", "julia"), default="c")
        command.add_argument("--function", default="deep_candidate")
        command.add_argument("--input-min", type=int, default=0)
        command.add_argument("--input-max", type=int, default=1 << 30)
        if action == "graph":
            command.add_argument("--realization", required=True)
            command.add_argument("--out")
        else:
            command.add_argument("--source-realization", default="scalar")
            command.add_argument("--search-states", type=int, default=256)
            command.add_argument("--search-ms", type=int, default=1000)
            if action == "search":
                command.add_argument("--target")
                command.add_argument("--out")
            else:
                command.add_argument("--target", required=True)
                command.add_argument("--out-dir", default=f"vladder-deep-{action}")
                if action == "benchmark":
                    command.add_argument("--processes", type=int, default=10)
                    command.add_argument("--repetitions", type=int, default=3)
                    command.add_argument("--n", type=int, default=1 << 20)
                    command.add_argument("--inner", type=int, default=128)
                    command.add_argument("--cpu", type=int)
                    command.add_argument("--min-speedup-pct", type=float, default=1.0)
        command.set_defaults(func=deep_command)
    dataflow = sub.add_parser(
        "dataflow",
        help="derive, emit, prove, and audit bounded variable-output and stateful dataflow",
    )
    dataflow.add_argument("--grammar", help="alternate bounded-dataflow-v1 grammar JSON")
    dataflow_sub = dataflow.add_subparsers(dest="dataflow_command", required=True)
    dataflow_coverage = dataflow_sub.add_parser("coverage", help="show every bounded dataflow family and executable terminal")
    dataflow_coverage.add_argument("--out")
    dataflow_coverage.set_defaults(func=dataflow_command)
    dataflow_audit = dataflow_sub.add_parser("audit", help="classify a C++ repository manifest without changing production source")
    dataflow_audit.add_argument("--manifest", required=True)
    dataflow_audit.add_argument("--out-dir", default="vladder-dataflow-audit")
    dataflow_audit.set_defaults(func=dataflow_command)
    for action, help_text in (
        ("graph", "construct one SemanticFlowGraph v2 bounded-dataflow realization"),
        ("emit", "emit native C/C++/Zig/Julia and bounded proof obligations without physical promotion"),
        ("verify", "emit, prove, compile, and differentially execute one native realization"),
    ):
        command = dataflow_sub.add_parser(action, help=help_text)
        command.add_argument("--contract", required=True, help="bounded dataflow contract JSON")
        command.add_argument("--target", required=True, help="terminal realization name from dataflow coverage")
        command.add_argument("--function", default="dataflow_candidate")
        command.add_argument("--language", choices=("c", "cpp", "zig", "julia"), default="cpp")
        if action == "graph":
            command.add_argument("--out")
        else:
            command.add_argument("--out-dir", default=f"vladder-dataflow-{action}")
        command.set_defaults(func=dataflow_command)
    region = sub.add_parser("region", help="inspect or optimize an automatically supported bounded C region")
    region_sub = region.add_subparsers(dest="region_command", required=True)
    region_inspect = region_sub.add_parser("inspect", help="classify automatic support or emit adapter requirements")
    region_inspect.add_argument("--source", required=True)
    region_inspect.add_argument("--function", required=True)
    region_inspect.add_argument("--out-dir", default="vladder-region-inspect")
    region_inspect.set_defaults(func=automatic_region_command)
    region_optimize = region_sub.add_parser("optimize", help="extract, regenerate, prove, benchmark, and promote a bounded region")
    region_optimize.add_argument("--source", required=True)
    region_optimize.add_argument("--function", required=True)
    region_optimize.add_argument("--out-dir", default="vladder-region-out")
    region_optimize.add_argument("--n", type=int, default=1 << 18)
    region_optimize.add_argument("--reps", type=int, default=25)
    region_optimize.add_argument("--inner", type=int, default=8)
    region_optimize.add_argument("--cpu", type=int, default=0)
    region_optimize.add_argument("--assume-no-alias", action="store_true")
    region_optimize.add_argument("--flush-cache", action="store_true")
    region_optimize.add_argument("--perf", action="store_true")
    region_optimize.add_argument("--min-speedup-pct", type=float, default=1.0)
    region_optimize.add_argument("--search-nodes", type=int, default=64)
    region_optimize.add_argument("--search-ms", type=int, default=1000)
    region_optimize.set_defaults(func=automatic_region_command)
    cpp = sub.add_parser("cpp", help="extract, isolate, prove, and optimize a bounded C++ kernel")
    cpp_sub = cpp.add_subparsers(dest="cpp_command", required=True)
    cpp_audit = cpp_sub.add_parser("audit", help="inspect a manifest of C++ regions without optimization or source changes")
    cpp_audit.add_argument("--manifest", required=True)
    cpp_audit.add_argument("--out-dir", default="vladder-cpp-audit")
    cpp_audit.add_argument(
        "--materialize-isolation", action="store_true",
        help="compile and prove predicted local proof units without applying source changes",
    )
    cpp_audit.set_defaults(func=cpp_region_command)
    cpp_adapter = cpp_sub.add_parser("adapter", help="generate an explicit application adapter bundle from C++ closure evidence")
    cpp_adapter.add_argument("--report", required=True, help="cpp-support.json from inspect or isolate")
    cpp_adapter.add_argument("--out-dir", default="vladder-cpp-adapter")
    cpp_adapter.set_defaults(func=cpp_region_command)
    for action, help_text, default_out in (
        ("inspect", "classify a concrete C++ definition and emit adapter requirements", "vladder-cpp-inspect"),
        ("isolate", "extract production IR, isolate the kernel, prove its adapter, and regenerate C++", "vladder-cpp-isolation"),
        ("synthesize", "materialize proved bounded C++ source candidates without applying them", "vladder-cpp-synthesis"),
        ("optimize", "run the strict C kernel optimizer and regenerate a proved C++ realization", "vladder-cpp-out"),
    ):
        command = cpp_sub.add_parser(action, help=help_text)
        command.add_argument("--source", required=True)
        command.add_argument("--function", required=True, help="source name, optionally class- or namespace-qualified")
        command.add_argument("--compile-commands", required=True, help="compile_commands.json or its containing directory")
        command.add_argument("--symbol", help="exact Clang mangled symbol for an overload or template specialization")
        command.add_argument("--command-index", type=int, help="exact JSON compilation database entry index")
        command.add_argument("--out-dir", default=default_out)
        if action == "optimize":
            command.add_argument("--n", type=int, default=1 << 18)
            command.add_argument("--reps", type=int, default=25)
            command.add_argument("--inner", type=int, default=8)
            command.add_argument("--cpu", type=int, default=0)
            command.add_argument("--min-speedup-pct", type=float, default=1.0)
        command.set_defaults(func=cpp_region_command)
    rust = sub.add_parser("rust", help="capture MIR/LLVM, synthesize, prove, and optimize a bounded Rust region")
    rust_sub = rust.add_subparsers(dest="rust_command", required=True)
    rust_support = rust_sub.add_parser("support", help="show the language-neutral adapter and Rust support version")
    rust_support.set_defaults(func=rust_region_command)
    rust_audit = rust_sub.add_parser("audit", help="inspect a manifest of Rust regions without source changes")
    rust_audit.add_argument("--manifest", required=True)
    rust_audit.add_argument("--out-dir", default="vladder-rust-audit")
    rust_audit.set_defaults(func=rust_region_command)
    for action, help_text, default_out in (
        ("inspect", "capture Cargo, source, MIR, LLVM IR, assembly, and closure evidence", "vladder-rust-inspect"),
        ("isolate", "construct the shared semantic graph and bounded proof unit", "vladder-rust-isolation"),
        ("synthesize", "regenerate native Rust candidates and prove MIR/LLVM equivalence", "vladder-rust-synthesis"),
        ("optimize", "prove and physically rank native Rust candidates", "vladder-rust-out"),
    ):
        command = rust_sub.add_parser(action, help=help_text)
        command.add_argument("--manifest-path", required=True, help="Cargo.toml for the selected package")
        command.add_argument("--source", required=True)
        command.add_argument("--function", required=True, help="module-qualified concrete function name")
        command.add_argument("--package")
        command.add_argument("--target-kind", choices=("lib", "bin", "example", "test", "bench"), default="lib")
        command.add_argument("--target-name")
        command.add_argument("--profile", default="release")
        command.add_argument("--feature", action="append", default=[])
        command.add_argument("--proof-bound", type=int, default=32)
        command.add_argument("--out-dir", default=default_out)
        if action == "optimize":
            command.add_argument("--n", type=int, default=1 << 20)
            command.add_argument("--inner", type=int, default=128)
            command.add_argument("--processes", type=int, default=8)
            command.add_argument("--repetitions", type=int, default=2)
            command.add_argument("--cpu", type=int)
            command.add_argument("--min-speedup-pct", type=float, default=1.0)
        command.set_defaults(func=rust_region_command)
    zig = sub.add_parser("zig", help="capture native/LLVM artifacts, prove, and optimize a bounded Zig region")
    zig_sub = zig.add_subparsers(dest="zig_command", required=True)
    zig_sub.add_parser("support", help="show bounded Zig support").set_defaults(func=zig_region_command)
    zig_audit = zig_sub.add_parser("audit", help="inspect a manifest of Zig regions")
    zig_audit.add_argument("--manifest", required=True); zig_audit.add_argument("--out-dir", default="vladder-zig-audit"); zig_audit.set_defaults(func=zig_region_command)
    for action, help_text, default_out in (
        ("inspect", "capture Zig source, compiler, LLVM, assembly, effects, and graph", "vladder-zig-inspect"),
        ("isolate", "emit the bounded Zig proof unit", "vladder-zig-isolation"),
        ("synthesize", "regenerate and prove native Zig candidates", "vladder-zig-synthesis"),
        ("optimize", "prove and physically rank native Zig candidates", "vladder-zig-out"),
    ):
        command = zig_sub.add_parser(action, help=help_text)
        command.add_argument("--source", required=True); command.add_argument("--function", required=True)
        command.add_argument("--specialization", help="concrete Zig comptime type, for example u8")
        command.add_argument("--build-root"); command.add_argument("--optimize-mode", choices=("Debug", "ReleaseSafe", "ReleaseFast", "ReleaseSmall"), default="ReleaseFast")
        command.add_argument("--target", default="native"); command.add_argument("--proof-bound", type=int, default=32); command.add_argument("--out-dir", default=default_out)
        if action == "optimize":
            command.add_argument("--n", type=int, default=1 << 20); command.add_argument("--inner", type=int, default=128)
            command.add_argument("--processes", type=int, default=8); command.add_argument("--repetitions", type=int, default=2)
            command.add_argument("--cpu", type=int); command.add_argument("--min-speedup-pct", type=float, default=1.0)
        command.set_defaults(func=zig_region_command)
    julia = sub.add_parser("julia", help="capture typed/LLVM artifacts, prove, and optimize one Julia specialization")
    julia_sub = julia.add_subparsers(dest="julia_command", required=True)
    julia_sub.add_parser("support", help="show bounded Julia support").set_defaults(func=julia_region_command)
    julia_audit = julia_sub.add_parser("audit", help="inspect a manifest of Julia specializations")
    julia_audit.add_argument("--manifest", required=True); julia_audit.add_argument("--out-dir", default="vladder-julia-audit"); julia_audit.set_defaults(func=julia_region_command)
    for action, help_text, default_out in (
        ("inspect", "capture project, method, lowered/typed IR, LLVM, native code, effects, and graph", "vladder-julia-inspect"),
        ("isolate", "emit the bounded Julia specialization proof unit", "vladder-julia-isolation"),
        ("synthesize", "regenerate and prove native Julia candidates", "vladder-julia-synthesis"),
        ("optimize", "prove and physically rank warmed Julia candidates", "vladder-julia-out"),
    ):
        command = julia_sub.add_parser(action, help=help_text)
        command.add_argument("--project", required=True); command.add_argument("--source", required=True)
        command.add_argument("--module", required=True); command.add_argument("--function", required=True)
        command.add_argument("--signature", required=True, help="concrete tuple members, e.g. Vector{UInt8},UInt8")
        command.add_argument("--cpu-target", default="native"); command.add_argument("--proof-bound", type=int, default=32); command.add_argument("--out-dir", default=default_out)
        if action == "optimize":
            command.add_argument("--n", type=int, default=1 << 20); command.add_argument("--inner", type=int, default=128)
            command.add_argument("--processes", type=int, default=8); command.add_argument("--repetitions", type=int, default=2)
            command.add_argument("--cpu", type=int); command.add_argument("--min-speedup-pct", type=float, default=1.0)
        command.set_defaults(func=julia_region_command)
    verify_application = sub.add_parser("verify-application", help="verify that an applied source rewrite is the proved generated candidate")
    verify_application.add_argument("--report", required=True, help="perf.json from the promoting optimization run")
    verify_application.add_argument("--source", required=True, help="source file containing the applied replacement")
    verify_application.add_argument("--function", required=True, help="rewritten function name")
    verify_application.add_argument("--compile-arg", action="append", default=[], help="additional compiler argument for project headers or defines")
    verify_application.add_argument("--out", help="also write the JSON verification report")
    verify_application.set_defaults(func=verify_application_command)
    benchmark = sub.add_parser("benchmark", help="collect paired evidence or compose disjoint regional effects")
    benchmark_sub = benchmark.add_subparsers(dest="benchmark_command", required=True)
    benchmark_paired = benchmark_sub.add_parser("paired", help="run randomized baseline/candidate process pairs")
    benchmark_paired.add_argument("--manifest", required=True)
    benchmark_paired.add_argument("--out-dir", default="vladder-paired-benchmark")
    benchmark_paired.set_defaults(func=benchmark_command)
    benchmark_compose = benchmark_sub.add_parser("compose", help="compose only disjoint or interaction-measured effects")
    benchmark_compose.add_argument("--manifest", required=True)
    benchmark_compose.add_argument("--out", default="vladder-composition.json")
    benchmark_compose.set_defaults(func=benchmark_command)
    benchmark_application = benchmark_sub.add_parser("compose-application", help="forecast end-to-end effect from runtime share, invocation, overlap, and amortization")
    benchmark_application.add_argument("--manifest", required=True)
    benchmark_application.add_argument("--out", default="vladder-application-composition.json")
    benchmark_application.set_defaults(func=benchmark_command)
    protocol = sub.add_parser("protocol", help="verify bounded retained-state protocol projections")
    protocol_sub = protocol.add_subparsers(dest="protocol_command", required=True)
    protocol_verify = protocol_sub.add_parser("verify", help="prove cache, publication, or finite-resource protocol obligations")
    protocol_verify.add_argument("--manifest", required=True)
    protocol_verify.add_argument("--out-dir", default="vladder-protocol-proof")
    protocol_verify.set_defaults(func=protocol_command)
    protocol_template_parser = protocol_sub.add_parser("template", help="emit a domain-neutral finite resource protocol template")
    protocol_template_parser.add_argument("--kind", required=True, choices=("publication", "queue", "socket", "device"))
    protocol_template_parser.add_argument("--out", default="vladder-resource-protocol.yaml")
    protocol_template_parser.set_defaults(func=protocol_command)
    shader = sub.add_parser("shader", help="inspect and synthesize portable compute shader evidence")
    shader_sub = shader.add_subparsers(dest="shader_command", required=True)
    shader_support = shader_sub.add_parser("support", help="show portable GPU toolchain and proof boundaries")
    shader_support.set_defaults(func=shader_command)
    for action, help_text, default_out in (
        ("inspect", "compile/import and validate a SPIR-V compute module", "vladder-shader-inspect"),
        ("synthesize", "generate bounded SPIR-V optimizer candidates", "vladder-shader-out"),
    ):
        command = shader_sub.add_parser(action, help=help_text)
        command.add_argument("--source", required=True)
        command.add_argument("--target-env", default="vulkan1.2")
        command.add_argument("--out-dir", default=default_out)
        if action == "synthesize":
            command.add_argument("--runner-manifest", help="application output-hash and device-timestamp runner")
        command.set_defaults(func=shader_command)
    gpu = sub.add_parser("gpu", help="capture, synthesize, verify, and rank heterogeneous GPU execution graphs")
    gpu_sub = gpu.add_subparsers(dest="gpu_command", required=True)
    gpu_support = gpu_sub.add_parser("support", help="show GPU kernel, protocol, cost-model, and counter capabilities")
    gpu_support.set_defaults(func=gpu_command)
    gpu_probe = gpu_sub.add_parser("probe", help="probe a CUDA device and measure a sustainable copy-flow bandwidth bound")
    gpu_probe.add_argument("--out", default="vladder-gpu-architecture.yaml")
    gpu_probe.add_argument("--device", type=int, default=0)
    gpu_probe.add_argument("--no-bandwidth", action="store_true")
    gpu_probe.add_argument("--bandwidth-n", type=int, default=1 << 25)
    gpu_probe.set_defaults(func=gpu_command)
    gpu_topology = gpu_sub.add_parser("topology", help="bind CUDA, Vulkan, PCIe, IOMMU, NIC, RDMA, and DRM capabilities into one topology")
    gpu_topology.add_argument("--out", default="vladder-device-topology.json")
    gpu_topology.add_argument("--device", type=int, default=0)
    gpu_topology.add_argument("--transfer-bytes", type=int, default=1 << 20)
    gpu_topology.set_defaults(func=gpu_command)
    gpu_vulkan = gpu_sub.add_parser("vulkan-probe", help="probe Vulkan device identity, queues, synchronization, and external-memory capabilities")
    gpu_vulkan.add_argument("--out", default="vladder-vulkan-capabilities.json")
    gpu_vulkan.set_defaults(func=gpu_command)
    gpu_presentation = gpu_sub.add_parser("presentation-probe", help="probe DRM connector and scanout capability boundaries")
    gpu_presentation.add_argument("--out", default="vladder-presentation-capabilities.json")
    gpu_presentation.set_defaults(func=gpu_command)
    gpu_dma = gpu_sub.add_parser("dma-template", help="emit a fail-closed DMA protocol template from a probed topology route")
    gpu_dma.add_argument("--topology", required=True)
    gpu_dma.add_argument("--destination", required=True)
    gpu_dma.add_argument("--out", default="vladder-dma-protocol.yaml")
    gpu_dma.add_argument("--transfer-bytes", type=int, default=1 << 20)
    gpu_dma.set_defaults(func=gpu_command)
    gpu_queue = gpu_sub.add_parser("queue-template", help="emit a live-device-bound Vulkan synchronization2 queue protocol")
    gpu_queue.add_argument("--topology", required=True)
    gpu_queue.add_argument("--out", default="vladder-vulkan-queue-protocol.yaml")
    gpu_queue.set_defaults(func=gpu_command)
    gpu_present_template = gpu_sub.add_parser("presentation-template", help="emit a live-connector-bound presentation protocol, failing closed when no connector is active")
    gpu_present_template.add_argument("--topology", required=True)
    gpu_present_template.add_argument("--out", default="vladder-presentation-protocol.yaml")
    gpu_present_template.set_defaults(func=gpu_command)
    gpu_protocol = gpu_sub.add_parser("protocol-verify", help="prove a bounded Vulkan queue, DMA, or presentation protocol graph")
    gpu_protocol.add_argument("--manifest", required=True)
    gpu_protocol.add_argument("--out-dir", default="vladder-device-protocol-proof")
    gpu_protocol.set_defaults(func=gpu_command)
    gpu_run = gpu_sub.add_parser("cuda-run", help="execute one bounded CUDA artifact with exact output hashing and device timestamps")
    gpu_run.add_argument("--artifact", required=True)
    gpu_run.set_defaults(func=gpu_command)
    gpu_plan = gpu_sub.add_parser(
        "plan-synthesize",
        help="synthesize bounded GPU-algorithm, queue-overlap, sparse-policy, or presentation plans",
    )
    gpu_plan.add_argument("--manifest", required=True)
    gpu_plan.add_argument("--out-dir", default="vladder-heterogeneous-plans")
    gpu_plan.set_defaults(func=gpu_command)
    gpu_plan_rank = gpu_sub.add_parser(
        "plan-rank",
        help="physically rank generated heterogeneous plans through an exact application runner",
    )
    gpu_plan_rank.add_argument("--manifest", required=True)
    gpu_plan_rank.add_argument("--out-dir", default="vladder-heterogeneous-ranking")
    gpu_plan_rank.set_defaults(func=gpu_command)
    gpu_project_audit = gpu_sub.add_parser(
        "project-audit",
        help="recognize heterogeneous algorithm and policy binding surfaces without writing the target project",
    )
    gpu_project_audit.add_argument("--project", required=True)
    gpu_project_audit.add_argument("--out-dir", default="vladder-heterogeneous-project-audit")
    gpu_project_audit.set_defaults(func=gpu_command)
    for action, help_text, default_out in (
        ("cuda-synthesize", "extract and generate proved bounded CUDA pointwise schedules", "vladder-cuda-synthesis"),
        ("cuda-optimize", "generate, prove, physically rank, and conditionally emit a CUDA replacement", "vladder-cuda-optimization"),
    ):
        command = gpu_sub.add_parser(action, help=help_text)
        command.add_argument("--source", required=True)
        command.add_argument("--function", required=True)
        command.add_argument("--architecture")
        command.add_argument("--out-dir", default=default_out)
        command.add_argument("--device", type=int, default=0)
        command.add_argument("--n", type=int, default=1 << 26)
        command.add_argument("--threads", default="64,128,256,512")
        command.add_argument("--unroll", default="1,2,4,8")
        command.add_argument("--baseline-threads", type=int, default=256)
        command.add_argument("--warmup", type=int, default=10)
        command.add_argument("--iterations", type=int, default=100)
        command.add_argument("--finalists", type=int, default=8)
        command.add_argument("--bandwidth-n", type=int, default=1 << 25)
        if action == "cuda-optimize":
            command.add_argument("--processes", type=int, default=10)
            command.add_argument("--min-effect", type=float, default=1.0)
            command.add_argument("--bootstrap-rounds", type=int, default=2000)
            command.add_argument("--seed", type=int, default=0)
            command.add_argument("--no-counters", action="store_true")
        command.set_defaults(func=gpu_command)
    for action, help_text, default_out in (
        ("capture", "capture SPIR-V/PTX/CUDA kernel and device protocol graphs", "vladder-gpu-capture"),
        ("synthesize", "enumerate architecture-aware kernel and protocol realization plans", "vladder-gpu-synthesis"),
        ("verify", "verify bounded kernel-capture and device-protocol obligations", "vladder-gpu-proof"),
        ("rank", "rank exact candidates using clean device timing and counter support", "vladder-gpu-ranking"),
    ):
        command = gpu_sub.add_parser(action, help=help_text)
        command.add_argument("--manifest", required=True)
        command.add_argument("--out-dir", default=default_out)
        command.set_defaults(func=gpu_command)
    prior = sub.add_parser("prior", help="build datasets and run the advisory learned search prior")
    prior_sub = prior.add_subparsers(dest="prior_command", required=True)
    prior_sub.add_parser("support", help="show learned-prior authority and capability boundaries").set_defaults(func=prior_command)
    prior_init = prior_sub.add_parser("init", help="create one canonical learned-prior workflow manifest")
    prior_init.add_argument("--out", default="vladder-prior.yaml"); prior_init.set_defaults(func=prior_command)
    prior_run = prior_sub.add_parser("run", help="run dataset, split, training, and shadow evaluation from one manifest")
    prior_run.add_argument("--manifest", required=True); prior_run.add_argument("--out-dir", default="vladder-prior-out"); prior_run.set_defaults(func=prior_command)
    prior_template = prior_sub.add_parser("template", help="create an extensible reference-based training-data template")
    prior_template.add_argument("--out", default="vladder-prior-training-template.yaml"); prior_template.set_defaults(func=prior_command)
    prior_materialize = prior_sub.add_parser("materialize", help="materialize deterministic records and hashes from a training-data template")
    prior_materialize.add_argument("--manifest", required=True); prior_materialize.add_argument("--store", required=True); prior_materialize.set_defaults(func=prior_command)
    prior_matrix = prior_sub.add_parser("evaluate-matrix", help="train and report separate root/project/language/hardware/temporal holdouts")
    prior_matrix.add_argument("--store", required=True); prior_matrix.add_argument("--out-dir", default="vladder-prior-generalization")
    prior_matrix.add_argument("--methods", default="root,project,language,hardware,temporal")
    prior_matrix.add_argument("--ensemble-size", type=int, default=3); prior_matrix.add_argument("--epochs", type=int, default=40)
    prior_matrix.add_argument("--learning-rate", type=float, default=0.08); prior_matrix.add_argument("--seed", type=int, default=4242)
    prior_matrix.add_argument("--budget-fraction", type=float, default=0.1); prior_matrix.add_argument("--exploration-fraction", type=float, default=0.2)
    prior_matrix.set_defaults(func=prior_command)
    prior_generate = prior_sub.add_parser("generate", help="generate the controlled multilingual pilot corpus")
    prior_generate.add_argument("--out-dir", default="vladder-prior-corpus"); prior_generate.add_argument("--roots", type=int, default=60); prior_generate.set_defaults(func=prior_command)
    prior_ingest = prior_sub.add_parser("ingest", help="append an immutable experience bundle")
    prior_ingest.add_argument("--manifest", required=True); prior_ingest.add_argument("--store", required=True); prior_ingest.set_defaults(func=prior_command)
    prior_validate = prior_sub.add_parser("validate", help="validate experience identities, labels, and optional split")
    prior_validate.add_argument("--store", required=True); prior_validate.add_argument("--split"); prior_validate.set_defaults(func=prior_command)
    prior_split = prior_sub.add_parser("split", help="create a root-grouped leakage-safe split")
    prior_split.add_argument("--store", required=True); prior_split.add_argument("--out", default="vladder-prior-split.json")
    prior_split.add_argument("--method", choices=("root", "project", "language", "hardware", "temporal"), default="project")
    prior_split.add_argument("--seed", type=int, default=4242); prior_split.add_argument("--test-fraction", type=float, default=0.2)
    prior_split.add_argument("--calibration-fraction", type=float, default=0.2); prior_split.add_argument("--holdout"); prior_split.set_defaults(func=prior_command)
    prior_train = prior_sub.add_parser("train", help="train a deterministic pooled-graph ensemble pilot")
    prior_train.add_argument("--store", required=True); prior_train.add_argument("--split", required=True); prior_train.add_argument("--out-dir", default="vladder-prior-model")
    prior_train.add_argument("--ensemble-size", type=int, default=5); prior_train.add_argument("--epochs", type=int, default=80)
    prior_train.add_argument("--learning-rate", type=float, default=0.08); prior_train.add_argument("--seed", type=int, default=4242); prior_train.set_defaults(func=prior_command)
    prior_recommend = prior_sub.add_parser("recommend", help="rank one root's legal candidate descriptors")
    prior_recommend.add_argument("--model", required=True); prior_recommend.add_argument("--store", required=True); prior_recommend.add_argument("--root-id", required=True)
    prior_recommend.add_argument("--out", default="vladder-prior-recommendation.json"); prior_recommend.set_defaults(func=prior_command)
    prior_select = prior_sub.add_parser("select", help="select a baseline- and exploration-preserving search budget")
    prior_select.add_argument("--recommendation", required=True); prior_select.add_argument("--store", required=True); prior_select.add_argument("--root-id", required=True)
    prior_select.add_argument("--budget", type=int, required=True); prior_select.add_argument("--exploration-fraction", type=float, default=0.2)
    prior_select.add_argument("--seed", type=int, default=4242); prior_select.add_argument("--out", default="vladder-prior-decision.json"); prior_select.set_defaults(func=prior_command)
    prior_evaluate = prior_sub.add_parser("evaluate", help="run counterfactual shadow search evaluation")
    prior_evaluate.add_argument("--model", required=True); prior_evaluate.add_argument("--store", required=True); prior_evaluate.add_argument("--split", required=True)
    prior_evaluate.add_argument("--partition", choices=("train", "calibration", "test"), default="test")
    prior_evaluate.add_argument("--budget-fraction", type=float, default=0.1); prior_evaluate.add_argument("--exploration-fraction", type=float, default=0.2)
    prior_evaluate.add_argument("--seed", type=int, default=4242); prior_evaluate.add_argument("--out", default="vladder-prior-evaluation.json"); prior_evaluate.set_defaults(func=prior_command)
    schema = sub.add_parser("schema", help="list and validate stable public artifact schemas")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    schema_sub.add_parser("list", help="list stable artifact kinds and compatibility policy").set_defaults(func=schema_command)
    schema_validate = schema_sub.add_parser("validate", help="validate one JSON artifact")
    schema_validate.add_argument("--kind", required=True, choices=tuple(sorted(list_artifact_schemas()["artifacts"])))
    schema_validate.add_argument("--artifact", required=True)
    schema_validate.set_defaults(func=schema_command)
    consent = sub.add_parser("consent", help="show or persist explicit user contribution choices")
    consent_sub = consent.add_subparsers(dest="consent_command", required=True)
    consent_show = consent_sub.add_parser("show", help="show durable opt-in/opt-out state without network access")
    consent_show.add_argument("--consent-file", help=argparse.SUPPRESS)
    consent_show.set_defaults(func=consent_command)
    consent_set = consent_sub.add_parser("set", help="record the user's explicit contribution choice")
    consent_set.add_argument("--scope", required=True, choices=tuple(scope.replace("_", "-") for scope in CONSENT_SCOPES))
    consent_set.add_argument("--decision", required=True, choices=("opt-in", "opt-out"))
    consent_set.add_argument(
        "--confirmed-user-choice", action="store_true",
        help="required assertion that the agent asked and the user explicitly chose this decision",
    )
    consent_set.add_argument("--consent-file", help=argparse.SUPPRESS)
    consent_set.set_defaults(func=consent_command)
    consent_review = consent_sub.add_parser(
        "review-requested", help="record a periodic review request and advance its cadence",
    )
    consent_review.add_argument(
        "--confirmed-user-prompt", action="store_true",
        help="required assertion that the agent actually requested the review",
    )
    consent_review.add_argument("--consent-file", help=argparse.SUPPRESS)
    consent_review.set_defaults(func=consent_command)
    contribution = sub.add_parser("contribution", help="verify scoped release-service contribution access")
    contribution_sub = contribution.add_subparsers(dest="contribution_command", required=True)
    contribution_doctor = contribution_sub.add_parser(
        "doctor", help="probe both opted-in append paths and negative authorization boundaries without storing records",
    )
    contribution_doctor.add_argument("--base-url", default=DEFAULT_CONTRIBUTION_BASE)
    contribution_doctor.add_argument("--timeout", type=float, default=20.0)
    contribution_doctor.set_defaults(func=contribution_command)
    review = sub.add_parser("review", help="create, validate, or explicitly submit a canonical agent review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_template = review_sub.add_parser("template", help="create a strict review record from a promotion summary")
    review_template.add_argument("--promotion-summary", required=True)
    review_template.add_argument("--project", required=True)
    review_template.add_argument("--revision", required=True)
    review_template.add_argument("--repository")
    review_template.add_argument("--out", default="vladder-agent-review.json")
    review_template.set_defaults(func=review_command)
    review_campaign = review_sub.add_parser("campaign-template", help="create one prepopulated review across multiple terminal workflows")
    review_campaign.add_argument("--promotion-summary", action="append", required=True)
    review_campaign.add_argument("--project", required=True)
    review_campaign.add_argument("--revision", required=True)
    review_campaign.add_argument("--repository")
    review_campaign.add_argument("--out", default="vladder-agent-campaign-review.json")
    review_campaign.set_defaults(func=review_command)
    review_validate = review_sub.add_parser("validate", help="validate a review without network access")
    review_validate.add_argument("--review", required=True)
    review_validate.set_defaults(func=review_command)
    review_submit = review_sub.add_parser("submit", help="submit only a validated review record after explicit consent")
    review_submit.add_argument("--review", required=True)
    review_submit.add_argument("--endpoint", help="override the public review endpoint or VLADDER_REVIEW_ENDPOINT")
    review_submit.add_argument("--confirm-upload", action="store_true", help="required explicit consent gate")
    review_submit.add_argument("--validate-only", action="store_true", help="validate through the service without storing")
    review_submit.add_argument("--timeout", type=float, default=20.0)
    review_submit.add_argument("--consent-file", help=argparse.SUPPRESS)
    review_submit.set_defaults(func=review_command)
    training = sub.add_parser(
        "training", help="create, validate, or explicitly submit graph-ready v2 training data",
    )
    training_sub = training.add_subparsers(dest="training_command", required=True)
    training_template = training_sub.add_parser(
        "template", help="create a strict graph-ready v2 training bundle",
    )
    training_template.add_argument("--out", default="vladder-model-training-bundle-v2.json")
    training_template.set_defaults(func=training_command)
    training_prior = training_sub.add_parser("from-prior", help="derive a source-free bundle from a local canonical prior store")
    training_prior.add_argument("--store", required=True)
    training_prior.add_argument("--project-id", required=True, help="opaque project identifier, not a repository path")
    training_prior.add_argument("--agent", required=True)
    training_prior.add_argument("--model", required=True)
    training_prior.add_argument("--provider")
    training_prior.add_argument("--maximum-examples", type=int, default=8)
    training_prior.add_argument(
        "--apply-durable-consent", action="store_true",
        help="set record consent from the saved training opt-in for continuous contribution",
    )
    training_prior.add_argument("--consent-file", help=argparse.SUPPRESS)
    training_prior.add_argument("--out", default="vladder-model-training-bundle-v2.json")
    training_prior.set_defaults(func=training_command)
    training_export = training_sub.add_parser(
        "export-prior", help="export every supported anonymized prior record into bounded bundles",
    )
    training_export.add_argument("--store", required=True)
    training_export.add_argument("--project-id", required=True, help="identifier is hashed before export")
    training_export.add_argument("--agent", required=True)
    training_export.add_argument("--model", required=True)
    training_export.add_argument("--provider")
    training_export.add_argument("--examples-per-bundle", type=int, default=12)
    training_export.add_argument("--apply-durable-consent", action="store_true")
    training_export.add_argument("--consent-file", help=argparse.SUPPRESS)
    training_export.add_argument("--out-dir", default="vladder-training-export")
    training_export.set_defaults(func=training_command)
    training_sync = training_sub.add_parser(
        "sync-prior", help="continuously export and submit all supported anonymized prior records after opt-in",
    )
    training_sync.add_argument("--store", required=True)
    training_sync.add_argument("--project-id", required=True, help="identifier is hashed before export")
    training_sync.add_argument("--agent", required=True)
    training_sync.add_argument("--model", required=True)
    training_sync.add_argument("--provider")
    training_sync.add_argument("--examples-per-bundle", type=int, default=12)
    training_sync.add_argument("--endpoint", help="override VLADDER_MODEL_TRAINING_ENDPOINT")
    training_sync.add_argument("--validate-only", action="store_true")
    training_sync.add_argument("--timeout", type=float, default=20.0)
    training_sync.add_argument("--consent-file", help=argparse.SUPPRESS)
    training_sync.add_argument("--out-dir", default="vladder-training-sync")
    training_sync.set_defaults(func=training_command)
    training_validate = training_sub.add_parser("validate", help="validate a training bundle without network access")
    training_validate.add_argument("--bundle", required=True)
    training_validate.set_defaults(func=training_command)
    training_ingest = training_sub.add_parser(
        "ingest-model", help="ingest a validated v2 graph/action/outcome bundle into a local prior store",
    )
    training_ingest.add_argument("--bundle", required=True)
    training_ingest.add_argument("--store", required=True)
    training_ingest.set_defaults(func=training_command)
    training_graph = training_sub.add_parser(
        "graph-examples", help="emit topology-preserving candidate/ranking examples as JSONL",
    )
    training_graph.add_argument("--bundle", required=True)
    training_graph.add_argument("--out", default="vladder-graph-learning-examples.jsonl")
    training_graph.set_defaults(func=training_command)
    training_submit = training_sub.add_parser(
        "submit", help="submit only a validated graph-ready v2 bundle after explicit consent",
    )
    training_submit.add_argument("--bundle", required=True)
    training_submit.add_argument(
        "--endpoint", help="override the public v2 endpoint or VLADDER_MODEL_TRAINING_ENDPOINT",
    )
    training_submit.add_argument("--confirm-upload", action="store_true", help="required explicit consent gate")
    training_submit.add_argument("--validate-only", action="store_true", help="validate through the service without storing")
    training_submit.add_argument("--timeout", type=float, default=20.0)
    training_submit.add_argument("--consent-file", help=argparse.SUPPRESS)
    training_submit.set_defaults(func=training_command)
    skill = sub.add_parser("skill", help="validate or install the bundled coding-agent skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_validate = skill_sub.add_parser("validate", help="validate the bundled or specified skill")
    skill_validate.add_argument("--path", help="alternate skill directory")
    skill_validate.set_defaults(func=skill_command)
    skill_install = skill_sub.add_parser("install", help="install the skill under an agent skills directory")
    skill_install.add_argument("--target", default=str(Path.home() / ".codex" / "skills"), help="parent directory for the vladder skill")
    skill_install.add_argument("--force", action="store_true", help="replace a differing existing skill")
    skill_install.set_defaults(func=skill_command)
    lifetime = sub.add_parser("lifetime", help="attribute and synthesize semantic realization lifetimes")
    lifetime_sub = lifetime.add_subparsers(dest="lifetime_command", required=True)
    for action, help_text, default_out in (
        ("analyze", "build LifetimeFlowGraph and attribute repeated or over-retained realizations", "vladder-lifetime-analysis"),
        ("synthesize", "enumerate, prove, and emit bounded lifetime realization plans", "vladder-lifetime-out"),
        ("evaluate-corpus", "run discovery, proof, deterministic replay, and isolated microbenchmarks", "vladder-lifetime-evaluation"),
    ):
        command = lifetime_sub.add_parser(action, help=help_text)
        command.add_argument("--manifest", required=True)
        command.add_argument("--trace", required=True)
        command.add_argument("--out-dir", default=default_out)
        command.set_defaults(func=lifetime_command)
    can_optimize = sub.add_parser("can-optimize", help="forecast routing, semantic reachability, cost, and grammar coverage before execution")
    can_optimize.add_argument("symbol", help="source-level symbol or function name")
    can_optimize.add_argument("--source", required=True, help="production source containing the selected symbol")
    can_optimize.add_argument("--project", default=".", help="project root used for evidence discovery")
    can_optimize.add_argument("--compile-commands", help="compilation database file or directory")
    can_optimize.add_argument("--contract", help="existing contract manifest")
    can_optimize.add_argument("--workload", help="existing workload manifest")
    can_optimize.add_argument("--profile", help="profile containing regional runtime share")
    can_optimize.add_argument("--out-dir", default="vladder-plan", help="plan and scaffold directory")
    can_optimize.add_argument("--min-speedup-pct", type=float, default=1.0)
    can_optimize.add_argument("--json", action="store_true", help="also print the complete plan")
    can_optimize.add_argument("--quiet", action="store_true", help="suppress progress events on stdout")
    can_optimize.add_argument("--force", action="store_true", help="recompute content-addressed planning stages")
    can_optimize.set_defaults(func=can_optimize_command)
    resume = sub.add_parser("resume", help="resume an optimization campaign from the first invalid content-addressed stage")
    resume.add_argument("--out-dir", required=True, help="existing orchestration output directory")
    resume.add_argument("--force", action="store_true", help="recompute matching stages")
    resume.add_argument("--quiet", action="store_true", help="suppress progress events on stdout")
    resume.set_defaults(func=resume_command)
    runner = sub.add_parser("runner", help="validate physical or remote runner evidence envelopes")
    runner_sub = runner.add_subparsers(dest="runner_command", required=True)
    runner_verify = runner_sub.add_parser("verify", help="verify remote result identity and optional HMAC integrity")
    runner_verify.add_argument("--request", required=True, help="immutable JSON/YAML request manifest")
    runner_verify.add_argument("--result", required=True, help="remote result JSON")
    runner_verify.add_argument("--key-environment", default="VLADDER_REMOTE_RESULT_KEY")
    runner_verify.add_argument("--out")
    runner_verify.set_defaults(func=runner_command)
    runner_execute = runner_sub.add_parser("execute", help="invoke an argv-form remote executor and verify its immutable result bundle")
    runner_execute.add_argument("--manifest", required=True)
    runner_execute.add_argument("--out-dir", default="vladder-remote-run")
    runner_execute.set_defaults(func=runner_command)
    opt = sub.add_parser("optimize", help="classify, plan, execute, prove, benchmark, and disposition one region or repository portfolio")
    opt.add_argument("source", nargs="?", help="production source file; existing C99 invocation remains supported")
    opt.add_argument("--function", "--symbol", dest="function", help="function or symbol to optimize")
    opt.add_argument("--project", default=".", help="project root used for evidence and portfolio discovery")
    opt.add_argument("--compile-commands", help="compilation database file or directory")
    opt.add_argument("--contract", help="semantic contract manifest")
    opt.add_argument("--workload", help="project workload manifest")
    opt.add_argument("--profile", help="profile containing regional runtime share")
    opt.add_argument("--plan-only", action="store_true", help="emit plan and scaffolds without extraction, proof, benchmark, contribution, or source changes")
    opt.add_argument("--portfolio", action="store_true", help="inventory and disposition a repository-wide region portfolio")
    opt.add_argument("--execute-portfolio", action="store_true", help="execute portfolio regions instead of planning only")
    opt.add_argument("--max-regions", type=int, default=20, help="maximum portfolio regions")
    opt.add_argument("--workers", type=int, default=4, help="parallel portfolio planning and execution workers")
    opt.add_argument("--strict-progress-exit", action="store_true", help="return evidence-state-specific nonzero exit codes")
    opt.add_argument("--json", action="store_true", help="also print the complete terminal plan or disposition")
    opt.add_argument("--verbose", action="store_true", help="retain verbose planning context in output")
    opt.add_argument("--quiet", action="store_true", help="suppress progress events on stdout")
    opt.add_argument("--force", action="store_true", help="recompute matching content-addressed stages")
    opt.add_argument("--out-dir", default="vladder-out", help="artifact directory")
    opt.add_argument("--n", type=int, default=1 << 20, help="benchmark element count")
    opt.add_argument("--reps", type=int, default=25, help="timed repetitions")
    opt.add_argument("--inner", type=int, default=8, help="calls per timed repetition")
    opt.add_argument("--cpu", type=int, default=0, help="CPU index for sched_setaffinity")
    opt.add_argument("--assume-no-alias", action="store_true", help="allow candidates that require non-overlapping dst/src")
    opt.add_argument("--flush-cache", action="store_true", help="touch a 64 MiB buffer before each sample")
    opt.add_argument("--perf", action="store_true", help="also attempt perf stat counter collection")
    opt.add_argument("--allow-unproved", action="store_true", help="benchmark candidates even when no formal proof schema is available")
    opt.add_argument("--alive2", action="store_true", help="run Alive2 translation validation on sanitized candidate LLVM IR")
    opt.add_argument("--verification-policy", choices=tuple(item.value for item in VerificationPolicy), default="strict", help="proof policy controlling patch promotion")
    opt.add_argument("--min-speedup-pct", type=float, default=1.0, help="minimum measured speedup required for patch promotion")
    opt.add_argument("--graph-inner-loop", action="store_true", help="generate candidates from information-flow graph grammar")
    opt.add_argument("--search-nodes", type=int, default=64, help="maximum grammar/e-graph states")
    opt.add_argument("--search-ms", type=int, default=1000, help="grammar search time budget in milliseconds")
    opt.add_argument("--llm-lift", action="store_true", help="ask DeepSeek to propose C through the zero-trust verifier loop")
    opt.add_argument("--llm-rounds", type=int, default=3, help="maximum DeepSeek verifier-feedback rounds")
    opt.set_defaults(func=orchestrated_optimize_command)
    analyze = sub.add_parser("analyze", help="emit target-only IR and information-flow graph artifacts")
    analyze.add_argument("source", help="C99 source file")
    analyze.add_argument("--function", required=True, help="function name to analyze")
    analyze.add_argument("--out-dir", default="vladder-analysis", help="artifact directory")
    analyze.set_defaults(func=analyze_function)
    corpus = sub.add_parser("corpus", help="run optimize over every .c file in a directory")
    corpus.add_argument("directory", help="directory containing benchmark kernels")
    corpus.add_argument("--out-dir", default="vladder-corpus-out", help="artifact directory")
    corpus.add_argument("--function", default="transform", help="function name to optimize")
    corpus.add_argument("--n", type=int, default=1 << 18, help="benchmark element count")
    corpus.add_argument("--reps", type=int, default=10, help="timed repetitions per candidate")
    corpus.add_argument("--inner", type=int, default=8, help="calls per timed repetition")
    corpus.add_argument("--cpu", type=int, default=0, help="CPU index for sched_setaffinity")
    corpus.add_argument("--assume-no-alias", action="store_true", help="allow candidates that require non-overlapping dst/src")
    corpus.add_argument("--perf", action="store_true", help="attempt perf stat counter collection")
    corpus.add_argument("--allow-unproved", action="store_true", help="benchmark candidates even when no formal proof schema is available")
    corpus.add_argument("--alive2", action="store_true", help="run Alive2 translation validation on sanitized candidate LLVM IR")
    corpus.add_argument("--verification-policy", choices=tuple(item.value for item in VerificationPolicy), default="strict", help="proof policy controlling patch promotion")
    corpus.add_argument("--min-speedup-pct", type=float, default=1.0, help="minimum measured speedup required for patch promotion")
    corpus.add_argument("--graph-inner-loop", action="store_true", help="generate candidates from information-flow graph grammar")
    corpus.add_argument("--search-nodes", type=int, default=64, help="maximum grammar/e-graph states")
    corpus.add_argument("--search-ms", type=int, default=1000, help="grammar search time budget in milliseconds")
    corpus.add_argument("--llm-lift", action="store_true", help="run zero-trust DeepSeek C reconstruction where configured")
    corpus.add_argument("--llm-rounds", type=int, default=3, help="maximum DeepSeek verifier-feedback rounds per kernel")
    corpus.set_defaults(func=run_corpus)
    operator = sub.add_parser("operator", help="analyze or optimize a fused streaming operator")
    operator_sub = operator.add_subparsers(dest="operator_command", required=True)
    operator_analyze = operator_sub.add_parser("analyze", help="validate a contract and emit OperatorGraph/LLVM artifacts")
    operator_analyze.add_argument("--source", required=True, help="C17 or restricted C++20 source")
    operator_analyze.add_argument("--contract", required=True, help="operator YAML/JSON semantic contract")
    operator_analyze.add_argument("--out-dir", default="vladder-operator-analysis", help="artifact directory")
    operator_analyze.add_argument("--target", default="local", help="target manifest name")
    operator_analyze.add_argument("--cpu", type=int, default=0, help="pinned CPU identity")
    operator_analyze.set_defaults(func=analyze_operator_command)
    operator_optimize = operator_sub.add_parser("optimize", help="search, verify, benchmark, and lift an OperatorGraph")
    operator_optimize.add_argument("--source", required=True, help="C17 or restricted C++20 source")
    operator_optimize.add_argument("--contract", required=True, help="operator YAML/JSON semantic contract")
    operator_optimize.add_argument("--out-dir", default="vladder-operator-out", help="artifact directory")
    operator_optimize.add_argument("--target", default="local", help="target manifest name")
    operator_optimize.add_argument("--cpu", type=int, default=0, help="pinned CPU")
    operator_optimize.add_argument("--processes", type=int, default=3, help="independent benchmark processes")
    operator_optimize.add_argument("--samples", type=int, default=2000, help="raw cycle samples per process")
    operator_optimize.add_argument("--beam-width", type=int, default=24, help="operator composition beam width")
    operator_optimize.set_defaults(func=optimize_operator_command)
    pipeline = sub.add_parser("pipeline", help="optimize an integrated stateful pipeline")
    pipeline_sub = pipeline.add_subparsers(dest="pipeline_command", required=True)
    pipeline_optimize = pipeline_sub.add_parser("optimize", help="verify and benchmark HFT pipeline candidates")
    pipeline_optimize.add_argument("--source", required=True, help="C17 pipeline source")
    pipeline_optimize.add_argument("--contract", required=True, help="pipeline semantic contract")
    pipeline_optimize.add_argument("--trace", help="optional external held-out market_replay_v1 trace")
    pipeline_optimize.add_argument("--objective", default="p99_9_cycles", choices=("p99_9_cycles", "p99_99_cycles"))
    pipeline_optimize.add_argument("--out-dir", default="vladder-pipeline-out")
    pipeline_optimize.add_argument("--target", default="local")
    pipeline_optimize.add_argument("--cpu", type=int, default=0)
    pipeline_optimize.add_argument("--processes", type=int, default=3)
    pipeline_optimize.add_argument("--samples", type=int, default=12000)
    pipeline_optimize.add_argument("--beam-width", type=int, default=24)
    pipeline_optimize.set_defaults(func=optimize_pipeline_command)
    pipeline_analyze_v4 = pipeline_sub.add_parser("analyze-v4", help="construct and analyze a hierarchical PipelineGraph")
    pipeline_analyze_v4.add_argument("--manifest", required=True)
    pipeline_analyze_v4.add_argument("--out-dir", default="vladder-pipeline-v4-analysis")
    pipeline_analyze_v4.set_defaults(func=analyze_pipeline_v4_command)
    pipeline_optimize_v4 = pipeline_sub.add_parser("optimize-v4", help="search and verify the hierarchical pipeline grammar")
    pipeline_optimize_v4.add_argument("--manifest", required=True)
    pipeline_optimize_v4.add_argument("--out-dir", default="vladder-pipeline-v4-out")
    pipeline_optimize_v4.add_argument("--beam-width", type=int, default=24)
    pipeline_optimize_v4.add_argument("--max-depth", type=int, default=5)
    pipeline_optimize_v4.add_argument("--child-budget", type=int, default=64)
    pipeline_optimize_v4.add_argument("--ggml-graph", help="normalized authoritative llama.cpp graph JSON")
    pipeline_optimize_v4.add_argument("--profile-report", help="instrumented ggml baseline attribution report")
    pipeline_optimize_v4.set_defaults(func=optimize_pipeline_v4_command)
    projection = sub.add_parser("projection", help="analyze, profile, or synthesize a quantized projection complex")
    projection_sub = projection.add_subparsers(dest="projection_command", required=True)
    projection_analyze = projection_sub.add_parser("analyze", help="validate and cost a ProjectionComplexGraph")
    projection_analyze.add_argument("--manifest", required=True)
    projection_analyze.add_argument("--out-dir", default="vladder-projection-v5-analysis")
    projection_analyze.set_defaults(func=analyze_projection_v5_command)
    projection_profile = projection_sub.add_parser("profile", help="decompose the pinned llama.cpp Q4_K projection path")
    projection_profile.add_argument("--llama-root", default="third_party/llama.cpp")
    projection_profile.add_argument("--model", required=True)
    projection_profile.add_argument("--out-dir", default="vladder-projection-v5-profile")
    projection_profile.add_argument("--cpu-list", default="0-7")
    projection_profile.add_argument("--threads", type=int, default=8)
    projection_profile.add_argument("--prompt-tokens", type=int, default=128)
    projection_profile.add_argument("--generation-tokens", type=int, default=8)
    projection_profile.add_argument("--microbatch", type=int, default=128)
    projection_profile.set_defaults(func=profile_projection_v5_command)
    projection_synthesize = projection_sub.add_parser("synthesize", help="search and structurally verify the projection grammar")
    projection_synthesize.add_argument("--manifest", required=True)
    projection_synthesize.add_argument("--out-dir", default="vladder-projection-v5-out")
    projection_synthesize.add_argument("--beam-width", type=int, default=32)
    projection_synthesize.add_argument("--max-depth", type=int, default=7)
    projection_synthesize.add_argument("--child-budget", type=int, default=64)
    projection_synthesize.set_defaults(func=synthesize_projection_v5_command)
    projection_layout = projection_sub.add_parser("transform-layout", help="exactly interleave opaque sibling weight blocks")
    projection_layout.add_argument("--input", action="append", required=True, help="sibling block payload; repeat for each projection")
    projection_layout.add_argument("--block-bytes", type=int, required=True)
    projection_layout.add_argument("--out-dir", default="vladder-projection-layout-v5")
    projection_layout.set_defaults(func=transform_projection_layout_v5_command)
    sksf = sub.add_parser("sksf", help="run attribution-gated kernel superoptimization workflows")
    sksf_sub = sksf.add_subparsers(dest="sksf_command", required=True)
    sksf_attribution = sksf_sub.add_parser("validate-attribution", help="validate and hash attribution studies")
    sksf_attribution.add_argument("--study", action="append", required=True)
    sksf_attribution.add_argument("--out", default="vladder-sksf-attribution.json")
    sksf_attribution.set_defaults(func=validate_sksf_attribution_command)
    sksf_synthesize = sksf_sub.add_parser("synthesize", help="run attribution-gated KernelGraph search")
    sksf_synthesize.add_argument("--manifest", required=True, help="ProjectionComplexGraph manifest")
    sksf_synthesize.add_argument("--study", action="append", required=True, help="attribution study; repeatable")
    sksf_synthesize.add_argument("--grammar-dir", default=str(Path(__file__).resolve().parent / "grammars/kernel-v6"))
    sksf_synthesize.add_argument("--out-dir", default="vladder-sksf-v6-out")
    sksf_synthesize.add_argument("--beam-width", type=int, default=32)
    sksf_synthesize.add_argument("--max-depth", type=int, default=6)
    sksf_synthesize.add_argument("--allow-exploratory", action="store_true")
    sksf_synthesize.set_defaults(func=synthesize_sksf_command)
    sksf_portfolio = sksf_sub.add_parser("rank-portfolio", help="rank independent-process tokens/sec measurements")
    sksf_portfolio.add_argument("--portfolio", required=True)
    sksf_portfolio.add_argument("--measurements", required=True)
    sksf_portfolio.add_argument("--out", default="vladder-sksf-portfolio-rank.json")
    sksf_portfolio.add_argument("--bootstrap-rounds", type=int, default=4000)
    sksf_portfolio.add_argument("--seed", type=int, default=0)
    sksf_portfolio.set_defaults(func=rank_sksf_portfolio_command)
    sksf_lab = sksf_sub.add_parser("kernel-lab", help="compile, verify, and benchmark the exact synthetic low-bit kernel grammar")
    sksf_lab.add_argument("--out-dir", default="vladder-sksf-kernel-lab")
    sksf_lab.add_argument("--cpu", type=int, default=0)
    sksf_lab.add_argument("--processes", type=int, default=10)
    sksf_lab.add_argument("--repetitions", type=int, default=15)
    sksf_lab.add_argument("--seed", type=int, default=0)
    sksf_lab.set_defaults(func=run_sksf_kernel_lab_command)
    q4k = sub.add_parser("q4k", help="capture and reconstruct the production Q4_K kernel path")
    q4k_sub = q4k.add_subparsers(dest="q4k_command", required=True)
    q4k_capture = q4k_sub.add_parser("capture", help="capture and enforce the active llama.cpp Q4_K dispatch")
    q4k_capture.add_argument("--llama-root", default="third_party/llama.cpp")
    q4k_capture.add_argument("--model", required=True)
    q4k_capture.add_argument("--out-dir", default="vladder-q4k-v7-capture")
    q4k_capture.add_argument("--cpu-list", default="0-7")
    q4k_capture.add_argument("--threads", type=int, default=8)
    q4k_capture.add_argument("--prompt-tokens", type=int, default=16)
    q4k_capture.add_argument("--expected-kernel", default="ggml_gemv_q4_K_8x8_q8_K")
    q4k_capture.set_defaults(func=capture_q4k_v7_command)
    q4k_reconstruct = q4k_sub.add_parser("reconstruct", help="reconstruct Q4_K/Q8_K block, repack, and graph semantics")
    q4k_reconstruct.add_argument("--manifest", required=True)
    q4k_reconstruct.add_argument("--out-dir", default="vladder-q4k-v7-reconstruct")
    q4k_reconstruct.add_argument("--random-cases", type=int, default=128)
    q4k_reconstruct.add_argument("--seed", type=int, default=7007)
    q4k_reconstruct.set_defaults(func=reconstruct_q4k_v7_command)
    q4k_parity = q4k_sub.add_parser("parity", help="regenerate the native AVX2 kernel and enforce E1/performance parity")
    q4k_parity.add_argument("--manifest", required=True)
    q4k_parity.add_argument("--out-dir", default="vladder-q4k-v7-parity")
    q4k_parity.add_argument("--processes", type=int, default=10)
    q4k_parity.add_argument("--repetitions", type=int, default=25)
    q4k_parity.add_argument("--inner", type=int, default=4)
    q4k_parity.add_argument("--seed", type=int, default=7707)
    q4k_parity.set_defaults(func=parity_q4k_v7_command)
    q4k_synthesize = q4k_sub.add_parser("synthesize", help="enumerate and benchmark the narrow production gate/up sibling grammar")
    q4k_synthesize.add_argument("--manifest", required=True)
    q4k_synthesize.add_argument("--parity-report", required=True)
    q4k_synthesize.add_argument("--complex", default="gate-up", choices=("gate-up",))
    q4k_synthesize.add_argument("--out-dir", default="vladder-q4k-v7-sibling")
    q4k_synthesize.add_argument("--processes", type=int, default=10)
    q4k_synthesize.add_argument("--repetitions", type=int, default=25)
    q4k_synthesize.add_argument("--inner", type=int, default=2)
    q4k_synthesize.add_argument("--seed", type=int, default=7717)
    q4k_synthesize.set_defaults(func=synthesize_q4k_v7_command)
    q4k_verify_model = q4k_sub.add_parser("verify-model", help="execute the regenerated E1 baseline through the pinned Qwen model")
    q4k_verify_model.add_argument("--manifest", required=True)
    q4k_verify_model.add_argument("--parity-report", required=True)
    q4k_verify_model.add_argument("--out-dir", default="vladder-q4k-v7-model-verify")
    q4k_verify_model.add_argument("--prompt", default="Write one sentence about compiler verification.")
    q4k_verify_model.add_argument("--generated-tokens", type=int, default=16)
    q4k_verify_model.add_argument("--seed", type=int, default=4242)
    q4k_verify_model.set_defaults(func=verify_q4k_model_v7_command)
    q4k_decompose = q4k_sub.add_parser("decompose-v8", help="physically decompose Q4_K execution and estimate improvement ceilings")
    q4k_decompose.add_argument("--manifest", required=True)
    q4k_decompose.add_argument("--reconstruction-report", required=True)
    q4k_decompose.add_argument("--parity-report", required=True)
    q4k_decompose.add_argument("--out-dir", default="vladder-q4k-v8")
    q4k_decompose.add_argument("--cpu", type=int, default=0)
    q4k_decompose.add_argument("--baseline-processes", type=int, default=20)
    q4k_decompose.add_argument("--baseline-repetitions", type=int, default=50)
    q4k_decompose.add_argument("--ablation-processes", type=int, default=10)
    q4k_decompose.add_argument("--ablation-repetitions", type=int, default=25)
    q4k_decompose.add_argument("--seed", type=int, default=8808)
    q4k_decompose.set_defaults(func=decompose_q4k_v8_command)
    q4k_reuse = q4k_sub.add_parser("synthesize-v9", help="synthesize and physically evaluate weight-reuse execution plans")
    q4k_reuse.add_argument("--manifest", required=True)
    q4k_reuse.add_argument("--v8-report", required=True)
    q4k_reuse.add_argument("--llama-root", default="third_party/llama.cpp")
    q4k_reuse.add_argument("--out-dir", default="vladder-weight-reuse-v9")
    q4k_reuse.add_argument("--cpu-list", default="0-7")
    q4k_reuse.add_argument("--threads", type=int, default=8)
    q4k_reuse.add_argument("--processes", type=int, default=3)
    q4k_reuse.add_argument("--seed", type=int, default=9009)
    q4k_reuse.set_defaults(func=synthesize_weight_reuse_v9_command)
    token = sub.add_parser("token", help="run pinned token-generation integrations")
    token_sub = token.add_subparsers(dest="token_command", required=True)
    token_llama = token_sub.add_parser("benchmark-llama", help="benchmark the graph-derived llama.cpp fusion")
    token_llama.add_argument("--llama-root", default="third_party/llama.cpp")
    token_llama.add_argument("--out-dir", default="vladder-llama-out")
    token_llama.add_argument("--cpu", type=int, default=0)
    token_llama.add_argument("--processes", type=int, default=3)
    token_llama.add_argument("--samples", type=int, default=12000)
    token_llama.add_argument("--dimension", type=int, default=4096)
    token_llama.set_defaults(func=benchmark_llama_command)
    token_model = token_sub.add_parser("benchmark-model", help="benchmark a GGUF model with the pinned graph fusion")
    token_model.add_argument("--llama-root", default="third_party/llama.cpp")
    token_model.add_argument("--model", required=True)
    token_model.add_argument("--out-dir", default="vladder-qwen-model-out")
    token_model.add_argument("--cpu-list", default="0-7")
    token_model.add_argument("--threads", type=int, default=8)
    token_model.add_argument("--processes", type=int, default=5)
    token_model.add_argument("--repetitions", type=int, default=5)
    token_model.add_argument("--prompt-tokens", type=int, default=128)
    token_model.add_argument("--generation-tokens", type=int, default=32)
    token_model.set_defaults(func=benchmark_llama_model_command)
    token_extract = token_sub.add_parser("extract-graph-v4", help="dump and normalize the pinned llama.cpp decode graph")
    token_extract.add_argument("--llama-root", default="third_party/llama.cpp")
    token_extract.add_argument("--model", required=True)
    token_extract.add_argument("--out-dir", default="vladder-ggml-graph-v4")
    token_extract.add_argument("--cpu-list", default="0-7")
    token_extract.add_argument("--threads", type=int, default=8)
    token_extract.set_defaults(func=extract_llama_graph_v4_command)
    token_profile = token_sub.add_parser("profile-graph-v4", help="attribute synchronized CPU time to normalized decode graph regions")
    token_profile.add_argument("--llama-root", default="third_party/llama.cpp")
    token_profile.add_argument("--model", required=True)
    token_profile.add_argument("--graph", required=True)
    token_profile.add_argument("--out-dir", default="vladder-ggml-profile-v4")
    token_profile.add_argument("--cpu-list", default="0-7")
    token_profile.add_argument("--threads", type=int, default=8)
    token_profile.add_argument("--tokens", type=int, default=16)
    token_profile.add_argument("--context-tokens", type=int, default=0)
    token_profile.set_defaults(func=profile_llama_graph_v4_command)
    return parser


def analyze_operator_command(args: argparse.Namespace) -> int:
    contract, graph, summary = analyze_operator(Path(args.source), Path(args.contract), Path(args.out_dir), args.target, args.cpu)
    print(f"vLadder operator: {contract.name}")
    print(f"vLadder operator: contract={contract.contract_hash[:16]} graph={graph.graph_hash[:16]}")
    print(f"vLadder operator: {summary['node_count']} nodes, {summary['edge_count']} edges")
    print(f"vLadder operator: wrote {Path(args.out_dir).resolve()}")
    return 0


def optimize_operator_command(args: argparse.Namespace) -> int:
    report = optimize_operator(Path(args.source), Path(args.contract), Path(args.out_dir), args.target, args.cpu, args.processes, args.samples, args.beam_width)
    winner = report.get("winner") or {}
    print(f"vLadder operator: winner={winner.get('candidate', 'none')}")
    if winner:
        print(f"vLadder operator: p50={winner['latency_cycles']['p50']:.1f} cycles speedup={winner.get('p50_speedup_pct', 0.0):.3f}%")
    print(f"vLadder operator: wrote {Path(args.out_dir).resolve()}")
    return 0


def optimize_pipeline_command(args: argparse.Namespace) -> int:
    report = optimize_hft_pipeline(Path(args.source), Path(args.contract), Path(args.out_dir), args.target, args.cpu, args.processes, args.samples, args.beam_width, Path(args.trace) if args.trace else None)
    winner = report.get("winner") or {}
    latency = winner.get("latency", {}).get("microburst8_held_out", {})
    print(f"vLadder pipeline: winner={winner.get('candidate', 'none')}")
    if latency:
        print(f"vLadder pipeline: p50={latency['p50']:.1f} p99.9={latency['p99_9']:.1f} p99.99={latency['p99_99']:.1f} cycles")
    print(f"vLadder pipeline: wrote {Path(args.out_dir).resolve()}")
    return 0


def analyze_pipeline_v4_command(args: argparse.Namespace) -> int:
    summary = analyze_pipeline_v4(Path(args.manifest), Path(args.out_dir))
    print(f"vLadder pipeline-v4: graph={summary['graph_hash'][:16]} nodes={summary['node_count']} edges={summary['edge_count']}")
    print(f"vLadder pipeline-v4: max-live={summary['max_live_logical_bytes']} logical bytes")
    print(f"vLadder pipeline-v4: wrote {Path(args.out_dir).resolve()}")
    return 0


def optimize_pipeline_v4_command(args: argparse.Namespace) -> int:
    report = optimize_pipeline_v4(
        Path(args.manifest), Path(args.out_dir), args.beam_width, args.max_depth, args.child_budget,
        Path(args.ggml_graph) if args.ggml_graph else None, Path(args.profile_report) if args.profile_report else None,
    )
    winner = report.get("winner") or {}
    print(f"vLadder pipeline-v4: winner={(winner.get('plan') or {}).get('id', 'none')}")
    print(f"vLadder pipeline-v4: physical-measurement={report['physical_measurement']['status']}")
    print(f"vLadder pipeline-v4: wrote {Path(args.out_dir).resolve()}")
    return 0


def analyze_projection_v5_command(args: argparse.Namespace) -> int:
    report = analyze_projection_v5(Path(args.manifest), Path(args.out_dir))
    print(f"vLadder projection-v5: complex={report['complex']} graph={report['graph_hash'][:16]}")
    print(f"vLadder projection-v5: physical-measurement={report['physical_measurement']['status']}")
    print(f"vLadder projection-v5: wrote {Path(args.out_dir).resolve()}")
    return 0


def synthesize_projection_v5_command(args: argparse.Namespace) -> int:
    report = synthesize_projection_v5(Path(args.manifest), Path(args.out_dir), args.beam_width, args.max_depth, args.child_budget)
    plan = report["winner"]["plan"]
    print(f"vLadder projection-v5: winner={plan['id']} search={report['search']['status']}")
    print(f"vLadder projection-v5: physical-measurement={report['physical_measurement']['status']}")
    print(f"vLadder projection-v5: wrote {Path(args.out_dir).resolve()}")
    return 0


def profile_projection_v5_command(args: argparse.Namespace) -> int:
    report = profile_llama_projection_path(Path(args.llama_root), Path(args.model), Path(args.out_dir), args.cpu_list, args.threads, args.prompt_tokens, args.generation_tokens, args.microbatch)
    print(f"vLadder projection-v5: samples={report['sample_count']} token-regimes={','.join(report['token_count_regimes'])}")
    print("vLadder projection-v5: measurement=instrumented-attribution-not-ranking")
    print(f"vLadder projection-v5: wrote {Path(args.out_dir).resolve()}")
    return 0


def transform_projection_layout_v5_command(args: argparse.Namespace) -> int:
    report = transform_projection_layout_v5([Path(path) for path in args.input], args.block_bytes, Path(args.out_dir))
    proof = report["proof"]
    print(f"vLadder projection-v5: layout-proof={proof['status']} blocks={proof['block_identity_count']}")
    print(f"vLadder projection-v5: wrote {Path(args.out_dir).resolve()}")
    return 0


def validate_sksf_attribution_command(args: argparse.Namespace) -> int:
    report = validate_attribution_v6([Path(path) for path in args.study], Path(args.out))
    print(f"vLadder SKSF: attribution={report['status']} studies={report['study_count']}")
    print(f"vLadder SKSF: wrote {Path(args.out).resolve()}")
    return 0


def synthesize_sksf_command(args: argparse.Namespace) -> int:
    report = synthesize_kernel_v6(
        Path(args.manifest), [Path(path) for path in args.study], Path(args.grammar_dir), Path(args.out_dir),
        beam_width=args.beam_width, max_depth=args.max_depth, allow_exploratory=args.allow_exploratory,
    )
    admissions = report["search"]["admissions"]
    counts = {state: sum(item["state"] == state for item in admissions) for state in ("admitted", "exploratory", "rejected")}
    print(f"vLadder SKSF: graph={report['kernel_graph']['graph_hash'][:16]} explored={report['search']['explored']}")
    print(f"vLadder SKSF: grammar admitted={counts['admitted']} exploratory={counts['exploratory']} rejected={counts['rejected']}")
    print(f"vLadder SKSF: wrote {Path(args.out_dir).resolve()}")
    return 0


def rank_sksf_portfolio_command(args: argparse.Namespace) -> int:
    portfolio = yaml.safe_load(Path(args.portfolio).read_text())
    measurements = json.loads(Path(args.measurements).read_text())
    report = rank_portfolio(portfolio, measurements, bootstrap_rounds=args.bootstrap_rounds, seed=args.seed)
    write_json(Path(args.out), report)
    print(f"vLadder SKSF: portfolio={report['classification']} improvement={report['portfolio_improvement_percent']:.3f}%")
    print(f"vLadder SKSF: wrote {Path(args.out).resolve()}")
    return 0


def run_sksf_kernel_lab_command(args: argparse.Namespace) -> int:
    report = run_quantized_kernel_lab(Path(args.out_dir), cpu=args.cpu, processes=args.processes, repetitions=args.repetitions, seed=args.seed)
    winner = report["winner"]
    print(f"vLadder SKSF: kernel-lab winner={winner['candidate']} speedup={winner['speedup_percent']:.3f}%")
    print(f"vLadder SKSF: production-claim={report['production_claim']}")
    print(f"vLadder SKSF: wrote {Path(args.out_dir).resolve()}")
    return 0


def capture_q4k_v7_command(args: argparse.Namespace) -> int:
    report = capture_active_q4k_path(
        Path(args.llama_root), Path(args.model), Path(args.out_dir), cpu_list=args.cpu_list,
        threads=args.threads, prompt_tokens=args.prompt_tokens, expected_kernel=args.expected_kernel,
    )
    decode = [item for item in report["records"] if item["tokens"] == 1]
    print(f"vLadder Q4_K V7: active-path={report['status']} decode-records={len(decode)}")
    print(f"vLadder Q4_K V7: kernel={report['runtime_contract']['expected_decode_kernel']} repack={report['runtime_contract']['runtime_repack_type']}")
    print(f"vLadder Q4_K V7: wrote {Path(args.out_dir).resolve()}")
    return 0


def reconstruct_q4k_v7_command(args: argparse.Namespace) -> int:
    report = reconstruct_q4k_v7(Path(args.manifest), Path(args.out_dir), random_cases=args.random_cases, seed=args.seed)
    print(f"vLadder Q4_K V7: reconstruction={report['status']} cases={report['case_count']} graph={report['graph_hash'][:16]}")
    print(f"vLadder Q4_K V7: native-E1={report['gates']['native_kernel_E1']}")
    print(f"vLadder Q4_K V7: wrote {Path(args.out_dir).resolve()}")
    return 0


def parity_q4k_v7_command(args: argparse.Namespace) -> int:
    report = run_q4k_parity(
        Path(args.manifest), Path(args.out_dir), processes=args.processes,
        repetitions=args.repetitions, inner=args.inner, seed=args.seed,
    )
    benchmark = report["benchmark"]
    print(f"vLadder Q4_K V7: parity={report['classification']} E1={report['verification']['status']}")
    print(f"vLadder Q4_K V7: regenerated-regression={benchmark['regenerated_regression_percent']:.3f}% speedup95={benchmark['regenerated_speedup_95']}")
    print(f"vLadder Q4_K V7: wrote {Path(args.out_dir).resolve()}")
    return 0


def synthesize_q4k_v7_command(args: argparse.Namespace) -> int:
    report = synthesize_q4k_siblings(
        Path(args.manifest), Path(args.parity_report), Path(args.out_dir), processes=args.processes,
        repetitions=args.repetitions, inner=args.inner, seed=args.seed,
    )
    winner = report["winner"]
    print(f"vLadder Q4_K V7: transfer={report['classification']} candidates={report['physically_benchmarked_candidate_count']}")
    print(f"vLadder Q4_K V7: winner={winner['candidate']} speedup={winner['speedup_percent']:.3f}% interval={winner['speedup_95']}")
    print(f"vLadder Q4_K V7: wrote {Path(args.out_dir).resolve()}")
    return 0


def verify_q4k_model_v7_command(args: argparse.Namespace) -> int:
    report = verify_regenerated_q4k_model(
        Path(args.manifest), Path(args.parity_report), Path(args.out_dir),
        prompt=args.prompt, generated_tokens=args.generated_tokens, seed=args.seed,
    )
    print(f"vLadder Q4_K V7: model verification={report['status']} bindings={report['dispatch']['binding_count']}")
    print(f"vLadder Q4_K V7: output_sha256={report['native_output_sha256']}")
    print(f"vLadder Q4_K V7: wrote {Path(args.out_dir).resolve()}")
    return 0


def decompose_q4k_v8_command(args: argparse.Namespace) -> int:
    report = run_q4k_v8(
        Path(args.manifest), Path(args.reconstruction_report), Path(args.parity_report), Path(args.out_dir),
        cpu=args.cpu, baseline_processes=args.baseline_processes, baseline_repetitions=args.baseline_repetitions,
        ablation_processes=args.ablation_processes, ablation_repetitions=args.ablation_repetitions, seed=args.seed,
    )
    print(f"vLadder Q4_K V8: status={report['status']} graph={report['physical_graph_hash'][:16]}")
    print(f"vLadder Q4_K V8: bound={report['bounds']['classification']} conservative-ceiling={report['ceilings']['total_conservative_percent']:.3f}% optimistic-ceiling={report['ceilings']['total_optimistic_percent']:.3f}%")
    print(f"vLadder Q4_K V8: admitted={report['grammar_decisions']['admitted']}")
    print(f"vLadder Q4_K V8: wrote {Path(args.out_dir).resolve()}")
    return 0


def synthesize_weight_reuse_v9_command(args: argparse.Namespace) -> int:
    report = run_weight_traversal_v9(
        Path(args.manifest), Path(args.v8_report), Path(args.out_dir),
        llama_root=Path(args.llama_root), cpu_list=args.cpu_list, threads=args.threads,
        processes=args.processes, seed=args.seed,
    )
    ranking = report["ranking"]
    print(f"vLadder Q4_K V9: status={report['status']} accepted={report['acceptance']['accepted']}")
    print(f"vLadder Q4_K V9: portfolio={ranking['portfolio_improvement_percent']:.3f}% interval={ranking['portfolio_improvement_95']}")
    print(f"vLadder Q4_K V9: conclusion={report['conclusion']['classification']}")
    print(f"vLadder Q4_K V9: wrote {Path(args.out_dir).resolve()}")
    return 0


def benchmark_llama_command(args: argparse.Namespace) -> int:
    report = benchmark_llama_integration(Path(args.llama_root), Path(args.out_dir), args.cpu, args.processes, args.samples, args.dimension)
    print(f"vLadder token: llama.cpp {report['llama_commit'][:12]}")
    print(f"vLadder token: verified p50 speedup={report['p50_speedup_pct']:.3f}%")
    print(f"vLadder token: wrote {Path(args.out_dir).resolve()}")
    return 0


def benchmark_llama_model_command(args: argparse.Namespace) -> int:
    report = benchmark_llama_model(
        Path(args.llama_root), Path(args.model), Path(args.out_dir), args.cpu_list, args.threads,
        args.processes, args.repetitions, args.prompt_tokens, args.generation_tokens,
    )
    baseline = report["measurements"]["pinned_llama_baseline"]["decode"]["tokens_per_second"]["p50"]
    optimized = report["measurements"]["vladder_add_rms_mul_fused"]["decode"]["tokens_per_second"]["p50"]
    delta = report["deltas"]["decode"]
    print(f"vLadder token: Qwen3 decode baseline={baseline:.3f} optimized={optimized:.3f} tok/s")
    print(f"vLadder token: speedup={delta['p50_speedup_pct']:.3f}% ({delta['classification']})")
    print(f"vLadder token: wrote {Path(args.out_dir).resolve()}")
    return 0


def extract_llama_graph_v4_command(args: argparse.Namespace) -> int:
    report = extract_llama_decode_graph(Path(args.llama_root), Path(args.model), Path(args.out_dir), args.cpu_list, args.threads)
    print(f"vLadder token-v4: graph={report['graph_hash'][:16]} nodes={report['annotations']['compute_node_count']}")
    print(f"vLadder token-v4: layers={report['annotations']['layer_count']} v3-regions={report['annotations']['v3_add_rms_mul_regions']}")
    print(f"vLadder token-v4: wrote {Path(args.out_dir).resolve()}")
    return 0


def profile_llama_graph_v4_command(args: argparse.Namespace) -> int:
    report = profile_llama_decode_graph(Path(args.llama_root), Path(args.model), Path(args.graph), Path(args.out_dir), args.cpu_list, args.threads, args.tokens, args.context_tokens)
    target = report["stage1_to_stage3_addressable"]
    print(f"vLadder token-v4: profiled-graphs={report['graph_samples']} median-exclusive={report['exclusive_graph_us']['median']:.1f} us")
    print(f"vLadder token-v4: stage1-3 coverage={target['median_decode_fraction'] * 100.0:.2f}%")
    print(f"vLadder token-v4: wrote {Path(args.out_dir).resolve()}")
    return 0


def analyze_function(args: argparse.Namespace) -> int:
    source_path = Path(args.source).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source = source_path.read_text()
    extracted = extract_function(source, args.function)
    tc = discover_toolchain()
    ir_info = emit_target_ir(tc, source_path, out_dir / "analysis", args.function)
    ir_slice = analyze_ir(ir_info, args.function)
    graph = build_flow_graph(extracted, (ir_info.get("stats") if isinstance(ir_info, dict) else {}) or {}, ir_slice)
    write_flow_artifacts(out_dir, graph, ir_info, ir_slice)
    emit_semantic_smt(graph, out_dir / "analysis" / "semantic_model.smt2")
    print(f"vLadder analyze: family={graph.family} canonical={graph.canonical}")
    print(f"vLadder analyze: wrote {out_dir / 'analysis'}")
    return 0


def run_corpus(args: argparse.Namespace) -> int:
    root = Path(args.directory).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    for source in sorted(root.glob("*.c")):
        kernel_out = out_dir / source.stem
        opt_args = argparse.Namespace(
            source=str(source),
            function=args.function,
            out_dir=str(kernel_out),
            n=args.n,
            reps=args.reps,
            inner=args.inner,
            cpu=args.cpu,
            assume_no_alias=args.assume_no_alias,
            flush_cache=False,
            perf=args.perf,
            allow_unproved=args.allow_unproved,
            alive2=args.alive2,
            verification_policy=args.verification_policy,
            min_speedup_pct=args.min_speedup_pct,
            graph_inner_loop=args.graph_inner_loop,
            search_nodes=args.search_nodes,
            search_ms=args.search_ms,
            llm_lift=args.llm_lift,
            llm_rounds=args.llm_rounds,
        )
        print(f"vLadder corpus: {source.name}")
        rc = optimize_c_kernel(opt_args)
        report_path = kernel_out / "perf.json"
        if rc == 0 and report_path.exists():
            data = json.loads(report_path.read_text())
            winner = data.get("winner") or {}
            shape = data.get("flow_shape") or {}
            summaries.append(
                {
                    "kernel": source.name,
                    "family": shape.get("family"),
                    "canonical": shape.get("canonical"),
                    "inner_loop": data.get("inner_loop"),
                    "winner": winner.get("candidate"),
                    "baseline_ns_per_item": data.get("baseline_ns_per_item"),
                    "winner_ns_per_item": winner.get("ns_per_item"),
                    "speedup_vs_baseline_pct": winner.get("speedup_vs_baseline_pct"),
                    "proof_status": ((winner.get("proof") or {}).get("status") if isinstance(winner, dict) else None),
                    "verification_tier": winner.get("verification_tier"),
                    "optimality": winner.get("optimality"),
                    "cycles": ((winner.get("perf") or {}).get("cycles") if isinstance(winner.get("perf"), dict) else None),
                    "instructions": ((winner.get("perf") or {}).get("instructions") if isinstance(winner.get("perf"), dict) else None),
                    "branch_misses": ((winner.get("perf") or {}).get("branch-misses") if isinstance(winner.get("perf"), dict) else None),
                    "cache_misses": ((winner.get("perf") or {}).get("cache-misses") if isinstance(winner.get("perf"), dict) else None),
                    "passing_candidates": len([r for r in data.get("candidates", []) if r.get("status") == "PASS"]),
                }
            )
        else:
            summaries.append({"kernel": source.name, "status": "FAILED", "returncode": rc})
    write_json(out_dir / "corpus.json", summaries)
    write_csv(
        out_dir / "corpus.csv",
        summaries,
        ["kernel", "family", "canonical", "inner_loop", "winner", "baseline_ns_per_item", "winner_ns_per_item", "speedup_vs_baseline_pct", "proof_status", "verification_tier", "optimality", "cycles", "instructions", "branch_misses", "cache_misses", "passing_candidates"],
    )
    improved = [r for r in summaries if float(r.get("speedup_vs_baseline_pct") or 0.0) > 0.0]
    over_10 = [r for r in summaries if float(r.get("speedup_vs_baseline_pct") or 0.0) >= 10.0]
    print(f"vLadder corpus: {len(summaries)} kernels, {len(improved)} improved, {len(over_10)} >=10%")
    print(f"vLadder corpus: wrote {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"vladder: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
