from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import struct
import time
from typing import Any

from .q4k_parity import _fixture
from .q4k_semantics import Q4KX8Block, inverse_repack_q4k_x8, q4k_quant_values
from .report import write_json
from .statistics_v3 import empirical_quantile
from .toolchain import run


V8_DIAGNOSTIC_SOURCE = r'''
#include "repack.h"
#include <immintrin.h>
#include <x86intrin.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

extern "C" void vladder_regenerated_gemv_q4_K_8x8_q8_K(
    int n, float * s, size_t bs, const void * vx, const void * vy, int nr, int nc);

static std::vector<uint8_t> read_file(const char * path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate); if (!input) std::exit(10);
    const auto size = input.tellg(); input.seekg(0); std::vector<uint8_t> data((size_t)size);
    input.read((char *)data.data(), size); return data;
}
static uint64_t fold256(__m256i value) {
    alignas(32) uint64_t words[4]; _mm256_store_si256((__m256i *)words, value);
    return words[0] ^ words[1] ^ words[2] ^ words[3];
}
static uint64_t weight_floor(const uint8_t * weights, size_t bytes) {
    __m256i a = _mm256_setzero_si256(), b = _mm256_set1_epi64x(0x5a5a5a5a5a5a5a5aULL);
    for (size_t offset = 0; offset < bytes; offset += 64) {
        a = _mm256_xor_si256(a, _mm256_loadu_si256((const __m256i *)(weights + offset)));
        b = _mm256_add_epi64(b, _mm256_loadu_si256((const __m256i *)(weights + offset + 32)));
    }
    return fold256(_mm256_xor_si256(a, b));
}
static uint64_t metadata_only(const block_q4_Kx8 * weights, int64_t blocks) {
    __m256i acc = _mm256_setzero_si256();
    const __m256i low = _mm256_set1_epi8(0x3f);
    for (int64_t index = 0; index < blocks; ++index) {
        const uint8_t * data = (const uint8_t *)&weights[index];
        for (int offset = 0; offset < 128; offset += 32) {
            __m256i value = _mm256_loadu_si256((const __m256i *)(data + offset));
            acc = _mm256_add_epi8(acc, _mm256_and_si256(value, low));
            acc = _mm256_xor_si256(acc, _mm256_srli_epi16(value, 4));
        }
    }
    return fold256(acc);
}
static uint64_t unpack_only(const block_q4_Kx8 * weights, int64_t blocks) {
    __m256i low_acc = _mm256_setzero_si256(), high_acc = _mm256_setzero_si256();
    const __m256i mask = _mm256_set1_epi8(0x0f);
    for (int64_t index = 0; index < blocks; ++index) {
        for (int offset = 0; offset < 1024; offset += 32) {
            __m256i raw = _mm256_loadu_si256((const __m256i *)(weights[index].qs + offset));
            low_acc = _mm256_add_epi8(low_acc, _mm256_and_si256(raw, mask));
            high_acc = _mm256_xor_si256(high_acc, _mm256_and_si256(_mm256_srli_epi16(raw, 4), mask));
        }
    }
    return fold256(_mm256_xor_si256(low_acc, high_acc));
}
static int32_t horizontal_i32(__m256i value) {
    __m128i sum = _mm_add_epi32(_mm256_castsi256_si128(value), _mm256_extracti128_si256(value, 1));
    sum = _mm_hadd_epi32(sum, sum); sum = _mm_hadd_epi32(sum, sum); return _mm_cvtsi128_si32(sum);
}
static uint64_t dot_preexpanded(const uint8_t * expanded, const block_q8_K * activation, int n, int nc, int nr, int mode) {
    const int nb = n/256; const int groups = nc/8; uint64_t guard = 0;
    for (int token = 0; token < nr; ++token) for (int group = 0; group < groups; ++group) {
        __m256i acc[8]; for (int row = 0; row < 8; ++row) acc[row] = _mm256_setzero_si256();
        for (int block = 0; block < nb; ++block) for (int chunk = 0; chunk < 8; ++chunk) {
            __m256i lhs = _mm256_loadu_si256((const __m256i *)(activation[token*nb + block].qs + chunk*32));
            for (int row = 0; row < 8; ++row) {
                const size_t offset = (((size_t)group*nb + block)*8 + row)*256 + chunk*32;
                __m256i rhs = _mm256_loadu_si256((const __m256i *)(expanded + offset));
                __m256i partial = _mm256_maddubs_epi16(rhs, lhs);
                acc[row] = _mm256_add_epi32(acc[row], _mm256_madd_epi16(partial, _mm256_set1_epi16(1)));
                if (mode == 2) {
                    alignas(32) volatile int32_t spill[8]; _mm256_store_si256((__m256i *)(void *)spill, acc[row]);
                    acc[row] = _mm256_load_si256((const __m256i *)(const void *)spill);
                }
            }
        }
        if (mode == 1) for (int row = 0; row < 8; ++row) {
            // Calibration dependency: serialize final consumption without changing dot count.
            guard = (guard * 0x100000001b3ULL) ^ (uint32_t)horizontal_i32(acc[row]);
        } else for (int row = 0; row < 8; ++row) guard ^= (uint32_t)horizontal_i32(acc[row]);
    }
    return guard;
}
static uint64_t correction_only(int n, int nc, int nr) {
    const int nb = n/256; const int groups = nc/8; uint64_t guard = 0;
    const __m256 row_scale = _mm256_set1_ps(0.03125f), col_scale = _mm256_set1_ps(0.0625f);
    for (int token = 0; token < nr; ++token) for (int group = 0; group < groups; ++group) {
        __m256 acc = _mm256_setzero_ps(), minimum = _mm256_setzero_ps();
        for (int block = 0; block < nb; ++block) {
            __m256i dot = _mm256_set_epi32(block+7,block+6,block+5,block+4,block+3,block+2,block+1,block);
            __m256i correction = _mm256_add_epi32(dot, _mm256_set1_epi32(17));
            acc = _mm256_fmadd_ps(_mm256_cvtepi32_ps(dot), _mm256_mul_ps(row_scale, col_scale), acc);
            minimum = _mm256_fmadd_ps(_mm256_cvtepi32_ps(correction), _mm256_mul_ps(row_scale, col_scale), minimum);
        }
        __m256 out = _mm256_sub_ps(acc, minimum); alignas(32) float values[8]; _mm256_store_ps(values, out);
        for (float value : values) { uint32_t bits; memcpy(&bits, &value, 4); guard ^= bits; }
    }
    return guard;
}
static void evict_cache(std::vector<uint8_t> & eviction) {
    volatile uint64_t sink = 0; for (size_t index = 0; index < eviction.size(); index += 64) sink += eviction[index];
    if (sink == UINT64_MAX) std::abort();
}
int main(int argc, char ** argv) {
    if (argc < 12) return 2;
    const std::string candidate = argv[1], cache_mode = argv[10];
    const auto weights = read_file(argv[2]), activation = read_file(argv[3]), expanded = read_file(argv[4]);
    const int n=atoi(argv[5]), nc=atoi(argv[6]), nr=atoi(argv[7]), reps=atoi(argv[8]), inner=atoi(argv[9]);
    const size_t eviction_bytes = strtoull(argv[11], nullptr, 10);
    std::vector<float> output((size_t)nc*std::max(1,nr) + 64); std::vector<uint8_t> eviction(eviction_bytes, 1);
    auto execute = [&]() -> uint64_t {
        if (candidate == "native") {
            vladder_regenerated_gemv_q4_K_8x8_q8_K(n, output.data(), nc, weights.data(), activation.data(), nr, nc);
            uint64_t guard=0; for (int i=0;i<8;i++){uint32_t bits;memcpy(&bits,&output[i],4);guard^=bits;} return guard;
        }
        const int64_t blocks = (int64_t)(n/256)*(nc/8);
        if (candidate == "weight_floor") return weight_floor(weights.data(), weights.size());
        if (candidate == "metadata_only") return metadata_only((const block_q4_Kx8 *)weights.data(), blocks);
        if (candidate == "unpack_only") return unpack_only((const block_q4_Kx8 *)weights.data(), blocks);
        if (candidate == "dot_preexpanded") return dot_preexpanded(expanded.data(), (const block_q8_K *)activation.data(), n,nc,nr,0);
        if (candidate == "dot_serial_consume") return dot_preexpanded(expanded.data(), (const block_q8_K *)activation.data(), n,nc,nr,1);
        if (candidate == "dot_forced_spill") return dot_preexpanded(expanded.data(), (const block_q8_K *)activation.data(), n,nc,nr,2);
        if (candidate == "correction_only") return correction_only(n,nc,nr);
        std::exit(4);
    };
    uint64_t guard=0; for (int warm=0;warm<3;++warm) guard = guard*UINT64_C(1099511628211) ^ execute();
    std::vector<uint64_t> samples((size_t)reps), tsc_samples((size_t)reps);
    for (int rep=0; rep<reps; ++rep) {
        if (cache_mode == "streaming") evict_cache(eviction);
        unsigned aux=0; const uint64_t t0=__rdtscp(&aux); const auto start=std::chrono::steady_clock::now();
        for (int iteration=0; iteration<inner; ++iteration) guard = guard*UINT64_C(1099511628211) ^ execute();
        const auto end=std::chrono::steady_clock::now(); const uint64_t t1=__rdtscp(&aux);
        samples[rep]=(uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(end-start).count()/inner;
        tsc_samples[rep]=(t1-t0)/inner;
    }
    std::sort(samples.begin(),samples.end()); std::sort(tsc_samples.begin(),tsc_samples.end());
    std::printf("{\"candidate\":\"%s\",\"cache_mode\":\"%s\",\"median_ns\":%llu,\"median_tsc\":%llu,\"guard\":\"%016llx\"}\n",
        candidate.c_str(),cache_mode.c_str(),(unsigned long long)samples[samples.size()/2],
        (unsigned long long)tsc_samples[tsc_samples.size()/2],(unsigned long long)guard);
}
'''


DIAGNOSTIC_DESCRIPTIONS = {
    "weight_floor": {"stages": ["A"], "distortion": "all Q4_Kx8 bytes are traversed with XOR/add sinks; arithmetic and native load issue order change"},
    "metadata_only": {"stages": ["A", "B"], "distortion": "loads the 128-byte metadata prefix and representative bit extraction only"},
    "unpack_only": {"stages": ["A", "C"], "distortion": "loads every packed value byte and performs mask/shift sinks without native permutations"},
    "dot_preexpanded": {"stages": ["D", "E"], "distortion": "decoded values match source nibbles but representation expands to eight bits and changes memory traffic"},
    "dot_serial_consume": {"stages": ["D", "E", "G"], "distortion": "same dot count with serialized result consumption; diagnostic dependency calibration"},
    "dot_forced_spill": {"stages": ["D", "E", "G"], "distortion": "forces volatile accumulator stores/reloads; calibration only"},
    "correction_only": {"stages": ["F", "G"], "distortion": "uses deterministic synthetic integer partials and scales; excludes all loads/decode/dot"},
}


def build_v8_diagnostic_harness(
    active_manifest: dict[str, Any], parity_report_path: Path, out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    parity = json.loads(parity_report_path.read_text())
    regenerated = parity_report_path.resolve().parent / "regenerated-q4k-gemv.cpp"
    if hashlib.sha256(regenerated.read_bytes()).hexdigest() != parity["regenerated_source_sha256"]:
        raise ValueError("V8 regenerated source hash mismatch")
    llama_root = Path(active_manifest["source_provenance"]["kernel"]["path"]).parents[5]
    source = out_dir / "q4k-v8-diagnostics.cpp"
    binary = out_dir / "q4k-v8-diagnostics"
    source.write_text(V8_DIAGNOSTIC_SOURCE)
    command = ["clang++-20", "-std=gnu++17", "-O3", "-DNDEBUG", "-march=native"]
    command.extend(f"-I{path}" for path in (llama_root/"ggml/include", llama_root/"ggml/src", llama_root/"ggml/src/ggml-cpu"))
    command.extend([str(regenerated), str(source), "-o", str(binary)])
    compiled = run(command, timeout=180)
    if compiled.returncode:
        raise RuntimeError((compiled.stdout + compiled.stderr)[-6000:])
    assembly = out_dir / "q4k-v8-diagnostics.s"
    asm_command = command[:]
    asm_command[asm_command.index(str(regenerated))] = str(source)
    asm_command.remove(str(source))
    asm_command[-2:] = ["-S", "-o", str(assembly)]
    assembled = run(asm_command, timeout=180)
    if assembled.returncode:
        raise RuntimeError((assembled.stdout + assembled.stderr)[-3000:])
    return {
        "source": str(source), "source_sha256": _sha256(source), "binary": str(binary),
        "binary_sha256": _sha256(binary), "assembly": str(assembly), "compile_command": command,
        "diagnostic_only": True, "eligible_for_ranking": False,
    }


def make_v8_fixtures(out_dir: Path, n: int, nc: int, nr: int, seed: int) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    weights, activation_one = _fixture(out_dir, f"q4k-{n}-{nc}", n, nc, "random", seed)
    raw_activation = activation_one.read_bytes()
    activation = out_dir / f"q8k-{n}-rows{nr}.bin"
    activation.write_bytes(raw_activation * nr)
    expanded = out_dir / f"expanded-{n}-{nc}.bin"
    if not expanded.exists():
        source = weights.read_bytes(); output = bytearray()
        for offset in range(0, len(source), 1152):
            block = source[offset:offset+1152]
            repacked = Q4KX8Block(
                struct.unpack_from("<8H", block), struct.unpack_from("<8H", block, 16), block[32:128], block[128:],
            )
            for native in inverse_repack_q4k_x8(repacked, 8):
                output.extend(q4k_quant_values(native))
        expanded.write_bytes(output)
    return {"weights": weights, "activation": activation, "expanded": expanded}


def execute_diagnostic_process(
    harness: dict[str, Any], fixtures: dict[str, Path], *, candidate: str, n: int, nc: int, nr: int,
    repetitions: int, inner: int, cache_mode: str, eviction_bytes: int, cpu: int,
) -> dict[str, Any]:
    frequency_before = _frequency_khz(cpu); temperature_before = _temperature_millic()
    command = [
        "taskset", "-c", str(cpu), harness["binary"], candidate, str(fixtures["weights"]),
        str(fixtures["activation"]), str(fixtures["expanded"]), str(n), str(nc), str(nr),
        str(repetitions), str(inner), cache_mode, str(eviction_bytes),
    ]
    result = run(command, timeout=300)
    frequency_after = _frequency_khz(cpu); temperature_after = _temperature_millic()
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr)[-4000:])
    payload = json.loads(result.stdout.splitlines()[-1])
    payload.update({
        "command": command, "frequency_khz_before": frequency_before, "frequency_khz_after": frequency_after,
        "frequency_khz_mean": (frequency_before + frequency_after)/2.0 if frequency_before and frequency_after else None,
        "temperature_millic_before": temperature_before, "temperature_millic_after": temperature_after,
        "temperature_millic_mean": (temperature_before + temperature_after)/2.0 if temperature_before and temperature_after else None,
    })
    return payload


def summarize_process_records(records: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    times = [float(item["median_ns"]) for item in records]
    tsc = [float(item["median_tsc"]) for item in records]
    frequencies = [float(item["frequency_khz_mean"]) for item in records if item.get("frequency_khz_mean")]
    temperatures = [float(item["temperature_millic_mean"]) for item in records if item.get("temperature_millic_mean")]
    interval = _bootstrap_mean_interval(times, seed)
    regression = _linear_regression(records)
    return {
        "process_count": len(records), "mean_process_median_ns": sum(times)/len(times),
        "median_process_median_ns": empirical_quantile(times, 0.5), "mean_ns_95": interval,
        "mean_process_median_tsc": sum(tsc)/len(tsc),
        "frequency_khz_range": [min(frequencies), max(frequencies)] if frequencies else None,
        "temperature_millic_range": [min(temperatures), max(temperatures)] if temperatures else None,
        "frequency_temperature_regression": regression,
    }


def perf_probe(
    harness: dict[str, Any], fixtures: dict[str, Path], candidate: str, n: int, nc: int, nr: int,
    cache_mode: str, eviction_bytes: int, cpu: int,
) -> dict[str, Any]:
    events = [
        "cycles", "instructions", "branches", "branch-misses", "cache-misses",
        "l2_cache_req_stat.ic_dc_miss_in_l2", "ls_any_fills_from_sys.dram_io_all",
    ]
    command = [
        "perf", "stat", "-x,", "-e", ",".join(events), "--", "taskset", "-c", str(cpu),
        harness["binary"], candidate, str(fixtures["weights"]), str(fixtures["activation"]),
        str(fixtures["expanded"]), str(n), str(nc), str(nr), "7", "1", cache_mode, str(eviction_bytes),
    ]
    result = run(command, timeout=300)
    if result.returncode:
        return {"status": "UNAVAILABLE", "reason": result.stderr[-1000:], "command": command}
    counters: dict[str, float] = {}
    for line in result.stderr.splitlines():
        fields = line.split(",")
        if len(fields) >= 3:
            try:
                counters[fields[2]] = float(fields[0])
            except ValueError:
                continue
    if "ls_any_fills_from_sys.dram_io_all" in counters:
        counters["estimated_dram_fill_bytes"] = 64.0*counters["ls_any_fills_from_sys.dram_io_all"]
    return {"status": "PASS", "counters": counters, "command": command, "supporting_evidence_only": True}


def _bootstrap_mean_interval(values: list[float], seed: int, rounds: int = 5000) -> list[float]:
    rng = random.Random(seed); means = []
    for _ in range(rounds):
        means.append(sum(values[rng.randrange(len(values))] for _ in values)/len(values))
    return [empirical_quantile(means, 0.025), empirical_quantile(means, 0.975)]


def _linear_regression(records: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [item for item in records if item.get("frequency_khz_mean") and item.get("temperature_millic_mean")]
    if len(usable) < 4:
        return {"status": "INSUFFICIENT"}
    frequencies = [float(item["frequency_khz_mean"])/1e6 for item in usable]
    temperatures = [float(item["temperature_millic_mean"])/1000.0 for item in usable]
    times = [float(item["median_ns"]) for item in usable]
    f0=sum(frequencies)/len(frequencies); t0=sum(temperatures)/len(temperatures)
    x = [[1.0, f-f0, t-t0] for f,t in zip(frequencies,temperatures)]
    xtx = [[sum(row[i]*row[j] for row in x) for j in range(3)] for i in range(3)]
    xty = [sum(row[i]*value for row,value in zip(x,times)) for i in range(3)]
    coefficients = _solve3(xtx, xty)
    predicted = [sum(c*v for c,v in zip(coefficients,row)) for row in x]
    mean=sum(times)/len(times); total=sum((v-mean)**2 for v in times); residual=sum((v-p)**2 for v,p in zip(times,predicted))
    return {
        "status": "PASS", "intercept_ns_at_mean_conditions": coefficients[0],
        "ns_per_ghz": coefficients[1], "ns_per_celsius": coefficients[2],
        "mean_frequency_ghz": f0, "mean_temperature_celsius": t0,
        "r_squared": 1.0-residual/total if total else 0.0,
        "use": "nuisance-variable sensitivity; unadjusted randomized results remain primary",
    }


def _solve3(matrix: list[list[float]], vector: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row,value in zip(matrix,vector)]
    for column in range(3):
        pivot=max(range(column,3),key=lambda row:abs(augmented[row][column])); augmented[column],augmented[pivot]=augmented[pivot],augmented[column]
        if abs(augmented[column][column]) < 1e-12:
            return [sum(vector)/max(1,len(vector)),0.0,0.0]
        scale=augmented[column][column]; augmented[column]=[value/scale for value in augmented[column]]
        for row in range(3):
            if row==column: continue
            factor=augmented[row][column]; augmented[row]=[value-factor*base for value,base in zip(augmented[row],augmented[column])]
    return [augmented[index][3] for index in range(3)]


def _frequency_khz(cpu: int) -> int:
    try:
        return int(Path(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq").read_text())
    except (OSError, ValueError):
        return 0


def _temperature_millic() -> int:
    values=[]
    for path in Path("/sys/class/hwmon").glob("hwmon*/temp*_input"):
        try:
            value=int(path.read_text());
        except (OSError, ValueError):
            continue
        if 0 < value < 120000: values.append(value)
    return max(values, default=0)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
