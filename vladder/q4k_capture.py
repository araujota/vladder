from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .hardware_manifest import capture_manifest, write_manifest
from .llama_integration import PINNED_LLAMA_COMMIT
from .report import write_json
from .toolchain import discover_toolchain, run


Q4K_PATH_RE = re.compile(
    r"^VLADDER_Q4K_PATH\|tensor=(?P<tensor>[^|]+)\|kernel=(?P<kernel>[^|]+)"
    r"\|weight_type=(?P<weight_type>[^|]+)\|activation_source_type=(?P<activation_source_type>[^|]+)"
    r"\|activation_block_type=(?P<activation_block_type>[^|]+)\|repack_type=(?P<repack_type>[^|]+)"
    r"\|interleave=(?P<interleave>\d+)\|output_row_group=(?P<output_row_group>\d+)"
    r"\|input=(?P<input>\d+)\|outputs=(?P<outputs>\d+)\|tokens=(?P<tokens>\d+)"
    r"\|threads=(?P<threads>\d+)\|gemm_threshold=(?P<gemm_threshold>\d+)"
    r"\|tail=(?P<tail>[^|]+)\|avx2=(?P<avx2>[01])$"
)


def parse_q4k_path_records(log: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    numeric = {"interleave", "output_row_group", "input", "outputs", "tokens", "threads", "gemm_threshold", "avx2"}
    for line in log.splitlines():
        match = Q4K_PATH_RE.match(line.strip())
        if not match:
            continue
        raw = match.groupdict()
        item = {key: (int(value) if key in numeric else value) for key, value in raw.items()}
        item["category"] = _tensor_category(str(item["tensor"]))
        records.append(item)
    return records


def capture_active_q4k_path(
    llama_root: Path,
    model: Path,
    out_dir: Path,
    *,
    cpu_list: str = "0-7",
    threads: int = 8,
    prompt_tokens: int = 16,
    expected_kernel: str = "ggml_gemv_q4_K_8x8_q8_K",
) -> dict[str, Any]:
    llama_root = llama_root.resolve()
    model = model.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not model.is_file():
        raise FileNotFoundError(model)
    commit = run(["git", "rev-parse", "HEAD"], timeout=20, cwd=llama_root).stdout.strip()
    if commit != PINNED_LLAMA_COMMIT:
        raise ValueError(f"llama.cpp commit mismatch: expected {PINNED_LLAMA_COMMIT}, got {commit}")
    build = llama_root / "build-vladder-cli"
    built = run(["cmake", "--build", str(build), "--target", "llama-bench", "-j4"], timeout=900, cwd=llama_root)
    if built.returncode:
        raise RuntimeError((built.stdout + built.stderr)[-5000:])
    first_cpu = int(cpu_list.split(",", 1)[0].split("-", 1)[0])
    hardware = capture_manifest("local-7950x3d-q4k-v7", first_cpu, discover_toolchain())
    write_manifest(out_dir / "hardware-manifest.json", hardware)
    command = [
        "taskset", "-c", cpu_list, str(build / "bin/llama-bench"), "-m", str(model),
        "-p", str(prompt_tokens), "-n", "1", "-r", "1", "-t", str(threads), "-ngl", "0", "-o", "json",
    ]
    execution = run(command, timeout=1200, cwd=llama_root, env={"VLADDER_CAPTURE_Q4K_PATH": "1"})
    (out_dir / "capture.stdout.json").write_text(execution.stdout)
    (out_dir / "capture.stderr.log").write_text(execution.stderr)
    if execution.returncode:
        raise RuntimeError((execution.stdout + execution.stderr)[-5000:])
    records = parse_q4k_path_records(execution.stderr)
    errors = _capture_errors(records, expected_kernel, threads)
    if errors:
        raise RuntimeError("active Q4_K path capture failed: " + "; ".join(errors))
    sources = {
        "dispatch": llama_root / "ggml/src/ggml-cpu/repack.cpp",
        "kernel": llama_root / "ggml/src/ggml-cpu/arch/x86/repack.cpp",
        "block_types": llama_root / "ggml/src/ggml-common.h",
        "repack_types": llama_root / "ggml/src/ggml-cpu/repack.h",
    }
    provenance = {
        name: {
            "path": str(path), "sha256": _sha256(path),
            "symbols": _source_symbols(path, _symbols_for(name)),
        }
        for name, path in sources.items()
    }
    compile_commands = _compile_commands(build / "compile_commands.json", sources.values())
    library = build / "bin/libggml-cpu.so"
    symbols = _binary_symbols(library, ("ggml_gemv_q4_K_8x8_q8_K", "ggml_gemm_q4_K_8x8_q8_K"))
    categories: dict[str, Any] = {}
    for category in sorted({str(item["category"]) for item in records}):
        selected = [item for item in records if item["category"] == category]
        categories[category] = {
            "count": len(selected),
            "tensors": sorted({str(item["tensor"]) for item in selected}),
            "shapes": sorted({(item["input"], item["outputs"], item["tokens"]) for item in selected}),
            "kernels": sorted({str(item["kernel"]) for item in selected}),
        }
    post = capture_manifest("local-7950x3d-q4k-v7", first_cpu, discover_toolchain())
    write_manifest(out_dir / "hardware-manifest.post.json", post)
    if hardware.manifest_hash != post.manifest_hash:
        raise RuntimeError("material hardware/software configuration changed during capture")
    manifest = {
        "schema_version": "vladder-active-q4k-path-v7.0",
        "status": "PASS",
        "llama_commit": commit,
        "model": {"path": str(model), "sha256": _sha256(model), "bytes": model.stat().st_size},
        "hardware_manifest_hash": hardware.manifest_hash,
        "post_hardware_manifest_hash": post.manifest_hash,
        "build": {
            "directory": str(build), "llama_bench_sha256": _sha256(build / "bin/llama-bench"),
            "ggml_cpu_sha256": _sha256(library), "compile_commands": compile_commands,
        },
        "runtime_contract": {
            "expected_decode_kernel": expected_kernel,
            "weight_block_type": "block_q4_K",
            "runtime_repack_type": "block_q4_Kx8",
            "activation_block_type": "q8_K",
            "output_row_group": 8,
            "interleave": 8,
            "gemm_threshold": 4,
            "thread_partition": "dynamic output-row chunks aligned to NB_COLS=8",
            "decode_tail": "GEMV for activation rows not consumed by groups of four",
            "fail_closed": True,
        },
        "records": records,
        "tensor_categories": categories,
        "source_provenance": provenance,
        "binary_symbols": symbols,
        "capture": {"command": command, "cpu_list": cpu_list, "threads": threads, "prompt_tokens": prompt_tokens},
    }
    write_json(out_dir / "active-q4k-path.json", manifest)
    return manifest


def enforce_active_q4k_manifest(manifest: dict[str, Any], records: list[dict[str, Any]]) -> None:
    contract = manifest["runtime_contract"]
    errors = _capture_errors(records, str(contract["expected_decode_kernel"]), int(manifest["capture"]["threads"]))
    if any(item["repack_type"] != contract["runtime_repack_type"] for item in records):
        errors.append("runtime repack type differs from manifest")
    if any(item["output_row_group"] != int(contract["output_row_group"]) for item in records):
        errors.append("output row group differs from manifest")
    if errors:
        raise ValueError("active Q4_K manifest mismatch: " + "; ".join(sorted(set(errors))))


def _capture_errors(records: list[dict[str, Any]], expected_decode_kernel: str, threads: int) -> list[str]:
    errors: list[str] = []
    if not records:
        return ["runtime emitted no Q4_K path records"]
    decode = [item for item in records if item["tokens"] == 1]
    if not decode:
        errors.append("runtime emitted no single-token Q4_K record")
    if any(item["kernel"] != expected_decode_kernel for item in decode):
        errors.append("single-token dispatch selected an unexpected kernel")
    if any(item["weight_type"] != "q4_K" for item in records):
        errors.append("captured non-Q4_K weight path")
    if any(item["activation_block_type"] != "q8_K" for item in records):
        errors.append("captured non-Q8_K activation path")
    if any(item["repack_type"] != "block_q4_Kx8" or item["interleave"] != 8 for item in records):
        errors.append("captured unexpected native repack")
    if any(item["avx2"] != 1 for item in records):
        errors.append("AVX2 dispatch precondition is false")
    if any(item["threads"] != threads for item in records):
        errors.append("captured thread count differs")
    if not any(item["category"] == "ffn_gate_up" for item in decode):
        errors.append("gate/up tensors did not exercise the decode path")
    return errors


def _tensor_category(name: str) -> str:
    if re.match(r"ffn_(?:gate|up)-\d+$", name):
        return "ffn_gate_up"
    if re.match(r"ffn_out-\d+$", name):
        return "ffn_down"
    if re.match(r"(?:Qcur|Kcur|Vcur)-\d+$", name):
        return "qkv"
    if name == "result_output":
        return "logits"
    return "attention_output_or_other"


def _source_symbols(path: Path, symbols: tuple[str, ...]) -> dict[str, list[int]]:
    lines = path.read_text().splitlines()
    return {symbol: [index for index, line in enumerate(lines, 1) if symbol in line] for symbol in symbols}


def _symbols_for(name: str) -> tuple[str, ...]:
    return {
        "dispatch": ("forward_mul_mat_one_chunk", "ggml_repack_get_optimal_repack_type", "repack_q4_K_to_q4_K_8_bl"),
        "kernel": ("ggml_gemv_q4_K_8x8_q8_K", "ggml_gemm_q4_K_8x8_q8_K"),
        "block_types": ("block_q4_K", "block_q8_K"),
        "repack_types": ("block_q4_Kx8",),
    }[name]


def _compile_commands(path: Path, sources: Any) -> list[dict[str, str]]:
    if not path.is_file():
        raise RuntimeError("compile_commands.json is required for active-path provenance")
    raw = json.loads(path.read_text())
    wanted = {str(path.resolve()) for path in sources}
    return [
        {"file": str(Path(item["file"]).resolve()), "command": str(item.get("command", ""))}
        for item in raw if str(Path(item["file"]).resolve()) in wanted
    ]


def _binary_symbols(library: Path, symbols: tuple[str, ...]) -> dict[str, Any]:
    result = run(["nm", "-D", "-C", str(library)], timeout=30)
    if result.returncode:
        raise RuntimeError("unable to inspect ggml-cpu symbols")
    return {symbol: [line for line in result.stdout.splitlines() if symbol in line] for symbol in symbols}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
