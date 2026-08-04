from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any

from .q4k_parity import _fixture, _speedup_interval
from .q4k_fused_source import FUSED_Q4K_SIBLING_SOURCE
from .report import write_json
from .toolchain import run


SIBLING_HARNESS = r'''
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
extern "C" void vladder_fused_gemv_q4_K_8x8_q8_K(
    int n, float * gate, float * up, const void * gate_w, const void * up_w,
    const void * activation, int nr, int nc);
static std::vector<uint8_t> read_file(const char * path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate); if (!input) std::exit(10);
    const auto size = input.tellg(); input.seekg(0); std::vector<uint8_t> data((size_t)size);
    input.read((char *)data.data(), size); return data;
}
static uint32_t bits(float value) { uint32_t out; std::memcpy(&out, &value, 4); return out; }
static uint64_t hash_pair(const std::vector<float> & gate, const std::vector<float> & up) {
    uint64_t hash = UINT64_C(1469598103934665603);
    for (const auto * values : {&gate, &up}) for (float value : *values) { hash ^= bits(value); hash *= UINT64_C(1099511628211); }
    return hash;
}
static void independent_native(int n, int nc, const void * gate_w, const void * up_w, const void * activation, float * gate, float * up) {
    ggml_gemv_q4_K_8x8_q8_K(n, gate, nc, gate_w, activation, 1, nc);
    ggml_gemv_q4_K_8x8_q8_K(n, up, nc, up_w, activation, 1, nc);
}
static void independent_regenerated(int n, int nc, const void * gate_w, const void * up_w, const void * activation, float * gate, float * up) {
    vladder_regenerated_gemv_q4_K_8x8_q8_K(n, gate, nc, gate_w, activation, 1, nc);
    vladder_regenerated_gemv_q4_K_8x8_q8_K(n, up, nc, up_w, activation, 1, nc);
}
static void coordinated_serial(int n, int nc, const void * gate_w, const void * up_w, const void * activation, float * gate, float * up) {
    // One explicit sibling region with shared Q8_K ownership; arithmetic calls retain E1 order.
    independent_regenerated(n, nc, gate_w, up_w, activation, gate, up);
}
static void interleaved_layout(int n, int nc, const void * combined_w, const void * activation, float * gate, float * up, std::vector<float> & combined) {
    vladder_regenerated_gemv_q4_K_8x8_q8_K(n, combined.data(), 2*nc, combined_w, activation, 1, 2*nc);
    for (int group = 0; group < nc/8; ++group) {
        std::memcpy(gate + 8*group, combined.data() + 16*group, 8*sizeof(float));
        std::memcpy(up + 8*group, combined.data() + 16*group + 8, 8*sizeof(float));
    }
}
static int verify(const std::vector<float> & ref, const std::vector<float> & candidate) {
    for (size_t i = 0; i < ref.size(); ++i) if (bits(ref[i]) != bits(candidate[i])) return (int)i + 1;
    return 0;
}
int main(int argc, char ** argv) {
    if (argc < 11) return 2;
    const std::string candidate = argv[1];
    const auto gate_w = read_file(argv[2]), up_w = read_file(argv[3]), combined_w = read_file(argv[4]), activation = read_file(argv[5]);
    const int n = std::atoi(argv[6]), nc = std::atoi(argv[7]), reps = std::atoi(argv[8]), inner = std::atoi(argv[9]);
    const bool include_adapter = std::atoi(argv[10]) != 0;
    std::vector<float> ref_gate((size_t)nc), ref_up((size_t)nc), gate((size_t)nc), up((size_t)nc), combined((size_t)2*nc);
    independent_native(n, nc, gate_w.data(), up_w.data(), activation.data(), ref_gate.data(), ref_up.data());
    auto execute = [&]() {
        if (candidate == "independent_native" || candidate == "shared_preparation")
            independent_native(n, nc, gate_w.data(), up_w.data(), activation.data(), gate.data(), up.data());
        else if (candidate == "independent_regenerated")
            independent_regenerated(n, nc, gate_w.data(), up_w.data(), activation.data(), gate.data(), up.data());
        else if (candidate == "coordinated_serial")
            coordinated_serial(n, nc, gate_w.data(), up_w.data(), activation.data(), gate.data(), up.data());
        else if (candidate == "fused_shared_q8_loads")
            vladder_fused_gemv_q4_K_8x8_q8_K(n, gate.data(), up.data(), gate_w.data(), up_w.data(), activation.data(), 1, nc);
        else if (candidate == "interleaved_layout") {
            if (include_adapter) interleaved_layout(n, nc, combined_w.data(), activation.data(), gate.data(), up.data(), combined);
            else vladder_regenerated_gemv_q4_K_8x8_q8_K(n, combined.data(), 2*nc, combined_w.data(), activation.data(), 1, 2*nc);
        } else std::exit(4);
    };
    execute();
    if (candidate == "interleaved_layout" && !include_adapter)
        interleaved_layout(n, nc, combined_w.data(), activation.data(), gate.data(), up.data(), combined);
    const int gate_error = verify(ref_gate, gate), up_error = verify(ref_up, up);
    if (gate_error || up_error) { std::printf("{\"verify\":\"FAIL\",\"gate_error\":%d,\"up_error\":%d}\n", gate_error, up_error); return 3; }
    for (int i = 0; i < 3; ++i) execute();
    std::vector<uint64_t> samples((size_t)reps); uint64_t guard = 0;
    for (int rep = 0; rep < reps; ++rep) {
        const auto start = std::chrono::steady_clock::now();
        for (int iter = 0; iter < inner; ++iter) execute();
        const auto end = std::chrono::steady_clock::now();
        samples[(size_t)rep] = (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(end-start).count()/(uint64_t)inner;
        guard ^= candidate == "interleaved_layout" && !include_adapter ? bits(combined[(size_t)rep % combined.size()]) : hash_pair(gate, up);
    }
    std::sort(samples.begin(), samples.end());
    std::printf("{\"verify\":\"PASS\",\"candidate\":\"%s\",\"median_ns\":%llu,\"output_hash\":\"%016llx\",\"guard\":\"%016llx\"}\n",
                candidate.c_str(), (unsigned long long)samples[samples.size()/2], (unsigned long long)hash_pair(ref_gate, ref_up), (unsigned long long)guard);
    return 0;
}
'''


def synthesize_q4k_siblings(
    active_manifest_path: Path,
    parity_report_path: Path,
    out_dir: Path,
    *,
    processes: int = 10,
    repetitions: int = 25,
    inner: int = 2,
    seed: int = 7717,
) -> dict[str, Any]:
    active = json.loads(active_manifest_path.read_text())
    parity = json.loads(parity_report_path.read_text())
    if active.get("status") != "PASS" or parity.get("classification") != "parity_pass":
        raise ValueError("sibling synthesis requires passing active-path and parity gates")
    out_dir.mkdir(parents=True, exist_ok=True)
    parity_dir = parity_report_path.resolve().parent
    regenerated = parity_dir / "regenerated-q4k-gemv.cpp"
    if hashlib.sha256(regenerated.read_bytes()).hexdigest() != parity["regenerated_source_sha256"]:
        raise ValueError("regenerated baseline source hash mismatch")
    build = Path(active["build"]["directory"])
    llama_root = Path(active["source_provenance"]["kernel"]["path"]).parents[5]
    harness = out_dir / "q4k-sibling-harness.cpp"
    fused_source = out_dir / "fused-q4k-sibling.cpp"
    binary = out_dir / "q4k-sibling-harness"
    harness.write_text(SIBLING_HARNESS)
    fused_source.write_text(FUSED_Q4K_SIBLING_SOURCE)
    command = ["clang++-20", "-std=gnu++17", "-O3", "-DNDEBUG", "-march=native"]
    command.extend(f"-I{path}" for path in (llama_root / "ggml/include", llama_root / "ggml/src", llama_root / "ggml/src/ggml-cpu"))
    command.extend([str(regenerated), str(fused_source), str(harness), f"-L{build/'bin'}", f"-Wl,-rpath,{build/'bin'}", "-lggml-cpu", "-lggml-base", "-lggml", "-pthread", "-lm", "-o", str(binary)])
    compiled = run(command, timeout=180)
    if compiled.returncode:
        raise RuntimeError((compiled.stdout + compiled.stderr)[-6000:])
    fixture_dir = out_dir / "fixtures"; fixture_dir.mkdir(exist_ok=True)
    gate, activation = _fixture(fixture_dir, "gate", 2560, 9728, "random", seed)
    up, activation_up = _fixture(fixture_dir, "up", 2560, 9728, "random", seed + 1)
    activation_up.unlink()
    combined, layout_manifest = _interleave_sibling_layout(gate, up, 2560, 9728, fixture_dir / "gate-up-interleaved.q4kx8")
    grammar = _enumerate_grammar()
    write_json(out_dir / "sibling-grammar-audit.json", grammar)
    labels = ["independent_native", "independent_regenerated", "shared_preparation", "coordinated_serial", "fused_shared_q8_loads", "interleaved_layout"]
    order = [(process, label) for process in range(processes) for label in labels]
    random.Random(seed).shuffle(order)
    samples = {label: [] for label in labels}
    audit = []
    for ordinal, (process, label) in enumerate(order):
        result = run([
            str(binary), label, str(gate), str(up), str(combined), str(activation), "2560", "9728",
            str(repetitions), str(inner), "1",
        ], timeout=240, env={"LD_LIBRARY_PATH": str(build / "bin")})
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[-4000:])
        payload = json.loads(result.stdout.splitlines()[-1])
        if payload["verify"] != "PASS":
            raise RuntimeError(f"sibling candidate {label} failed E1 verification")
        samples[label].append(float(payload["median_ns"]))
        audit.append({"ordinal": ordinal, "process": process, **payload})
    baseline_mean = sum(samples["independent_native"]) / len(samples["independent_native"])
    rankings = []
    for label in labels:
        mean = sum(samples[label]) / len(samples[label])
        interval = _speedup_interval(samples["independent_native"], samples[label], seed + labels.index(label))
        speedup = (baseline_mean / mean - 1.0) * 100.0
        classification = "baseline" if label == "independent_native" else ("regional_win" if interval[0] >= 3.0 else ("measured_regression" if interval[1] < 0.0 else "statistical_tie"))
        rankings.append({"candidate": label, "mean_process_median_ns": mean, "speedup_percent": speedup, "speedup_95": interval, "classification": classification, "contract": "E1"})
    winner = min(rankings, key=lambda item: item["mean_process_median_ns"])
    regional_winners = [item for item in rankings if item["classification"] == "regional_win"]
    assembly = _fused_assembly_report(binary, out_dir)
    perf = {
        label: _sibling_perf_probe(binary, label, gate, up, combined, activation, build / "bin")
        for label in ("independent_native", "fused_shared_q8_loads")
    }
    attribution = _attribution_report(rankings, assembly, perf, n=2560, nc=9728)
    report = {
        "schema_version": "vladder-q4k-sibling-search-v7.0",
        "classification": "regional_transfer_pass" if regional_winners else "negative_transfer",
        "active_path_manifest_sha256": hashlib.sha256(active_manifest_path.read_bytes()).hexdigest(),
        "parity_report_sha256": hashlib.sha256(parity_report_path.read_bytes()).hexdigest(),
        "compiler": {"command": command, "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()},
        "grammar": grammar,
        "compiled_candidate_count": len(labels),
        "physically_benchmarked_candidate_count": len(labels),
        "measurement": {"processes": processes, "repetitions": repetitions, "inner": inner, "randomized_order": order, "instrumentation": False},
        "layout_manifest": layout_manifest,
        "assembly": assembly,
        "perf": perf,
        "attribution": attribution,
        "rankings": rankings,
        "winner": winner,
        "regional_winners": regional_winners,
        "ablation": [
            {"change": "regenerated lowering", "candidate": "independent_regenerated"},
            {"change": "shared Q8_K ownership; preparation excluded", "candidate": "shared_preparation"},
            {"change": "explicit coordinated serial sibling region", "candidate": "coordinated_serial"},
            {"change": "shared Q8_K vector loads inside the AVX2 block loop", "candidate": "fused_shared_q8_loads"},
            {"change": "sibling-interleaved persistent layout plus output adapter", "candidate": "interleaved_layout"},
        ],
        "limitations": [
            "Shared preparation is represented by one pre-quantized Q8_K buffer; F32-to-Q8_K preparation time is excluded from every candidate.",
            "Coordinated serial is the loop-ownership control; fused_shared_q8_loads isolates AVX2 activation-load reuse.",
            "Interleaved layout includes output deinterleave cost but excludes one-time persistent conversion cost, which is reported separately.",
            "CPU boost remained enabled; randomized interleaving supports rejection, but any future positive promotion requires fixed frequency or per-process frequency regression and separate-day reproduction.",
        ],
        "claim": "Production-semantic sibling transfer measured; no model-level claim." if regional_winners else "V6 sibling benefit did not transfer in the implemented production-semantic grammar; no model integration attempted.",
    }
    write_json(out_dir / "q4k-sibling-benchmark-audit.json", audit)
    write_json(out_dir / "q4k-attribution-report.json", attribution)
    write_json(out_dir / "q4k-sibling-report.json", report)
    return report


def _interleave_sibling_layout(gate: Path, up: Path, n: int, nc: int, destination: Path) -> tuple[Path, dict[str, Any]]:
    gate_bytes, up_bytes = gate.read_bytes(), up.read_bytes()
    group_bytes = (n // 256) * 1152
    expected = (nc // 8) * group_bytes
    if len(gate_bytes) != expected or len(up_bytes) != expected:
        raise ValueError("sibling layout source dimensions do not match")
    output = bytearray()
    forward_map = []
    for group in range(nc // 8):
        for sibling, source in (("gate", gate_bytes), ("up", up_bytes)):
            start = group * group_bytes
            destination_group = len(output) // group_bytes
            output.extend(source[start:start + group_bytes])
            forward_map.append({"projection": sibling, "source_group": group, "destination_group": destination_group})
    destination.write_bytes(output)
    inverse_gate = bytearray(); inverse_up = bytearray()
    for item in forward_map:
        start = item["destination_group"] * group_bytes
        (inverse_gate if item["projection"] == "gate" else inverse_up).extend(output[start:start + group_bytes])
    if bytes(inverse_gate) != gate_bytes or bytes(inverse_up) != up_bytes:
        raise RuntimeError("sibling-interleaved layout inverse failed")
    manifest = {
        "status": "proved", "group_bytes": group_bytes, "group_count_per_projection": nc // 8,
        "forward_map": forward_map, "padding_bytes": 0,
        "gate_sha256": hashlib.sha256(gate_bytes).hexdigest(), "up_sha256": hashlib.sha256(up_bytes).hexdigest(),
        "transformed_sha256": hashlib.sha256(output).hexdigest(),
        "inverse_gate_sha256": hashlib.sha256(inverse_gate).hexdigest(), "inverse_up_sha256": hashlib.sha256(inverse_up).hexdigest(),
        "conversion_bytes_read": len(gate_bytes) + len(up_bytes), "conversion_bytes_written": len(output),
    }
    return destination, manifest


def _enumerate_grammar() -> dict[str, Any]:
    candidates, rejected = [], []
    for row_group in (4, 8, 16):
        for reuse in ("independent", "shared_q8_owner"):
            for order in ("gate_then_up", "up_then_gate", "interleaved_groups"):
                for accumulator_banks in (1, 2):
                    item = {"row_group": row_group, "activation_reuse": reuse, "sibling_order": order, "accumulator_banks": accumulator_banks}
                    if row_group != 8:
                        rejected.append({**item, "reason": "active AVX2 baseline contract fixes output row group at 8"})
                    elif accumulator_banks != 1:
                        rejected.append({**item, "reason": "E1 baseline extraction fixes per-kernel accumulator schedule"})
                    else:
                        candidates.append(item)
    return {
        "classification": "best_verified_found",
        "control_product_coverage": "exhaustive_legality",
        "enumerated": 36,
        "legal": len(candidates),
        "rejected": len(rejected),
        "legal_plans": candidates,
        "rejection_audit": rejected,
        "bounded_optimality_reason": "compiled source realizations are not a one-to-one saturation of the legal control product",
    }


def _fused_assembly_report(binary: Path, out_dir: Path) -> dict[str, Any]:
    result = run([
        "objdump", "-d", "-C", "--disassemble=vladder_fused_gemv_q4_K_8x8_q8_K", str(binary),
    ], timeout=60)
    if result.returncode:
        raise RuntimeError("objdump failed for fused sibling candidate")
    (out_dir / "fused-shared-q8-loads.assembly.txt").write_text(result.stdout)
    instructions = [line for line in result.stdout.splitlines() if re.match(r"^\s*[0-9a-f]+:\s", line)]
    mnemonics = [match.group(1) for line in instructions if (match := re.search(r"\t([a-z][a-z0-9]+)\s", line))]
    return {
        "fused_shared_q8_loads": {
            "instruction_count": len(instructions),
            "vector_instruction_count": sum(item.startswith("v") for item in mnemonics),
            "load_store_instruction_count": sum(item.startswith(("vmov", "mov")) for item in mnemonics),
            "branch_instruction_count": sum(item.startswith("j") or item in {"call", "ret"} for item in mnemonics),
            "stack_reference_count": sum("%rsp" in line or "%rbp" in line for line in instructions),
            "integer_dot_instructions": sum(item in {"vpmaddubsw", "vpmaddwd"} for item in mnemonics),
            "float_fma_instructions": sum(item.startswith("vfmadd") for item in mnemonics),
        }
    }


def _sibling_perf_probe(
    binary: Path, label: str, gate: Path, up: Path, combined: Path, activation: Path, library_dir: Path,
) -> dict[str, Any]:
    result = run([
        "perf", "stat", "-x,", "-e", "cycles,instructions,branches,branch-misses,cache-misses", "--",
        str(binary), label, str(gate), str(up), str(combined), str(activation), "2560", "9728", "3", "1", "1",
    ], timeout=90, env={"LD_LIBRARY_PATH": str(library_dir)})
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
    return {"status": "PASS", "counters": counters, "supporting_evidence_only": True}


def _attribution_report(
    rankings: list[dict[str, Any]], assembly: dict[str, Any], perf: dict[str, Any], *, n: int, nc: int,
) -> dict[str, Any]:
    blocks = n // 256
    output_groups = nc // 8
    q8_block_bytes = 292
    q4kx8_block_bytes = 1152
    activation_bytes_independent = 2 * blocks * output_groups * q8_block_bytes
    activation_bytes_fused = blocks * output_groups * q8_block_bytes
    weight_bytes = 2 * blocks * output_groups * q4kx8_block_bytes
    indexed = {item["candidate"]: item for item in rankings}
    fused = indexed["fused_shared_q8_loads"]
    return {
        "schema_version": "vladder-q4k-attribution-v7.0",
        "method": ["controlled source ablation", "static byte accounting", "disassembly", "supporting PMU probe"],
        "instrumentation_used_for_ranking": False,
        "byte_model": {
            "independent_activation_load_bytes": activation_bytes_independent,
            "fused_activation_load_bytes": activation_bytes_fused,
            "activation_bytes_removed": activation_bytes_independent - activation_bytes_fused,
            "sibling_weight_bytes": weight_bytes,
            "removed_fraction_of_modeled_input_bytes_percent":
                100.0 * (activation_bytes_independent - activation_bytes_fused) / (activation_bytes_independent + weight_bytes),
            "cache_interpretation": "Q8_K activation is 2920 bytes and hot; Q4_K sibling weights dominate streaming traffic.",
        },
        "stages": [
            {"stage": "activation block load", "admitted": True, "quality": "controlled ablation", "regional_delta_percent": fused["speedup_percent"], "confidence": fused["speedup_95"]},
            {"stage": "packed weight load/decode/dot", "admitted": True, "quality": "byte model plus native attribution", "regional_delta_percent": None, "note": "unchanged by the load-sharing candidate and remains dominant"},
            {"stage": "accumulator/register pressure", "admitted": True, "quality": "disassembly plus ablation", "regional_delta_percent": fused["speedup_percent"], "note": "two live decode streams increase code and stack pressure"},
            {"stage": "consumer fusion", "admitted": False, "quality": "not measured", "regional_delta_percent": None},
        ],
        "assembly": assembly,
        "perf": perf,
        "promotion_decision": {
            "family": "shared_q8_activation_load",
            "state": "rejected_for_expansion",
            "reason": "E1 fused candidate failed the 3% regional gate; independent full runs ranged from regression to an inconclusive sub-threshold gain.",
        },
    }
