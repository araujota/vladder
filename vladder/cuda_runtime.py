from __future__ import annotations

import hashlib
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import yaml

from .language_adapter import canonical_hash, file_sha256


CUDA_RUNNER_SCHEMA_VERSION = "vladder-cuda-runner-v1"
CUDA_ARTIFACT_SCHEMA_VERSION = "vladder-cuda-artifact-v1"

DEFAULT_NCU_METRICS = (
    "sm__warps_active.avg.pct_of_peak_sustained_active",
    "l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum",
    "l1tex__t_sectors_pipe_lsu_mem_global_op_st.sum",
    "lts__t_sector_hit_rate.pct",
    "smsp__inst_executed.sum",
    "smsp__warp_issue_stalled_long_scoreboard_per_warp_active.pct",
)


def _command(command: list[str], *, timeout: float = 180.0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"CUDA command failed: {' '.join(command)}\n{result.stderr[-4000:]}")
    return result


def cuda_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"CUDA tool is unavailable: {name}")
    return str(Path(path).resolve())


def _cache_root() -> Path:
    root = Path(os.environ.get("VLADDER_CACHE_DIR", Path.home() / ".cache" / "vladder")) / "cuda"
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_cuda_driver_runner() -> Path:
    source = Path(__file__).resolve().parent / "native" / "cuda_driver_runner.cpp"
    if not source.is_file():
        raise RuntimeError(f"bundled CUDA runner source is missing: {source}")
    nvcc = cuda_tool("nvcc")
    compiler = _command([nvcc, "--version"]).stdout
    identity = hashlib.sha256(
        (file_sha256(source) + "\n" + nvcc + "\n" + compiler).encode("utf-8")
    ).hexdigest()[:20]
    directory = _cache_root() / f"driver-runner-{identity}"
    binary = directory / "vladder-cuda-driver-runner"
    if binary.is_file() and os.access(binary, os.X_OK):
        return binary
    directory.mkdir(parents=True, exist_ok=True)
    command = [nvcc, "-std=c++17", "-O3", str(source), "-lcuda", "-o", str(binary)]
    _command(command)
    (directory / "build.json").write_text(json.dumps({
        "schema_version": CUDA_RUNNER_SCHEMA_VERSION,
        "source": str(source),
        "source_hash": file_sha256(source),
        "compiler": nvcc,
        "compiler_identity": compiler.strip(),
        "command": command,
        "binary": str(binary),
    }, indent=2, sort_keys=True) + "\n")
    return binary


def _json_result(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    for line in reversed(result.stdout.splitlines()):
        if line.lstrip().startswith("{"):
            payload = json.loads(line)
            if isinstance(payload, dict):
                return payload
    raise ValueError("CUDA runner emitted no JSON object")


def probe_cuda_device(device: int = 0) -> dict[str, Any]:
    runner = ensure_cuda_driver_runner()
    return _json_result(_command([str(runner), "--probe", "--device", str(device)]))


def inspect_cuda_module(
    module: Path,
    *,
    entry_point: str = "vladder_transform",
    device: int = 0,
) -> dict[str, Any]:
    module = module.resolve()
    if not module.is_file():
        raise ValueError(f"CUDA module is missing: {module}")
    runner = ensure_cuda_driver_runner()
    return _json_result(_command([
        str(runner), "--inspect-module",
        "--module", str(module),
        "--entry", entry_point,
        "--device", str(device),
    ]))


def compile_cuda_source(
    source: Path,
    output: Path,
    *,
    architecture: str | None = None,
    extra_flags: tuple[str, ...] = (),
) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    nvcc = cuda_tool("nvcc")
    command = [nvcc, "-ptx", "-lineinfo"]
    if architecture:
        command.append(f"-arch={architecture}")
    command.extend(extra_flags)
    command.extend((str(source), "-o", str(output)))
    _command(command)
    return {
        "source": str(source),
        "source_hash": file_sha256(source),
        "ptx": str(output),
        "ptx_hash": file_sha256(output),
        "compiler": nvcc,
        "compiler_identity": _command([nvcc, "--version"]).stdout.strip(),
        "command": command,
    }


def run_cuda_artifact(path_or_mapping: Path | dict[str, Any]) -> dict[str, Any]:
    raw, root = _load_cuda_artifact(path_or_mapping)
    command, module = _cuda_artifact_command(raw, root)
    payload = _json_result(_command(command))
    payload.update({
        "schema_version": CUDA_RUNNER_SCHEMA_VERSION,
        "artifact_hash": canonical_hash(raw),
        "module_hash": file_sha256(module),
        "runner": command[0],
    })
    return payload


def _load_cuda_artifact(path_or_mapping: Path | dict[str, Any]) -> tuple[dict[str, Any], Path]:
    if isinstance(path_or_mapping, Path):
        path = path_or_mapping.resolve()
        raw = yaml.safe_load(path.read_text())
        root = path.parent
    else:
        raw = path_or_mapping
        root = Path.cwd()
    if not isinstance(raw, dict):
        raise ValueError("CUDA artifact must be a mapping")
    if str(raw.get("schema_version", CUDA_ARTIFACT_SCHEMA_VERSION)) != CUDA_ARTIFACT_SCHEMA_VERSION:
        raise ValueError("unsupported CUDA artifact schema")
    return raw, root


def _cuda_artifact_command(raw: dict[str, Any], root: Path) -> tuple[list[str], Path]:
    module = Path(str(raw["module"]))
    if not module.is_absolute():
        module = (root / module).resolve()
    if not module.is_file():
        raise ValueError(f"CUDA artifact module is missing: {module}")
    runner = ensure_cuda_driver_runner()
    command = [
        str(runner),
        "--module", str(module),
        "--entry", str(raw.get("entry_point", "vladder_transform")),
        "--n", str(int(raw.get("logical_extent", 1 << 20))),
        "--threads", str(int(raw.get("threads", 256))),
        "--elements-per-thread", str(int(raw.get("elements_per_thread", 1))),
        "--warmup", str(int(raw.get("warmup", 10))),
        "--iterations", str(int(raw.get("iterations", 100))),
        "--device", str(int(raw.get("device", 0))),
    ]
    return command, module


def collect_ncu_counters(
    artifact: Path,
    output_path: Path,
    *,
    metrics: tuple[str, ...] = DEFAULT_NCU_METRICS,
) -> dict[str, Any]:
    ncu = cuda_tool("ncu")
    raw, root = _load_cuda_artifact(artifact)
    runner_command, module = _cuda_artifact_command(raw, root)
    warmup = int(raw.get("warmup", 10))
    profiled_runner = list(runner_command)
    iterations_index = profiled_runner.index("--iterations") + 1
    profiled_runner[iterations_index] = "1"
    command = [
        ncu,
        "--csv",
        "--page", "raw",
        "--launch-skip", str(warmup),
        "--launch-count", "1",
        "--metrics", ",".join(metrics),
        *profiled_runner,
    ]
    result = _command(command, timeout=300.0)
    rows = list(csv.reader(io.StringIO(result.stdout)))
    header_index = next((index for index, row in enumerate(rows) if row and row[0] == "ID"), None)
    if header_index is None or header_index + 2 >= len(rows):
        raise ValueError("Nsight Compute emitted no raw CSV metric row")
    header = rows[header_index]
    units = rows[header_index + 1]
    values = rows[header_index + 2]
    by_name = {
        name: {
            "value": values[index] if index < len(values) else "",
            "unit": units[index] if index < len(units) else "count",
        }
        for index, name in enumerate(header)
    }
    selected_names: set[str] = set()
    for requested in metrics:
        selected_names.update(name for name in by_name if name == requested or name.startswith(requested + "."))
    selected_names.update(name for name in by_name if name in {
        "gpu__time_duration.sum",
        "profiler__replayer_passes",
        "launch__registers_per_thread",
        "launch__registers_per_thread_allocated",
        "launch__shared_mem_per_block",
        "launch__stack_size",
        "launch__waves_per_multiprocessor",
        "launch__occupancy_limit_registers",
        "launch__occupancy_limit_shared_mem",
        "launch__occupancy_limit_warps",
    })
    normalized_metrics: dict[str, dict[str, Any]] = {}
    for name in sorted(selected_names):
        value = by_name[name]["value"].replace(",", "")
        try:
            numeric = float(value)
        except ValueError:
            continue
        normalized_metrics[name] = {"value": numeric, "unit": by_name[name]["unit"] or "count"}
    replay_count = int(normalized_metrics.get("profiler__replayer_passes", {}).get("value", 1))
    device = probe_cuda_device(int(raw.get("device", 0)))
    version = _command([ncu, "--version"]).stdout.strip()
    evidence = {
        "schema_version": "gpu-counter-evidence-v1",
        "collector": f"Nsight Compute: {version}",
        "architecture": device["architecture"],
        "device_identity": device["device_uuid"],
        "replay_count": replay_count,
        "profiler_distorts_timing": True,
        "serialized_execution": True,
        "metrics": normalized_metrics,
        "artifact_hash": canonical_hash(raw),
        "module_hash": file_sha256(module),
        "command": command,
        "claim_boundary": "counter attribution only; Nsight replay timing is excluded from physical ranking",
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(evidence, sort_keys=False))
    raw_path = output_path.with_suffix(".csv")
    raw_path.write_text(result.stdout)
    evidence["raw_csv"] = str(raw_path)
    return evidence


def write_cuda_artifact(
    path: Path,
    *,
    module: Path,
    entry_point: str,
    logical_extent: int,
    threads: int,
    elements_per_thread: int,
    warmup: int = 10,
    iterations: int = 100,
    device: int = 0,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CUDA_ARTIFACT_SCHEMA_VERSION,
        "module": str(module.resolve()),
        "entry_point": entry_point,
        "logical_extent": logical_extent,
        "threads": threads,
        "elements_per_thread": elements_per_thread,
        "warmup": warmup,
        "iterations": iterations,
        "device": device,
        "provenance": provenance or {},
    }
    payload["artifact_hash"] = canonical_hash(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def probe_cuda_architecture(
    output_path: Path | None = None,
    *,
    device: int = 0,
    measure_bandwidth: bool = True,
    bandwidth_extent: int = 1 << 25,
) -> dict[str, Any]:
    probe = probe_cuda_device(device)
    measured_bandwidth = float(probe["theoretical_memory_bandwidth_bytes_per_second"])
    bandwidth_evidence: dict[str, Any] = {"mode": "theoretical-fallback"}
    if measure_bandwidth:
        directory = _cache_root() / "bandwidth-probe"
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "copy.cu"
        source.write_text(
            '#include <cstddef>\n'
            'extern "C" __global__ void vladder_transform(float *dst, const float *src, std::size_t n) {\n'
            '    const std::size_t i = static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;\n'
            '    if (i < n) dst[i] = src[i];\n'
            '}\n'
        )
        module = directory / f"copy-{probe['architecture']}.ptx"
        compilation = compile_cuda_source(source, module, architecture=str(probe["architecture"]))
        artifact = write_cuda_artifact(
            directory / "copy-artifact.json",
            module=module,
            entry_point="vladder_transform",
            logical_extent=bandwidth_extent,
            threads=256,
            elements_per_thread=1,
            warmup=5,
            iterations=20,
            device=device,
            provenance=compilation,
        )
        timing = run_cuda_artifact(artifact)
        transferred_bytes = bandwidth_extent * 2 * 4
        measured_bandwidth = transferred_bytes / (float(timing["gpu_time_ns"]) * 1e-9)
        bandwidth_evidence = {
            "mode": "measured-copy-kernel",
            "logical_bytes_per_dispatch": transferred_bytes,
            "gpu_time_ns": timing["gpu_time_ns"],
            "bandwidth_bytes_per_second": measured_bandwidth,
            "artifact_hash": timing["artifact_hash"],
            "output_hash": timing["output_hash"],
        }
    architecture = {
        "schema_version": "gpu-architecture-v1",
        "vendor": probe["vendor"],
        "name": probe["name"],
        "architecture": probe["architecture"],
        "device_uuid": probe["device_uuid"],
        "warp_size": probe["warp_size"],
        "multiprocessors": probe["multiprocessors"],
        "max_threads_per_block": probe["max_threads_per_block"],
        "max_grid_dim_x": probe["max_grid_dim_x"],
        "max_threads_per_sm": probe["max_threads_per_sm"],
        "max_blocks_per_sm": probe["max_blocks_per_sm"],
        "max_warps_per_sm": probe["max_warps_per_sm"],
        "registers_per_sm": probe["registers_per_sm"],
        "register_allocation_unit": 256,
        "shared_memory_per_sm": probe["shared_memory_per_sm"],
        "shared_memory_per_block": probe["shared_memory_per_block"],
        "global_transaction_bytes": 128,
        "cache_line_bytes": 128,
        "memory_bandwidth_bytes_per_second": measured_bandwidth,
        "clock_hz": probe["clock_hz"],
        "issue_width": 4.0,
        "probe": probe,
        "bandwidth_evidence": bandwidth_evidence,
        "assumptions": {
            "register_allocation_unit": "NVIDIA architecture-family assumption; calibrate with compiler occupancy metadata",
            "global_transaction_bytes": "128-byte coalesced segment model",
            "cache_line_bytes": "128-byte sector-group model",
            "issue_width": "static pruning assumption, not a measured throughput claim",
        },
    }
    architecture["manifest_hash"] = canonical_hash({
        key: value for key, value in architecture.items() if key != "manifest_hash"
    })
    report = {"architecture": architecture, "probe_status": "PASS"}
    if output_path is not None:
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml.safe_dump(report, sort_keys=False))
    return report
