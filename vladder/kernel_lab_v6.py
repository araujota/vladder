from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import subprocess
from typing import Any

from .hardware_manifest import capture_manifest, stability_warnings
from .statistics_v3 import empirical_quantile
from .toolchain import discover_toolchain


KERNEL_LAB_C = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { INPUTS = 4096, ROWS = 128, PROJECTIONS = 2, PACKED = INPUTS / 2 };
static uint8_t *weights;
static int8_t *activation;
static int64_t reference_out[PROJECTIONS * ROWS];
static int64_t candidate_out[PROJECTIONS * ROWS];
static int8_t decode_lut[256][2];

static uint64_t rng_state = UINT64_C(0x9e3779b97f4a7c15);
static uint32_t next_u32(void) {
    uint64_t x = rng_state;
    x ^= x >> 12; x ^= x << 25; x ^= x >> 27; rng_state = x;
    return (uint32_t)((x * UINT64_C(2685821657736338717)) >> 32);
}
static uint64_t now_ns(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}
static void pin_cpu(int cpu) {
    cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set);
    if (sched_setaffinity(0, sizeof(set), &set) != 0) fprintf(stderr, "affinity: %s\n", strerror(errno));
}
static void init_data(void) {
    weights = aligned_alloc(64, (size_t)PROJECTIONS * ROWS * PACKED);
    activation = aligned_alloc(64, INPUTS);
    for (int q = 0; q < 256; ++q) {
        decode_lut[q][0] = (int8_t)((q & 15) - 8);
        decode_lut[q][1] = (int8_t)(((q >> 4) & 15) - 8);
    }
}
static void randomize_data(void) {
    for (size_t i = 0; i < (size_t)PROJECTIONS * ROWS * PACKED; ++i) weights[i] = (uint8_t)next_u32();
    for (int i = 0; i < INPUTS; ++i) activation[i] = (int8_t)((int)(next_u32() % 255) - 127);
}
static void adversarial_data(int high) {
    memset(weights, high ? 0xff : 0x00, (size_t)PROJECTIONS * ROWS * PACKED);
    for (int i = 0; i < INPUTS; ++i) activation[i] = (int8_t)((i & 1) ? 127 : -127);
}
__attribute__((noinline)) static void baseline(int64_t *out) {
    for (int p = 0; p < PROJECTIONS; ++p) for (int r = 0; r < ROWS; ++r) {
        const uint8_t *w = weights + ((size_t)p * ROWS + r) * PACKED;
        int64_t sum = 0;
        for (int j = 0; j < PACKED; ++j) {
            uint8_t q = w[j];
            sum += (int64_t)((q & 15) - 8) * activation[2*j];
            sum += (int64_t)(((q >> 4) & 15) - 8) * activation[2*j + 1];
        }
        out[p * ROWS + r] = sum;
    }
}
__attribute__((noinline)) static void lut_decode(int64_t *out) {
    for (int p = 0; p < PROJECTIONS; ++p) for (int r = 0; r < ROWS; ++r) {
        const uint8_t *w = weights + ((size_t)p * ROWS + r) * PACKED;
        int64_t sum = 0;
        for (int j = 0; j < PACKED; ++j) {
            const int8_t *q = decode_lut[w[j]];
            sum += (int64_t)q[0] * activation[2*j];
            sum += (int64_t)q[1] * activation[2*j + 1];
        }
        out[p * ROWS + r] = sum;
    }
}
__attribute__((noinline)) static void four_banks(int64_t *out) {
    for (int p = 0; p < PROJECTIONS; ++p) for (int r = 0; r < ROWS; ++r) {
        const uint8_t *w = weights + ((size_t)p * ROWS + r) * PACKED;
        int64_t s0 = 0, s1 = 0, s2 = 0, s3 = 0;
        for (int j = 0; j < PACKED; j += 4) {
            uint8_t q0 = w[j], q1 = w[j+1], q2 = w[j+2], q3 = w[j+3];
            s0 += (int64_t)((q0 & 15)-8)*activation[2*j] + (int64_t)(((q0>>4)&15)-8)*activation[2*j+1];
            s1 += (int64_t)((q1 & 15)-8)*activation[2*j+2] + (int64_t)(((q1>>4)&15)-8)*activation[2*j+3];
            s2 += (int64_t)((q2 & 15)-8)*activation[2*j+4] + (int64_t)(((q2>>4)&15)-8)*activation[2*j+5];
            s3 += (int64_t)((q3 & 15)-8)*activation[2*j+6] + (int64_t)(((q3>>4)&15)-8)*activation[2*j+7];
        }
        out[p * ROWS + r] = (s0 + s1) + (s2 + s3);
    }
}
__attribute__((noinline)) static void sibling_traversal(int64_t *out) {
    for (int r = 0; r < ROWS; ++r) {
        const uint8_t *w0 = weights + (size_t)r * PACKED;
        const uint8_t *w1 = weights + ((size_t)ROWS + r) * PACKED;
        int64_t s0 = 0, s1 = 0;
        for (int j = 0; j < PACKED; ++j) {
            uint8_t q0 = w0[j], q1 = w1[j];
            int a0 = activation[2*j], a1 = activation[2*j+1];
            s0 += (int64_t)((q0 & 15)-8)*a0 + (int64_t)(((q0>>4)&15)-8)*a1;
            s1 += (int64_t)((q1 & 15)-8)*a0 + (int64_t)(((q1>>4)&15)-8)*a1;
        }
        out[r] = s0; out[ROWS + r] = s1;
    }
}
typedef void (*kernel_fn)(int64_t *);
static kernel_fn select_kernel(const char *name) {
    if (!strcmp(name, "baseline")) return baseline;
    if (!strcmp(name, "lut_decode")) return lut_decode;
    if (!strcmp(name, "four_banks")) return four_banks;
    if (!strcmp(name, "sibling_traversal")) return sibling_traversal;
    return NULL;
}
static int compare_u64(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}
int main(int argc, char **argv) {
    const char *name = argc > 1 ? argv[1] : "baseline";
    int cpu = argc > 2 ? atoi(argv[2]) : 0;
    int reps = argc > 3 ? atoi(argv[3]) : 15;
    kernel_fn fn = select_kernel(name);
    if (!fn) return 2;
    pin_cpu(cpu); init_data();
    for (int trial = 0; trial < 10; ++trial) {
        if (trial < 8) randomize_data(); else adversarial_data(trial == 9);
        baseline(reference_out); fn(candidate_out);
        if (memcmp(reference_out, candidate_out, sizeof(reference_out)) != 0) {
            printf("{\"candidate\":\"%s\",\"verify\":\"FAIL\",\"trial\":%d}\n", name, trial); return 3;
        }
    }
    rng_state = UINT64_C(0x9e3779b97f4a7c15); randomize_data();
    for (int i = 0; i < 4; ++i) fn(candidate_out);
    uint64_t *samples = calloc((size_t)reps, sizeof(uint64_t));
    volatile int64_t guard = 0;
    for (int i = 0; i < reps; ++i) {
        uint64_t start = now_ns(); fn(candidate_out); uint64_t end = now_ns();
        samples[i] = end - start; guard ^= candidate_out[i % (PROJECTIONS * ROWS)];
    }
    qsort(samples, (size_t)reps, sizeof(uint64_t), compare_u64);
    uint64_t median = samples[reps/2];
    printf("{\"candidate\":\"%s\",\"verify\":\"PASS\",\"verification_cases\":10,\"median_ns\":%" PRIu64 ",\"guard\":%" PRId64 "}\n", name, median, guard);
    free(samples); free(weights); free(activation); return 0;
}
'''


def run_quantized_kernel_lab(out_dir: Path, *, cpu: int = 0, processes: int = 10, repetitions: int = 15, seed: int = 0) -> dict[str, Any]:
    if processes < 2:
        raise ValueError("kernel lab requires at least two independent processes")
    out_dir.mkdir(parents=True, exist_ok=True)
    source = out_dir / "q4-affine-kernel-lab.c"
    binary = out_dir / "q4-affine-kernel-lab"
    source.write_text(KERNEL_LAB_C)
    tc = discover_toolchain()
    build = subprocess.run([tc.compiler, "-std=c17", "-O3", "-march=native", str(source), "-o", str(binary)], text=True, capture_output=True, timeout=120)
    if build.returncode != 0:
        raise RuntimeError(build.stderr)
    candidates = ["baseline", "lut_decode", "four_banks", "sibling_traversal"]
    order = [(candidate, process) for process in range(processes) for candidate in candidates]
    random.Random(seed).shuffle(order)
    samples = {candidate: [] for candidate in candidates}
    verification = {candidate: "PASS" for candidate in candidates}
    audit = []
    for candidate, process in order:
        run = subprocess.run([str(binary), candidate, str(cpu), str(repetitions)], text=True, capture_output=True, timeout=120)
        if run.returncode != 0:
            raise RuntimeError(f"kernel lab {candidate} failed: {run.stdout}\n{run.stderr}")
        result = json.loads(run.stdout.splitlines()[-1])
        verification[candidate] = result["verify"]
        samples[candidate].append(float(result["median_ns"]))
        audit.append({"ordinal": len(audit), "process": process, "candidate": candidate, "median_ns": result["median_ns"]})
    rankings = []
    for candidate in candidates:
        interval = _improvement_interval(samples["baseline"], samples[candidate], seed=f"{seed}:{candidate}")
        base = sum(samples["baseline"]) / len(samples["baseline"])
        measured = sum(samples[candidate]) / len(samples[candidate])
        rankings.append({
            "candidate": candidate, "verify": verification[candidate], "mean_process_median_ns": measured,
            "speedup_percent": (base / measured - 1.0) * 100.0,
            "speedup_95": interval,
            "classification": "measured_win" if candidate != "baseline" and interval[0] > 0.0 else ("baseline" if candidate == "baseline" else "not_demonstrated"),
        })
    winner = min((row for row in rankings if row["verify"] == "PASS"), key=lambda row: row["mean_process_median_ns"])
    manifest = capture_manifest("local-sksf-kernel-lab", cpu, tc)
    report = {
        "schema_version": "vladder-kernel-lab-v6.0",
        "scope": "synthetic exact signed-nibble x int8 projection; not GGUF Q4_K and not production inference",
        "semantic_contract": "exact int64 dot products; bounded inputs preclude signed overflow",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "compiler": tc.compiler,
        "flags": ["-std=c17", "-O3", "-march=native"],
        "candidate_order_policy": "seeded randomized interleaving across independent processes",
        "processes": processes,
        "repetitions_per_process": repetitions,
        "hardware_manifest": manifest.to_dict(),
        "stability_warnings": stability_warnings(manifest),
        "rankings": rankings,
        "winner": winner,
        "production_claim": "NONE",
        "perf_counters": _perf_probe(binary, cpu),
    }
    (out_dir / "kernel-lab-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    (out_dir / "kernel-lab-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _improvement_interval(baseline: list[float], candidate: list[float], *, seed: str, rounds: int = 4000) -> list[float]:
    rng = random.Random(seed)
    values = []
    for _ in range(rounds):
        base = sum(baseline[rng.randrange(len(baseline))] for _ in baseline) / len(baseline)
        cand = sum(candidate[rng.randrange(len(candidate))] for _ in candidate) / len(candidate)
        values.append((base / cand - 1.0) * 100.0)
    return [empirical_quantile(values, 0.025), empirical_quantile(values, 0.975)]


def _perf_probe(binary: Path, cpu: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["perf", "stat", "-x,", "-e", "cycles,instructions,cache-misses,branches,branch-misses", "--", str(binary), "baseline", str(cpu), "3"],
            text=True, capture_output=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"status": "UNAVAILABLE", "reason": str(exc)}
    if result.returncode != 0:
        return {"status": "UNAVAILABLE", "reason": result.stderr.strip()[:500]}
    counters: dict[str, float] = {}
    for line in result.stderr.splitlines():
        fields = line.split(",")
        if len(fields) >= 3:
            try:
                counters[fields[2]] = float(fields[0])
            except ValueError:
                continue
    return {"status": "PASS", "baseline": counters}
