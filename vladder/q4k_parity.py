from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess
from typing import Any

from .q4k_semantics import Q4KBlock, Q8KBlock, pack_scale_min, repack_q4k_x8
from .report import write_json
from .statistics_v3 import empirical_quantile
from .toolchain import run


HARNESS_SOURCE = r'''
#include "repack.h"
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
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    if (!input) std::exit(10);
    const auto size = input.tellg(); input.seekg(0);
    std::vector<uint8_t> data((size_t) size);
    input.read((char *) data.data(), size);
    return data;
}
static uint32_t bits(float value) { uint32_t out; std::memcpy(&out, &value, 4); return out; }
static uint64_t hash_outputs(const std::vector<float> & values) {
    uint64_t hash = UINT64_C(1469598103934665603);
    for (float value : values) { hash ^= bits(value); hash *= UINT64_C(1099511628211); }
    return hash;
}
static int compare_outputs(const std::vector<float> & native, const std::vector<float> & regenerated) {
    for (size_t index = 0; index < native.size(); ++index) {
        if (bits(native[index]) != bits(regenerated[index])) {
            std::fprintf(stderr, "mismatch index=%zu native=%a regenerated=%a native_bits=%08x regenerated_bits=%08x\n",
                         index, native[index], regenerated[index], bits(native[index]), bits(regenerated[index]));
            return 1;
        }
    }
    return 0;
}
using kernel_fn = void (*)(int, float *, size_t, const void *, const void *, int, int);
int main(int argc, char ** argv) {
    if (argc < 8) return 2;
    const std::string candidate = argv[1];
    const auto weights = read_file(argv[2]); const auto activation = read_file(argv[3]);
    const int n = std::atoi(argv[4]), nc = std::atoi(argv[5]), reps = std::atoi(argv[6]), inner = std::atoi(argv[7]);
    std::vector<float> native((size_t)nc), regenerated((size_t)nc);
    ggml_gemv_q4_K_8x8_q8_K(n, native.data(), nc, weights.data(), activation.data(), 1, nc);
    vladder_regenerated_gemv_q4_K_8x8_q8_K(n, regenerated.data(), nc, weights.data(), activation.data(), 1, nc);
    if (compare_outputs(native, regenerated)) {
        std::printf("{\"verify\":\"FAIL\"}\n"); return 3;
    }
    kernel_fn fn = candidate == "native" ? ggml_gemv_q4_K_8x8_q8_K : vladder_regenerated_gemv_q4_K_8x8_q8_K;
    for (int warmup = 0; warmup < 4; ++warmup) fn(n, regenerated.data(), nc, weights.data(), activation.data(), 1, nc);
    std::vector<uint64_t> samples((size_t)reps); uint64_t guard = 0;
    for (int rep = 0; rep < reps; ++rep) {
        const auto start = std::chrono::steady_clock::now();
        for (int iteration = 0; iteration < inner; ++iteration) fn(n, regenerated.data(), nc, weights.data(), activation.data(), 1, nc);
        const auto end = std::chrono::steady_clock::now();
        samples[(size_t)rep] = (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count() / (uint64_t)inner;
        guard ^= hash_outputs(regenerated);
    }
    std::sort(samples.begin(), samples.end());
    std::printf("{\"verify\":\"PASS\",\"candidate\":\"%s\",\"median_ns\":%llu,\"output_hash\":\"%016llx\",\"guard\":\"%016llx\"}\n",
                candidate.c_str(), (unsigned long long)samples[samples.size()/2],
                (unsigned long long)hash_outputs(native), (unsigned long long)guard);
    return 0;
}
'''


def run_q4k_parity(
    active_manifest_path: Path,
    out_dir: Path,
    *,
    processes: int = 10,
    repetitions: int = 25,
    inner: int = 4,
    seed: int = 7707,
) -> dict[str, Any]:
    if processes < 2:
        raise ValueError("Q4_K parity requires at least two independent processes")
    active = json.loads(active_manifest_path.read_text())
    if active.get("status") != "PASS":
        raise ValueError("Q4_K parity requires a passing active-path manifest")
    out_dir.mkdir(parents=True, exist_ok=True)
    llama_root = Path(active["source_provenance"]["kernel"]["path"]).parents[5]
    build = Path(active["build"]["directory"])
    kernel_source = Path(active["source_provenance"]["kernel"]["path"])
    extracted = _extract_function(kernel_source.read_text(), "ggml_gemv_q4_K_8x8_q8_K")
    regenerated = _regenerated_source(extracted)
    regenerated_path = out_dir / "regenerated-q4k-gemv.cpp"
    harness_path = out_dir / "q4k-parity-harness.cpp"
    binary = out_dir / "q4k-parity-harness"
    regenerated_path.write_text(regenerated)
    harness_path.write_text(HARNESS_SOURCE)
    include_dirs = [llama_root / "ggml/include", llama_root / "ggml/src", llama_root / "ggml/src/ggml-cpu"]
    command = ["clang++-20", "-std=gnu++17", "-O3", "-DNDEBUG", "-march=native"]
    command.extend(f"-I{path}" for path in include_dirs)
    command.extend([
        str(regenerated_path), str(harness_path), f"-L{build/'bin'}", f"-Wl,-rpath,{build/'bin'}",
        "-lggml-cpu", "-lggml-base", "-lggml", "-pthread", "-lm", "-o", str(binary),
    ])
    compiled = run(command, timeout=180)
    if compiled.returncode:
        raise RuntimeError((compiled.stdout + compiled.stderr)[-8000:])
    fixture_dir = out_dir / "fixtures"
    fixture_dir.mkdir(exist_ok=True)
    verification = []
    for index, mode in enumerate(("random", "zeros", "maxima", "alternating", "sparse", "random")):
        weights, activation = _fixture(fixture_dir, f"verify-{index}-{mode}", 256, 8, mode, seed + index)
        result = run([str(binary), "regenerated", str(weights), str(activation), "256", "8", "1", "1"], timeout=30, env={"LD_LIBRARY_PATH": str(build / "bin")})
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[-3000:])
        payload = json.loads(result.stdout.splitlines()[-1])
        verification.append({"mode": mode, **payload})
    production_n, production_nc = 2560, 9728
    weights, activation = _fixture(fixture_dir, "qwen-gate-up", production_n, production_nc, "random", seed)
    labels = ["native", "regenerated"]
    order = [(process, label) for process in range(processes) for label in labels]
    random.Random(seed).shuffle(order)
    samples = {label: [] for label in labels}
    audit = []
    output_hashes = set()
    for ordinal, (process, label) in enumerate(order):
        result = run([
            str(binary), label, str(weights), str(activation), str(production_n), str(production_nc),
            str(repetitions), str(inner),
        ], timeout=180, env={"LD_LIBRARY_PATH": str(build / "bin")})
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[-4000:])
        payload = json.loads(result.stdout.splitlines()[-1])
        if payload["verify"] != "PASS":
            raise RuntimeError("regenerated Q4_K baseline failed E1 verification")
        samples[label].append(float(payload["median_ns"]))
        output_hashes.add(payload["output_hash"])
        audit.append({"ordinal": ordinal, "process": process, **payload})
    if len(output_hashes) != 1:
        raise RuntimeError("Q4_K parity output hashes are not deterministic")
    interval = _speedup_interval(samples["native"], samples["regenerated"], seed)
    native_mean = sum(samples["native"]) / len(samples["native"])
    regenerated_mean = sum(samples["regenerated"]) / len(samples["regenerated"])
    regression = (regenerated_mean / native_mean - 1.0) * 100.0
    classification = "parity_pass" if regression <= 3.0 and interval[0] >= -5.0 else "parity_fail"
    assembly = _assembly_report(build / "bin/libggml-cpu.so", binary, out_dir)
    perf = {label: _perf_probe(binary, label, weights, activation, production_n, production_nc, build / "bin") for label in labels}
    report = {
        "schema_version": "vladder-q4k-parity-v7.0",
        "classification": classification,
        "contract": "E1 bitwise production equivalence",
        "active_path_manifest_sha256": hashlib.sha256(active_manifest_path.read_bytes()).hexdigest(),
        "regenerated_source_sha256": hashlib.sha256(regenerated_path.read_bytes()).hexdigest(),
        "extraction": {"source": str(kernel_source), "source_symbol": "ggml_gemv_q4_K_8x8_q8_K", "generated_symbol": "vladder_regenerated_gemv_q4_K_8x8_q8_K"},
        "compiler": {"command": command, "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()},
        "verification": {"status": "PASS", "cases": verification, "production_output_hash": next(iter(output_hashes))},
        "benchmark": {
            "dimensions": {"input": production_n, "outputs": production_nc, "tokens": 1},
            "processes": processes, "repetitions": repetitions, "inner": inner, "randomized_order": order,
            "native_mean_process_median_ns": native_mean,
            "regenerated_mean_process_median_ns": regenerated_mean,
            "regenerated_regression_percent": regression,
            "regenerated_speedup_95": interval,
            "gate": "p50 regression <= 3%; confidence interval lower speedup bound >= -5%",
        },
        "assembly": assembly,
        "perf": perf,
        "dynamic_allocation_hot_loop": False,
        "claim": "Regenerated baseline performance parity and E1 semantics pass." if classification == "parity_pass" else "Transformation search is blocked until regenerated baseline parity is corrected.",
    }
    write_json(out_dir / "q4k-parity-audit.json", audit)
    write_json(out_dir / "q4k-parity-report.json", report)
    return report


def _extract_function(source: str, symbol: str) -> str:
    match = re.search(rf"void\s+{re.escape(symbol)}\s*\(", source)
    if not match:
        raise ValueError(f"unable to extract {symbol}")
    start = match.start()
    brace = source.find("{", match.end())
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise ValueError(f"unterminated function {symbol}")


def _regenerated_source(function: str) -> str:
    renamed = function.replace("void ggml_gemv_q4_K_8x8_q8_K(", "extern \"C\" void vladder_regenerated_gemv_q4_K_8x8_q8_K(", 1)
    return '''#define GGML_COMMON_DECL_CPP
#include "ggml-common.h"
#include "repack.h"
#include <immintrin.h>
#include <cassert>
#include <cstdint>
#include <cstring>
#define UNUSED GGML_UNUSED
#define GGML_F32Cx8_LOAD(x) _mm256_cvtph_ps(_mm_loadu_si128((const __m128i *)(x)))
#define GGML_F32Cx8_REARRANGE_LOAD(x, arrangeMask) _mm256_cvtph_ps(_mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(x)), arrangeMask))
''' + renamed + "\n"


def _fixture(directory: Path, name: str, n: int, nc: int, mode: str, seed: int) -> tuple[Path, Path]:
    if n % 256 or nc % 8:
        raise ValueError("Q4_Kx8 fixture dimensions require n % 256 == 0 and nc % 8 == 0")
    rng = random.Random(seed)
    nblocks = n // 256
    repacked = bytearray()
    for row_group in range(nc // 8):
        for block_index in range(nblocks):
            blocks = tuple(_q4_block(rng, mode, row_group * 8 + row, block_index) for row in range(8))
            repacked.extend(repack_q4k_x8(blocks).to_bytes())
    activation = b"".join(_q8_block(rng, mode, block_index).to_bytes() for block_index in range(nblocks))
    weight_path, activation_path = directory / f"{name}.q4kx8", directory / f"{name}.q8k"
    weight_path.write_bytes(repacked)
    activation_path.write_bytes(activation)
    return weight_path, activation_path


def _q4_block(rng: random.Random, mode: str, row: int, block: int) -> Q4KBlock:
    if mode == "zeros":
        return Q4KBlock(0, 0, bytes(12), bytes(128))
    if mode == "maxima":
        return Q4KBlock(0x3c00, 0x3c00, pack_scale_min([63] * 8, [63] * 8), bytes([255] * 128))
    if mode == "alternating":
        return Q4KBlock(0x3800, 0x3400, pack_scale_min([63 if i % 2 else 0 for i in range(8)], [0 if i % 2 else 63 for i in range(8)]), bytes(255 if i % 2 else 0 for i in range(128)))
    if mode == "sparse":
        quants = bytearray(128); quants[(row + block) % 128] = 1
        return Q4KBlock(0x3000, 0, pack_scale_min([1] * 8, [0] * 8), bytes(quants))
    return Q4KBlock(
        rng.choice((0x2400, 0x2c00, 0x3400, 0x3800, 0x3c00)),
        rng.choice((0, 0x2000, 0x2c00, 0x3400)),
        pack_scale_min([rng.randrange(64) for _ in range(8)], [rng.randrange(64) for _ in range(8)]),
        bytes(rng.randrange(256) for _ in range(128)),
    )


def _q8_block(rng: random.Random, mode: str, block: int) -> Q8KBlock:
    if mode == "zeros":
        values, scale = [0] * 256, 0.0
    elif mode == "maxima":
        values, scale = [127] * 256, 1.0
    elif mode == "alternating":
        values, scale = [127 if i % 2 else -127 for i in range(256)], 0.5
    elif mode == "sparse":
        values, scale = [0] * 256, 0.125; values[block % 256] = 127
    else:
        values, scale = [rng.randrange(-127, 128) for _ in range(256)], rng.choice((0.0078125, 0.03125, 0.125, 0.5, 1.0))
    return Q8KBlock(scale, tuple(values), tuple(sum(values[i:i + 16]) for i in range(0, 256, 16)))


def _speedup_interval(native: list[float], regenerated: list[float], seed: int, rounds: int = 5000) -> list[float]:
    rng = random.Random(seed)
    values = []
    for _ in range(rounds):
        baseline = sum(native[rng.randrange(len(native))] for _ in native) / len(native)
        candidate = sum(regenerated[rng.randrange(len(regenerated))] for _ in regenerated) / len(regenerated)
        values.append((baseline / candidate - 1.0) * 100.0)
    return [empirical_quantile(values, 0.025), empirical_quantile(values, 0.975)]


def _assembly_report(library: Path, binary: Path, out_dir: Path) -> dict[str, Any]:
    symbols = {
        "native": (library, "ggml_gemv_q4_K_8x8_q8_K"),
        "regenerated": (binary, "vladder_regenerated_gemv_q4_K_8x8_q8_K"),
    }
    report = {}
    for label, (artifact, symbol) in symbols.items():
        disassembly = run(["objdump", "-d", "-C", f"--disassemble={symbol}", str(artifact)], timeout=60)
        if disassembly.returncode:
            raise RuntimeError(f"objdump failed for {label}")
        (out_dir / f"{label}.assembly.txt").write_text(disassembly.stdout)
        instructions = [line for line in disassembly.stdout.splitlines() if re.match(r"^\s*[0-9a-f]+:\s", line)]
        mnemonics = [match.group(1) for line in instructions if (match := re.search(r"\t([a-z][a-z0-9]+)\s", line))]
        report[label] = {
            "instruction_count": len(instructions),
            "vector_instruction_count": sum(item.startswith("v") for item in mnemonics),
            "load_store_instruction_count": sum(item.startswith(("vmov", "mov")) for item in mnemonics),
            "branch_instruction_count": sum(item.startswith("j") or item in {"call", "ret"} for item in mnemonics),
            "stack_reference_count": sum("%rsp" in line or "%rbp" in line for line in instructions),
            "integer_dot_instructions": sum(item in {"vpmaddubsw", "vpmaddwd"} for item in mnemonics),
            "float_fma_instructions": sum(item.startswith("vfmadd") for item in mnemonics),
        }
    return report


def _perf_probe(binary: Path, label: str, weights: Path, activation: Path, n: int, nc: int, library_dir: Path) -> dict[str, Any]:
    result = run([
        "perf", "stat", "-x,", "-e", "cycles,instructions,branches,branch-misses,cache-misses", "--",
        str(binary), label, str(weights), str(activation), str(n), str(nc), "3", "1",
    ], timeout=60, env={"LD_LIBRARY_PATH": str(library_dir)})
    if result.returncode:
        return {"status": "UNAVAILABLE", "reason": result.stderr[-500:]}
    counters: dict[str, float] = {}
    for line in result.stderr.splitlines():
        fields = line.split(",")
        if len(fields) >= 3:
            try:
                counters[fields[2]] = float(fields[0])
            except ValueError:
                continue
    return {"status": "PASS", "counters": counters}
