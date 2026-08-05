from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import yaml

from .deep_grammar import DeepDerivation
from .deep_ir import DeepKernelContract
from .deep_lowering import (
    DeepCandidate,
    emit_c_candidate,
    emit_cpp_candidate,
    emit_julia_candidate,
    emit_rust_candidate,
    emit_zig_candidate,
)
from .paired_benchmark import run_paired_benchmark


C_HARNESS = r"""
typedef size_t (*kernel_fn)(const uint8_t *, size_t, uint8_t);

static uint64_t rng_state = UINT64_C(0x9e3779b97f4a7c15);
static uint64_t next_u64(void) {
    uint64_t x = rng_state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    rng_state = x;
    return x * UINT64_C(2685821657736338717);
}

static void fill(uint8_t *data, size_t n, uint64_t seed) {
    rng_state = seed;
    for (size_t i = 0; i < n; ++i) data[i] = (uint8_t)next_u64();
}

static int verify(void) {
    uint8_t data[521];
    const uint8_t needles[] = {0, 1, 17, 127, 128, 254, 255};
    for (unsigned value = 0; value < 256; ++value) {
        data[0] = (uint8_t)value;
        for (unsigned needle = 0; needle < 256; ++needle) {
            size_t a = deep_baseline(data, 1, (uint8_t)needle);
            size_t b = deep_candidate(data, 1, (uint8_t)needle);
            if (a != b) return 10;
        }
    }
    for (size_t n = 0; n <= 520; ++n) {
        fill(data, n, UINT64_C(0x123456789abcdef0) ^ n);
        for (size_t k = 0; k < sizeof(needles); ++k) {
            size_t a = deep_baseline(data, n, needles[k]);
            size_t b = deep_candidate(data, n, needles[k]);
            if (a != b) return 20;
        }
    }
    return 0;
}

static double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (double)ts.tv_sec * 1000000000.0 + (double)ts.tv_nsec;
}

int main(int argc, char **argv) {
    int rc = verify();
    if (rc) return rc;
    const int candidate = argc > 1 && strcmp(argv[1], "candidate") == 0;
    const size_t n = argc > 2 ? (size_t)strtoull(argv[2], 0, 10) : (1u << 20);
    const int inner = argc > 3 ? atoi(argv[3]) : 128;
    uint8_t *data = (uint8_t *)aligned_alloc(64, (n + 64 + 63) & ~(size_t)63);
    if (!data) return 30;
    fill(data, n, UINT64_C(0x5a17d33d));
    kernel_fn fn = candidate ? deep_candidate : deep_baseline;
    volatile size_t guard = 0;
    for (int warm = 0; warm < 8; ++warm) guard += fn(data, n, (uint8_t)(17 + warm));
    double begin = now_ns();
    for (int i = 0; i < inner; ++i) guard += fn(data, n, (uint8_t)(17 + (i & 15)));
    double elapsed = now_ns() - begin;
    size_t observable = fn(data, n, UINT8_C(17));
    printf("{\"ns_per_call\":%.9f,\"observable\":\"%zu\",\"guard\":\"%zu\"}\n", elapsed / (double)inner, observable, (size_t)guard);
    free(data);
    return 0;
}
"""


RUST_HARNESS = r"""
fn fill(data: &mut [u8], mut state: u64) {
    for value in data {
        state ^= state >> 12;
        state ^= state << 25;
        state ^= state >> 27;
        state = state.wrapping_mul(2_685_821_657_736_338_717u64);
        *value = state as u8;
    }
}

fn verify() {
    let mut data = vec![0u8; 521];
    for value in 0u16..=255 {
        data[0] = value as u8;
        for needle in 0u16..=255 {
            assert_eq!(deep_baseline(&data[..1], needle as u8), deep_candidate(&data[..1], needle as u8));
        }
    }
    for n in 0usize..=520 {
        fill(&mut data[..n], 0x1234_5678_9abc_def0u64 ^ n as u64);
        for &needle in &[0u8, 1, 17, 127, 128, 254, 255] {
            assert_eq!(deep_baseline(&data[..n], needle), deep_candidate(&data[..n], needle));
        }
    }
}

fn main() {
    verify();
    let args: Vec<String> = std::env::args().collect();
    let candidate = args.get(1).map(String::as_str) == Some("candidate");
    let n = args.get(2).and_then(|value| value.parse().ok()).unwrap_or(1usize << 20);
    let inner = args.get(3).and_then(|value| value.parse().ok()).unwrap_or(128usize);
    let mut data = vec![0u8; n];
    fill(&mut data, 0x5a17_d33du64);
    let function: fn(&[u8], u8) -> usize = if candidate { deep_candidate } else { deep_baseline };
    let mut guard = 0usize;
    for warm in 0..8 { guard = guard.wrapping_add(function(&data, (17 + warm) as u8)); }
    let begin = std::time::Instant::now();
    for index in 0..inner { guard = guard.wrapping_add(function(&data, (17 + (index & 15)) as u8)); }
    let elapsed = begin.elapsed().as_nanos() as f64;
    let observable = function(&data, 17);
    println!("{{\"ns_per_call\":{:.9},\"observable\":\"{}\",\"guard\":\"{}\"}}", elapsed / inner as f64, observable, guard);
}
"""


JULIA_HARNESS = r"""
function vladder_fill!(data::Vector{UInt8}, state::UInt64)
    @inbounds for index in eachindex(data)
        state = xor(state, state >> 12)
        state = xor(state, state << 25)
        state = xor(state, state >> 27)
        state *= UInt64(2685821657736338717)
        data[index] = UInt8(state & 0xff)
    end
end

function vladder_verify()
    data = zeros(UInt8, 521)
    for value in 0:255
        data[1] = UInt8(value)
        single = data[1:1]
        for needle in 0:255
            deep_baseline(single, UInt8(needle)) == deep_candidate(single, UInt8(needle)) || exit(10)
        end
    end
    needles = UInt8[0, 1, 17, 127, 128, 254, 255]
    for n in 0:520
        slice = zeros(UInt8, n)
        vladder_fill!(slice, xor(UInt64(0x123456789abcdef0), UInt64(n)))
        for needle in needles
            deep_baseline(slice, needle) == deep_candidate(slice, needle) || exit(20)
        end
    end
end

function vladder_main()
    get(ENV, "VLADDER_SKIP_EXHAUSTIVE_VERIFY", "0") == "1" || vladder_verify()
    candidate_mode = length(ARGS) >= 1 && ARGS[1] == "candidate"
    n = length(ARGS) >= 2 ? parse(Int, ARGS[2]) : 1 << 20
    inner = length(ARGS) >= 3 ? parse(Int, ARGS[3]) : 128
    data = zeros(UInt8, n)
    vladder_fill!(data, UInt64(0x5a17d33d))
    fn = candidate_mode ? deep_candidate : deep_baseline
    guard = 0
    for warm in 0:7
        guard += fn(data, UInt8(17 + warm))
    end
    begin_ns = time_ns()
    for index in 0:(inner - 1)
        guard += fn(data, UInt8(17 + (index & 15)))
    end
    elapsed = time_ns() - begin_ns
    observable = fn(data, UInt8(17))
    println("{\"ns_per_call\":", Float64(elapsed) / inner, ",\"observable\":\"", observable, "\",\"guard\":\"", guard, "\"}")
end

vladder_main()
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _function_symbol_matches(symbol: str, function: str) -> bool:
    """Match native and JIT symbol spellings without accepting unrelated suffixes."""
    normalized = symbol.strip('"')
    return bool(re.search(
        rf"(?:^|[.$_]){re.escape(function)}(?:$|[.$_]\d+$)",
        normalized,
    )) and not normalized.endswith(("_scalar", "_avx2"))


def _normalized_identity(
    lines: list[str], function: str, source: str, symbol: str | None,
) -> dict[str, Any]:
    encoded = "\n".join(lines).encode()
    instruction_lines = sum(line != "FUNCTION" and not line.startswith(("define ", "}")) for line in lines)
    if instruction_lines == 0:
        return {
            "schema_version": "vladder-hot-code-identity-v2",
            "status": "unresolved",
            "function": function,
            "source": source,
            "resolved_symbol": symbol,
            "normalized_sha256": None,
            "normalized_instruction_lines": 0,
            "mnemonics": {},
            "reason": "no hot instructions or LLVM operations were resolved for the requested function",
        }
    mnemonics: dict[str, int] = {}
    for line in lines:
        if line == "FUNCTION" or line.startswith(("define ", "}")):
            continue
        mnemonic = line.split(None, 1)[0]
        mnemonics[mnemonic] = mnemonics.get(mnemonic, 0) + 1
    return {
        "schema_version": "vladder-hot-code-identity-v2",
        "status": "resolved",
        "function": function,
        "source": source,
        "resolved_symbol": symbol,
        "normalized_sha256": hashlib.sha256(encoded).hexdigest(),
        "normalized_instruction_lines": instruction_lines,
        "mnemonics": dict(sorted(mnemonics.items())),
        "normalization": "comments, assembler directives, local labels, and generated function symbols removed",
    }


def _hot_llvm_identity(path: Path, function: str) -> dict[str, Any]:
    text = path.read_text(errors="replace")
    alias_target: str | None = None
    alias = re.search(
        rf'^@(?:"?{re.escape(function)}"?)\s*=\s*alias\b[^\n]*\bptr\s+@(?:"([^"]+)"|([^,\s]+))',
        text,
        flags=re.MULTILINE,
    )
    if alias:
        alias_target = alias.group(1) or alias.group(2)
    selected: list[str] = []
    active = False
    depth = 0
    symbol: str | None = None
    for raw in text.splitlines():
        definition = re.match(r'^define\b.*@(?:"([^"]+)"|([^ (]+))\(', raw)
        if definition:
            candidate = definition.group(1) or definition.group(2)
            active = _function_symbol_matches(candidate, function) or candidate == alias_target
            depth = raw.count("{") - raw.count("}")
            if active:
                symbol = candidate
                selected.append("define FUNCTION")
            continue
        if not active:
            continue
        depth += raw.count("{") - raw.count("}")
        line = raw.split(";", 1)[0].strip()
        if line and not line.endswith(":") and not line.startswith("!"):
            line = re.sub(r"%[A-Za-z0-9_.-]+", "%v", line)
            line = re.sub(r"!\d+", "!n", line)
            selected.append(line)
        if depth <= 0:
            active = False
            break
    return _normalized_identity(selected, function, "llvm_ir", symbol)


def _hot_assembly_identity(
    path: Path, function: str, llvm_path: Path | None = None,
) -> dict[str, Any]:
    """Fingerprint a resolved hot body; an empty selection is never an identity."""
    selected: list[str] = []
    active = False
    symbol: str | None = None
    for raw in path.read_text(errors="replace").splitlines():
        label = re.match(r'^\s*(?:"([^"]+)"|([A-Za-z_.$][A-Za-z0-9_.$]*)):\s*(?:[#;].*)?$', raw)
        candidate_symbol = (label.group(1) or label.group(2)) if label else None
        if candidate_symbol is not None and not candidate_symbol.startswith(".L"):
            active = _function_symbol_matches(candidate_symbol, function)
            if active:
                symbol = candidate_symbol
                selected.append("FUNCTION")
            continue
        if not active:
            continue
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("."):
            continue
        line = re.sub(r"\.L(?:BB|tmp|CPI|JTI)[A-Za-z0-9_.$-]*", ".L", line)
        line = re.sub(rf"\b(?:{re.escape(function)}(?:_avx2|_scalar)?)\b", "FUNCTION", line)
        selected.append(line)
    identity = _normalized_identity(selected, function, "assembly", symbol)
    if identity["status"] == "unresolved" and llvm_path is not None and llvm_path.exists():
        return _hot_llvm_identity(llvm_path, function)
    return identity


def _physical_search_complete(
    rows: list[dict[str, Any]], assembly_identity_count: int, measured_count: int,
) -> bool:
    """Return true only when every proved terminal has resolved physical coverage."""
    return (
        bool(rows)
        and all(row.get("physical_identity_status") == "resolved" for row in rows)
        and measured_count == assembly_identity_count
        and all(
            row["classification"]
            not in {"verification_failed", "compile_failed", "benchmark_failed"}
            for row in rows
        )
    )


def compile_deep_harness(
    contract: DeepKernelContract,
    candidate: DeepCandidate,
    output_directory: Path,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    if candidate.language in {"c", "cpp"}:
        cpp = candidate.language == "cpp"
        compiler = (shutil.which("clang++-20") or shutil.which("clang++")) if cpp else (shutil.which("clang-20") or shutil.which("clang"))
        if not compiler:
            return {"status": "unavailable", "reason": f"{'clang++' if cpp else 'clang'} not found"}
        source = output_directory / ("paired.cpp" if cpp else "paired.c")
        binary = output_directory / "paired"
        assembly = output_directory / "paired.s"
        llvm = output_directory / "paired.ll"
        baseline = (emit_cpp_candidate if cpp else emit_c_candidate)(contract, "scalar", "deep_baseline")
        feature_prefix = "" if cpp else "#define _GNU_SOURCE\n"
        text = feature_prefix + "#include <immintrin.h>\n#include <stdint.h>\n#include <stddef.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <time.h>\n\n" + baseline + "\n" + candidate.source + "\n" + C_HARNESS
        source.write_text(text)
        standard = "-std=c++20" if cpp else "-std=c17"
        command = [compiler, standard, "-O3", "-march=native", str(source), "-o", str(binary)]
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode == 0:
            subprocess.run([compiler, standard, "-O3", "-march=native", "-S", str(source), "-o", str(assembly)], check=True)
            subprocess.run([compiler, standard, "-O3", "-march=native", "-S", "-emit-llvm", str(source), "-o", str(llvm)], check=True)
    elif candidate.language == "rust":
        compiler = shutil.which("rustc")
        if not compiler:
            return {"status": "unavailable", "reason": "rustc not found"}
        source = output_directory / "paired.rs"
        binary = output_directory / "paired"
        assembly = output_directory / "paired.s"
        llvm = output_directory / "paired.ll"
        baseline = emit_rust_candidate(contract, "scalar", "deep_baseline")
        source.write_text(baseline + "\n" + candidate.source + "\n" + RUST_HARNESS)
        command = [compiler, "--edition", "2021", "-C", "opt-level=3", "-C", "target-cpu=native", str(source), "-o", str(binary)]
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode == 0:
            subprocess.run([compiler, "--edition", "2021", "-C", "opt-level=3", "-C", "target-cpu=native", "--emit", f"asm={assembly}", str(source)], check=True)
            subprocess.run([compiler, "--edition", "2021", "-C", "opt-level=3", "-C", "target-cpu=native", "--emit", f"llvm-ir={llvm}", str(source)], check=True)
    elif candidate.language == "zig":
        compiler = shutil.which("zig")
        linker = shutil.which("clang-20") or shutil.which("clang")
        if not compiler or not linker:
            return {"status": "unavailable", "reason": "zig and clang are required"}
        source = output_directory / "paired.zig"
        harness = output_directory / "harness.c"
        obj = output_directory / "paired.o"
        binary = output_directory / "paired"
        assembly = output_directory / "paired.s"
        llvm = output_directory / "paired.ll"
        baseline = emit_zig_candidate(contract, "scalar", "deep_baseline")
        source.write_text(baseline + "\n" + candidate.source)
        harness.write_text("#define _GNU_SOURCE\n#include <stdint.h>\n#include <stddef.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <time.h>\n\nextern size_t deep_baseline(const uint8_t *, size_t, uint8_t);\nextern size_t deep_candidate(const uint8_t *, size_t, uint8_t);\n\n" + C_HARNESS)
        zig_command = [compiler, "build-obj", "-O", "ReleaseFast", "-mcpu", "native", f"-femit-bin={obj}", f"-femit-asm={assembly}", f"-femit-llvm-ir={llvm}", str(source)]
        generated = subprocess.run(zig_command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        command = [linker, "-std=c17", "-O3", "-march=native", str(harness), str(obj), "-o", str(binary)]
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) if generated.returncode == 0 else generated
        if generated.returncode != 0:
            command = zig_command
    elif candidate.language == "julia":
        compiler = shutil.which("julia")
        if not compiler:
            return {"status": "unavailable", "reason": "julia not found"}
        source = output_directory / "paired.jl"
        binary = output_directory / "paired"
        assembly = output_directory / "paired.s"
        llvm = output_directory / "paired.ll"
        baseline = emit_julia_candidate(contract, "scalar", "deep_baseline")
        definitions = baseline + "\n" + candidate.source
        source.write_text(definitions + "\n" + JULIA_HARNESS)
        binary.write_text(f'#!/bin/sh\nexec "{compiler}" --startup-file=no -O3 --check-bounds=no "{source}" "$@"\n')
        binary.chmod(0o755)
        capture = output_directory / "capture.jl"
        capture.write_text(
            definitions
            + "\nusing InteractiveUtils\n"
            + f'open(raw"{llvm}", "w") do io; code_llvm(io, deep_candidate, (Vector{{UInt8}}, UInt8); optimize=true); end\n'
            + f'open(raw"{assembly}", "w") do io; code_native(io, deep_candidate, (Vector{{UInt8}}, UInt8); syntax=:intel); end\n'
        )
        command = [compiler, "--startup-file=no", "-O3", "--check-bounds=no", str(source), "baseline", "521", "1"]
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode == 0:
            capture_result = subprocess.run([compiler, "--startup-file=no", "-O3", "--check-bounds=no", str(capture)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if capture_result.returncode != 0:
                completed = capture_result
    else:
        raise ValueError(f"unsupported benchmark language: {candidate.language}")
    report = {
        "status": "pass" if completed.returncode == 0 else "fail",
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "source": str(source),
        "binary": str(binary) if binary.exists() else None,
        "assembly": str(assembly) if assembly.exists() else None,
        "llvm_ir": str(llvm) if llvm.exists() else None,
        "hashes": {path.name: _sha256(path) for path in (source, binary, assembly, llvm) if path.exists()},
    }
    if assembly.exists():
        report["hot_assembly_identity"] = _hot_assembly_identity(
            assembly,
            candidate.function,
            llvm if llvm.exists() else None,
        )
    return report


def benchmark_deep_candidate(
    contract: DeepKernelContract,
    derivation: DeepDerivation,
    candidate: DeepCandidate,
    output_directory: Path,
    *,
    processes: int = 10,
    repetitions_per_process: int = 3,
    n: int = 1 << 20,
    inner: int = 128,
    cpu: int | None = None,
    minimum_effect_percent: float = 1.0,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    build = compile_deep_harness(contract, candidate, output_directory / "build")
    if build["status"] != "pass":
        report = {"schema_version": "vladder-deep-benchmark-v1", "status": "compile_failed", "build": build}
        (output_directory / "deep-benchmark.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report
    executable = Path(str(build["binary"]))
    verify = subprocess.run([str(executable), "baseline", "521", "1"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if verify.returncode != 0:
        report = {"schema_version": "vladder-deep-benchmark-v1", "status": "differential_failed", "build": build, "verification": {"return_code": verify.returncode, "stdout": verify.stdout, "stderr": verify.stderr}}
        (output_directory / "deep-benchmark.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report
    manifest = {
        "executable": str(executable),
        "baseline_args": ["baseline", str(n), str(inner)],
        "candidate_args": ["candidate", str(n), str(inner)],
        "processes": processes,
        "repetitions_per_process": repetitions_per_process,
        "metric_key": "ns_per_call",
        "observable_key": "observable",
        "exact_observables": True,
        "direction": "lower",
        "minimum_effect_percent": minimum_effect_percent,
        "bootstrap_rounds": 2000,
        "seed": 0xD33F,
        "cpu": cpu,
        "candidate_identity": candidate.id,
    }
    if candidate.language == "julia":
        # The exhaustive oracle has already run once above. Repeating it in every
        # short-lived Julia timing process distorts the sample and needlessly
        # recompiles the full verification loop.
        manifest["environment"] = {"VLADDER_SKIP_EXHAUSTIVE_VERIFY": "1"}
    manifest_path = output_directory / "paired.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True))
    paired = run_paired_benchmark(manifest_path, output_directory / "paired")
    report = {
        "schema_version": "vladder-deep-benchmark-v1",
        "status": "pass" if paired["semantic_parity"] == "PASS" else "verification_failed",
        "candidate": candidate.to_dict(),
        "derivation_hash": derivation.derivation_hash,
        "build": build,
        "differential": {"status": "PASS", "exhaustive_single_byte_pairs": 65536, "boundary_lengths": 521},
        "paired": paired,
    }
    (output_directory / "deep-benchmark.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def rank_deep_grammar(
    contract: DeepKernelContract,
    grammar: Any,
    language: str,
    output_directory: Path,
    *,
    processes: int = 10,
    repetitions_per_process: int = 3,
    n: int = 1 << 20,
    inner: int = 128,
    cpu: int | None = None,
    minimum_effect_percent: float = 1.0,
) -> dict[str, Any]:
    """Prove, assembly-deduplicate, and physically rank every reachable terminal realization."""
    from .deep_grammar import search_deep_grammar
    from .deep_lowering import emit_deep_candidate
    from .deep_proof import prove_deep_candidate

    output_directory.mkdir(parents=True, exist_ok=True)
    search = search_deep_grammar(contract, grammar)
    rows: list[dict[str, Any]] = []
    assembly_owners: dict[str, str] = {}
    for derivation in search.derivations:
        case_directory = output_directory / derivation.target
        candidate = emit_deep_candidate(contract, derivation, language, "deep_candidate", grammar)
        proof = prove_deep_candidate(contract, derivation, candidate, case_directory / "proofs")
        row: dict[str, Any] = {
            "realization": derivation.target,
            "candidate_id": candidate.id,
            "derivation_hash": derivation.derivation_hash,
            "proof_status": proof["status"],
            "classification": "verification_failed" if proof["status"] != "PASS" else "proof_complete",
        }
        if proof["status"] == "PASS":
            build = compile_deep_harness(contract, candidate, case_directory / "screening-build")
            row["build"] = build
            physical_identity = build.get("hot_assembly_identity") or {}
            identity = physical_identity.get("normalized_sha256") if physical_identity.get("status") == "resolved" else None
            row["physical_identity_status"] = physical_identity.get("status", "unresolved")
            if identity and identity in assembly_owners:
                row["classification"] = "assembly_duplicate"
                row["assembly_duplicate_of"] = assembly_owners[identity]
            elif build.get("status") == "pass":
                if identity:
                    assembly_owners[identity] = derivation.target
                benchmark = benchmark_deep_candidate(
                    contract,
                    derivation,
                    candidate,
                    case_directory / "benchmark",
                    processes=processes,
                    repetitions_per_process=repetitions_per_process,
                    n=n,
                    inner=inner,
                    cpu=cpu,
                    minimum_effect_percent=minimum_effect_percent,
                )
                paired = benchmark.get("paired") or {}
                row["benchmark"] = benchmark
                row["effect_percent"] = paired.get("paired_effect_percent")
                row["confidence_95"] = paired.get("paired_effect_95_percent")
                row["classification"] = paired.get("classification", "benchmark_failed")
            else:
                row["classification"] = "compile_failed"
        rows.append(row)
    measured = [row for row in rows if isinstance(row.get("effect_percent"), (int, float))]
    winner = max(measured, key=lambda row: float(row["effect_percent"])) if measured else None
    identities_resolved = bool(rows) and all(row.get("physical_identity_status") == "resolved" for row in rows)
    all_closed = _physical_search_complete(rows, len(assembly_owners), len(measured))
    report = {
        "schema_version": "vladder-deep-ranking-v1",
        "status": "pass" if all_closed else "incomplete",
        "grammar_version": grammar.version,
        "grammar_hash": grammar.hash,
        "language": language,
        "contract": contract.to_dict(),
        "search": search.to_dict(),
        "classification": "bounded_optimal_local" if search.saturated and all_closed else "best_verified_found",
        "assembly_identity_count": len(assembly_owners),
        "physical_identity_complete": identities_resolved,
        "candidate_count": len(rows),
        "measured_candidate_count": len(measured),
        "winner": {
            "realization": winner["realization"],
            "effect_percent": winner["effect_percent"],
            "confidence_95": winner["confidence_95"],
            "classification": winner["classification"],
        } if winner else None,
        "candidates": rows,
    }
    (output_directory / "deep-ranking.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
