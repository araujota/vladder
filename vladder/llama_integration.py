from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any

from .report import write_json
from .statistics_v3 import summarize_samples
from .toolchain import run
from .toolchain import discover_toolchain
from .hardware_manifest import capture_manifest, write_manifest
from .ggml_graph import normalize_ggml_dot, write_normalized_ggml_graph
from .ggml_profile import parse_ggml_profile
from .projection_profile import parse_projection_profile


PINNED_LLAMA_COMMIT = "a7a6d0d269c896218b6c78e0933bd6a17519d3f6"


def benchmark_llama_integration(root: Path, out_dir: Path, cpu: int, processes: int, samples: int, dimension: int) -> dict[str, Any]:
    root = root.resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    hardware = capture_manifest("local-7950x3d", cpu, discover_toolchain())
    write_manifest(out_dir / "hardware_manifest.json", hardware)
    commit = run(["git", "rev-parse", "HEAD"], timeout=20, cwd=root).stdout.strip()
    if commit != PINNED_LLAMA_COMMIT:
        raise ValueError(f"llama.cpp commit mismatch: expected {PINNED_LLAMA_COMMIT}, got {commit}")
    build = root / "build-vladder"
    built = run(["cmake", "--build", str(build), "--target", "ggml-cpu", "-j4"], timeout=600, cwd=root)
    if built.returncode:
        raise RuntimeError((built.stdout + built.stderr)[-4000:])
    benchmark_source = root.parent.parent / "examples/operators/llama_add_rms_mul_bench.cpp"
    binary = build / "bin/vladder-rms-bench"
    compile_result = run([
        "clang++-20", "-std=c++20", "-O3", "-march=native", f"-I{root/'ggml/include'}", f"-I{root/'ggml/src'}",
        str(benchmark_source), f"-L{build/'bin'}", f"-Wl,-rpath,{build/'bin'}", "-lggml-cpu", "-lggml-base", "-lggml", "-pthread", "-lm", "-o", str(binary),
    ], timeout=180, cwd=root)
    if compile_result.returncode:
        raise RuntimeError((compile_result.stdout + compile_result.stderr)[-4000:])
    labels = ["pinned_llama_baseline", "vladder_add_rms_mul_fused"]
    order = labels * processes
    random.Random(707).shuffle(order)
    blocks = {label: [] for label in labels}; checksums = {label: [] for label in labels}; output_hashes = {label: [] for label in labels}
    env_base = {"LD_LIBRARY_PATH": str(build / "bin")}
    for label in order:
        env = dict(env_base)
        if label == "pinned_llama_baseline": env["VLADDER_DISABLE_ADD_RMS_MUL_FUSION"] = "1"
        result = run(["taskset", "-c", str(cpu), str(binary), str(dimension), str(samples)], timeout=600, cwd=root, env=env)
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[-4000:])
        payload = json.loads(result.stdout.splitlines()[-1])
        blocks[label].append([float(value) for value in payload["cycles"]])
        checksums[label].append(float(payload["checksum"]))
        output_hashes[label].append(str(payload["output_hash"]))
    if any(value != checksums[labels[0]][0] for values in checksums.values() for value in values) or any(value != output_hashes[labels[0]][0] for values in output_hashes.values() for value in values):
        raise RuntimeError("llama.cpp fused and unfused graph outputs differ")
    stats = {label: summarize_samples(values, bootstrap_rounds=600, seed=707) for label, values in blocks.items()}
    baseline, candidate = stats[labels[0]], stats[labels[1]]
    speedup = (baseline["p50"] / candidate["p50"] - 1.0) * 100.0
    source_patch = run(["git", "diff", "--", "ggml/src/ggml-cpu/ops.cpp", "ggml/src/ggml-cpu/ops.h", "ggml/src/ggml-cpu/ggml-cpu.c"], timeout=30, cwd=root).stdout
    (out_dir / "llama-integration.patch").write_text(source_patch)
    post_hardware = capture_manifest("local-7950x3d", cpu, discover_toolchain())
    write_manifest(out_dir / "hardware_manifest.post.json", post_hardware)
    if hardware.manifest_hash != post_hardware.manifest_hash:
        raise RuntimeError("material hardware/software configuration changed during llama.cpp benchmark")
    manifest = {
        "schema_version": "vladder-llama-integration-v3.0", "llama_commit": commit,
        "build_directory": str(build), "compiler": "clang++-20", "flags": ["-O3", "-march=native"],
        "hardware_manifest_hash": hardware.manifest_hash, "post_hardware_manifest_hash": post_hardware.manifest_hash,
        "kernel_sources": ["ggml/src/ggml-cpu/ops.cpp:3794", "ggml/src/ggml-cpu/ggml-cpu.c:3026"],
        "graph": ["GGML_OP_ADD", "GGML_OP_RMS_NORM", "GGML_OP_MUL"],
        "dimension": dimension, "cpu": cpu, "processes": processes, "samples_per_process": samples,
        "randomized_order": order, "verification": {"status": "PASS", "class": "bitwise_output_tensor", "checksum": checksums[labels[0]][0], "output_hash": output_hashes[labels[0]][0]},
        "latency_cycles": stats, "p50_speedup_pct": speedup,
        "materialization_change": "ADD and RMS_NORM intermediates are no longer written/read when ggml_can_fuse proves the three-node region private",
        "claim": "Best measured implementation among the fused and unfused pinned llama.cpp graph variants on this target; no global optimality claim.",
    }
    write_json(out_dir / "llama-integration-report.json", manifest)
    return manifest


def benchmark_llama_model(
    root: Path,
    model: Path,
    out_dir: Path,
    cpu_list: str,
    threads: int,
    processes: int,
    repetitions: int,
    prompt_tokens: int,
    generation_tokens: int,
) -> dict[str, Any]:
    root = root.resolve()
    model = model.resolve()
    out_dir = out_dir.resolve()
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if not model.is_file():
        raise FileNotFoundError(model)
    commit = run(["git", "rev-parse", "HEAD"], timeout=20, cwd=root).stdout.strip()
    if commit != PINNED_LLAMA_COMMIT:
        raise ValueError(f"llama.cpp commit mismatch: expected {PINNED_LLAMA_COMMIT}, got {commit}")
    build = root / "build-vladder-cli"
    built = run(["cmake", "--build", str(build), "--target", "llama-bench", "llama-completion", "-j4"], timeout=900, cwd=root)
    if built.returncode:
        raise RuntimeError((built.stdout + built.stderr)[-4000:])
    bench = build / "bin/llama-bench"
    completion = build / "bin/llama-completion"
    first_cpu = int(cpu_list.split(",", 1)[0].split("-", 1)[0])
    hardware = capture_manifest("local-7950x3d-qwen3-4b", first_cpu, discover_toolchain())
    write_manifest(out_dir / "hardware_manifest.json", hardware)
    model_sha256 = _sha256(model)

    base_command = [
        "taskset", "-c", cpu_list, str(bench), "-m", str(model),
        "-p", str(prompt_tokens), "-n", str(generation_tokens), "-r", str(repetitions),
        "-t", str(threads), "-ngl", "0", "-o", "json",
    ]
    probe_command = [
        "taskset", "-c", cpu_list, str(bench), "-m", str(model),
        "-p", "16", "-n", "1", "-r", "1", "-t", str(threads), "-ngl", "0", "-o", "json",
    ]
    probe = run(probe_command, timeout=600, cwd=root, env={"VLADDER_REPORT_ADD_RMS_MUL_FUSION": "1"})
    if probe.returncode or "matched ADD -> RMS_NORM -> MUL fusion" not in probe.stderr:
        raise RuntimeError("Qwen3 graph did not exercise the vLadder ADD/RMSNorm/MUL fusion")

    labels = ["pinned_llama_baseline", "vladder_add_rms_mul_fused"]
    order = labels * processes
    random.Random(3404).shuffle(order)
    samples_ns: dict[str, dict[str, list[list[float]]]] = {
        label: {"prompt": [], "decode": []} for label in labels
    }
    samples_ts: dict[str, dict[str, list[list[float]]]] = {
        label: {"prompt": [], "decode": []} for label in labels
    }
    metadata: dict[str, Any] | None = None
    counters = {label: 0 for label in labels}
    for label in order:
        index = counters[label]
        counters[label] += 1
        raw_path = raw_dir / f"{label}-{index:02d}.json"
        env = {"VLADDER_DISABLE_ADD_RMS_MUL_FUSION": "1"} if label == labels[0] else {}
        if raw_path.exists():
            payload = json.loads(raw_path.read_text())
        else:
            result = run(base_command, timeout=1200, cwd=root, env=env)
            if result.returncode:
                raise RuntimeError((result.stdout + result.stderr)[-4000:])
            payload = json.loads(result.stdout)
            write_json(raw_path, payload)
        if len(payload) != 2:
            raise RuntimeError(f"expected prompt and decode records, got {len(payload)}")
        record_by_kind = {"prompt" if row["n_prompt"] else "decode": row for row in payload}
        for kind, row in record_by_kind.items():
            samples_ns[label][kind].append([float(value) for value in row["samples_ns"]])
            samples_ts[label][kind].append([float(value) for value in row["samples_ts"]])
        metadata = payload[0]

    stats: dict[str, dict[str, Any]] = {}
    for label in labels:
        stats[label] = {}
        for kind in ("prompt", "decode"):
            latency = summarize_samples(samples_ns[label][kind], bootstrap_rounds=1000, seed=3404)
            throughput = summarize_samples(samples_ts[label][kind], bootstrap_rounds=1000, seed=3404)
            stats[label][kind] = {"latency_ns": latency, "tokens_per_second": throughput}
    deltas: dict[str, Any] = {}
    for kind in ("prompt", "decode"):
        baseline = stats[labels[0]][kind]["latency_ns"]
        optimized = stats[labels[1]][kind]["latency_ns"]
        point = (baseline["p50"] / optimized["p50"] - 1.0) * 100.0
        bounds = [
            (baseline["bootstrap_95"]["p50"][0] / optimized["bootstrap_95"]["p50"][1] - 1.0) * 100.0,
            (baseline["bootstrap_95"]["p50"][1] / optimized["bootstrap_95"]["p50"][0] - 1.0) * 100.0,
        ]
        classification = "improvement" if bounds[0] > 0.0 else ("regression" if bounds[1] < 0.0 else "statistical_tie")
        deltas[kind] = {"p50_speedup_pct": point, "p50_speedup_95": bounds, "classification": classification}

    generated = {}
    for label in labels:
        env = {"VLADDER_DISABLE_ADD_RMS_MUL_FUSION": "1"} if label == labels[0] else {}
        command = [
            "taskset", "-c", cpu_list, str(completion), "-m", str(model),
            "-p", "The capital of France is", "-n", "16", "-t", str(threads),
            "-ngl", "0", "-s", "42", "--temp", "0", "-no-cnv", "--no-warmup",
        ]
        result = run(command, timeout=600, cwd=root, env=env)
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[-4000:])
        generated[label] = result.stdout
    if not generated[labels[0]] or generated[labels[0]] != generated[labels[1]]:
        raise RuntimeError("fixed-seed greedy model outputs differ")

    post_hardware = capture_manifest("local-7950x3d-qwen3-4b", first_cpu, discover_toolchain())
    write_manifest(out_dir / "hardware_manifest.post.json", post_hardware)
    if hardware.manifest_hash != post_hardware.manifest_hash:
        raise RuntimeError("material hardware/software configuration changed during model benchmark")

    report = {
        "schema_version": "vladder-llama-model-v3.0",
        "llama_commit": commit,
        "model": {
            "path": str(model), "sha256": model_sha256, "bytes": model.stat().st_size,
            "type": metadata.get("model_type") if metadata else None,
            "parameters": metadata.get("model_n_params") if metadata else None,
        },
        "execution": {
            "backend": "CPU", "cpu_list": cpu_list, "threads": threads, "gpu_layers": 0,
            "processes_per_variant": processes, "repetitions_per_process": repetitions,
            "prompt_tokens": prompt_tokens, "generation_tokens": generation_tokens,
            "randomized_order": order, "hardware_manifest_hash": hardware.manifest_hash,
            "post_hardware_manifest_hash": post_hardware.manifest_hash,
        },
        "fusion_probe": "PASS",
        "verification": {
            "status": "PASS", "class": "fixed_seed_greedy_generated_text",
            "prompt": "The capital of France is", "seed": 42, "temperature": 0,
            "generated_text": generated[labels[0]].removeprefix("The capital of France is").strip(),
        },
        "measurements": stats,
        "deltas": deltas,
        "claim": "Best measured comparison of the pinned llama.cpp baseline and vLadder ADD/RMSNorm/MUL fusion for this model, target, and configuration; no global optimality claim.",
    }
    write_json(out_dir / "qwen3-4b-model-report.json", report)
    return report


def extract_llama_decode_graph(root: Path, model: Path, out_dir: Path, cpu_list: str, threads: int) -> dict[str, Any]:
    root = root.resolve(); model = model.resolve(); out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    commit = run(["git", "rev-parse", "HEAD"], timeout=20, cwd=root).stdout.strip()
    if commit != PINNED_LLAMA_COMMIT:
        raise ValueError(f"llama.cpp commit mismatch: expected {PINNED_LLAMA_COMMIT}, got {commit}")
    build = root / "build-vladder-cli"
    built = run(["cmake", "--build", str(build), "--target", "llama-bench", "-j4"], timeout=900, cwd=root)
    if built.returncode:
        raise RuntimeError((built.stdout + built.stderr)[-4000:])
    raw_dot = out_dir / "decode.raw.dot"
    command = [
        "taskset", "-c", cpu_list, str(build / "bin/llama-bench"), "-m", str(model),
        "-p", "0", "-n", "1", "-r", "1", "-t", str(threads), "-ngl", "0", "-o", "json",
    ]
    result = run(command, timeout=900, cwd=root, env={"VLADDER_DUMP_GRAPH": str(raw_dot)})
    if result.returncode or not raw_dot.is_file():
        raise RuntimeError((result.stdout + result.stderr)[-4000:] or "llama.cpp emitted no graph dump")
    provenance = {
        "llama_commit": commit, "model_path": str(model), "model_sha256": _sha256(model),
        "model_bytes": model.stat().st_size, "phase": "decode", "batch": 1,
        "cpu_list": cpu_list, "threads": threads, "gpu_layers": 0,
        "raw_dot_sha256": _sha256(raw_dot), "extraction_hook": "VLADDER_DUMP_GRAPH",
    }
    graph = normalize_ggml_dot(raw_dot, provenance)
    write_normalized_ggml_graph(out_dir / "decode.normalized.json", graph)
    report = {
        "schema_version": "vladder-llama-graph-extraction-v4.0",
        "graph_hash": graph.graph_hash, "provenance": provenance, "annotations": graph.annotations,
        "claim": "Authoritative normalized graph emitted by the pinned llama.cpp model builder for one CPU decode token.",
    }
    write_json(out_dir / "extraction-report.json", report)
    return report


def profile_llama_decode_graph(root: Path, model: Path, normalized_graph: Path, out_dir: Path, cpu_list: str, threads: int, tokens: int, context_tokens: int = 0) -> dict[str, Any]:
    root = root.resolve(); model = model.resolve(); normalized_graph = normalized_graph.resolve(); out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    commit = run(["git", "rev-parse", "HEAD"], timeout=20, cwd=root).stdout.strip()
    if commit != PINNED_LLAMA_COMMIT:
        raise ValueError(f"llama.cpp commit mismatch: expected {PINNED_LLAMA_COMMIT}, got {commit}")
    graph = json.loads(normalized_graph.read_text())
    if graph.get("provenance", {}).get("model_sha256") != _sha256(model):
        raise ValueError("normalized graph and model SHA-256 differ")
    build = root / "build-vladder-cli"
    target = "llama-completion" if context_tokens > 0 else "llama-bench"
    built = run(["cmake", "--build", str(build), "--target", target, "-j4"], timeout=900, cwd=root)
    if built.returncode:
        raise RuntimeError((built.stdout + built.stderr)[-4000:])
    if context_tokens > 0:
        prompt = " token" * context_tokens
        command = [
            "taskset", "-c", cpu_list, str(build / "bin/llama-completion"), "-m", str(model),
            "-p", prompt, "-n", str(tokens + 1), "-t", str(threads), "-ngl", "0", "-s", "42",
            "--temp", "0", "-no-cnv", "--no-warmup", "--no-display-prompt",
        ]
    else:
        command = [
            "taskset", "-c", cpu_list, str(build / "bin/llama-bench"), "-m", str(model),
            "-p", "0", "-n", str(tokens), "-r", "1", "-t", str(threads), "-ngl", "0", "-o", "json",
        ]
    result = run(command, timeout=1800, cwd=root, env={"VLADDER_PROFILE_GRAPH": "1"})
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr)[-4000:])
    (out_dir / "profile.raw.log").write_text(result.stderr)
    profile = parse_ggml_profile(result.stderr, graph, expected_samples=tokens)
    prompt_match = re.search(r"prompt eval time\s*=.*?/\s*(\d+) tokens", result.stderr)
    profile["provenance"] = {
        "llama_commit": commit, "model_sha256": graph["provenance"]["model_sha256"],
        "normalized_graph_hash": graph["graph_hash"], "cpu_list": cpu_list, "threads": threads,
        "requested_decode_tokens": tokens, "requested_context_tokens": context_tokens,
        "actual_prompt_tokens": int(prompt_match.group(1)) if prompt_match else 0, "gpu_layers": 0,
    }
    write_json(out_dir / "profile-report.json", profile)
    return profile


def profile_llama_projection_path(root: Path, model: Path, out_dir: Path, cpu_list: str, threads: int, prompt_tokens: int, generation_tokens: int, microbatch: int) -> dict[str, Any]:
    root = root.resolve(); model = model.resolve(); out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    commit = run(["git", "rev-parse", "HEAD"], timeout=20, cwd=root).stdout.strip()
    if commit != PINNED_LLAMA_COMMIT:
        raise ValueError(f"llama.cpp commit mismatch: expected {PINNED_LLAMA_COMMIT}, got {commit}")
    build = root / "build-vladder-cli"
    built = run(["cmake", "--build", str(build), "--target", "llama-bench", "-j4"], timeout=900, cwd=root)
    if built.returncode:
        raise RuntimeError((built.stdout + built.stderr)[-4000:])
    command = [
        "taskset", "-c", cpu_list, str(build / "bin/llama-bench"), "-m", str(model),
        "-p", str(prompt_tokens), "-n", str(generation_tokens), "-r", "1", "-t", str(threads),
        "-b", str(max(microbatch, prompt_tokens)), "-ub", str(microbatch), "-ngl", "0", "-o", "json", "--no-warmup",
    ]
    result = run(command, timeout=1800, cwd=root, env={"VLADDER_PROFILE_PROJECTION": "1"})
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr)[-4000:])
    (out_dir / "projection-profile.raw.log").write_text(result.stderr)
    profile = parse_projection_profile(result.stderr)
    profile["provenance"] = {
        "llama_commit": commit, "model_path": str(model), "model_sha256": _sha256(model),
        "model_bytes": model.stat().st_size, "cpu_list": cpu_list, "threads": threads,
        "prompt_tokens": prompt_tokens, "generation_tokens": generation_tokens,
        "microbatch": microbatch, "gpu_layers": 0, "instrumentation_env": "VLADDER_PROFILE_PROJECTION=1",
    }
    write_json(out_dir / "projection-profile.json", profile)
    return profile


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract_completion(log: str) -> str:
    match = re.search(r"I generate:.*?\n(?P<text>.*?)\n\d+\.\d+\.\d+ I common_perf_print:", log, re.DOTALL)
    if not match:
        return ""
    lines = []
    for line in match.group("text").splitlines():
        lines.append(re.sub(r"^\d+\.\d+\.\d+(?: [A-Z](?= ))? ?", "", line))
    return "\n".join(lines).strip()
