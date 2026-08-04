from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .report import write_json
from .toolchain import run


def verify_regenerated_q4k_model(
    active_manifest_path: Path,
    parity_report_path: Path,
    out_dir: Path,
    *,
    prompt: str = "Write one sentence about compiler verification.",
    generated_tokens: int = 16,
    seed: int = 4242,
) -> dict[str, Any]:
    active = json.loads(active_manifest_path.read_text())
    parity = json.loads(parity_report_path.read_text())
    if active.get("status") != "PASS" or parity.get("classification") != "parity_pass":
        raise ValueError("model verification requires active-path and parity gates")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    parity_dir = parity_report_path.resolve().parent
    regenerated = parity_dir / "regenerated-q4k-gemv.cpp"
    if hashlib.sha256(regenerated.read_bytes()).hexdigest() != parity["regenerated_source_sha256"]:
        raise ValueError("regenerated source hash mismatch")
    build = Path(active["build"]["directory"])
    llama_root = Path(active["source_provenance"]["kernel"]["path"]).parents[5]
    model = Path(active["model"]["path"])
    completion = build / "bin/llama-completion"
    built = run(["cmake", "--build", str(build), "--target", "llama-completion", "-j4"], timeout=900, cwd=llama_root)
    if built.returncode:
        raise RuntimeError((built.stdout + built.stderr)[-5000:])
    override = out_dir / "libvladder-q4k-regenerated.so"
    rename = "-Dvladder_regenerated_gemv_q4_K_8x8_q8_K=ggml_gemv_q4_K_8x8_q8_K"
    compile_command = [
        "clang++-20", "-std=gnu++17", "-O3", "-DNDEBUG", "-march=native", "-fPIC", "-shared", rename,
        f"-I{llama_root/'ggml/include'}", f"-I{llama_root/'ggml/src'}", f"-I{llama_root/'ggml/src/ggml-cpu'}",
        str(regenerated), "-o", str(override),
    ]
    compiled = run(compile_command, timeout=180)
    if compiled.returncode:
        raise RuntimeError((compiled.stdout + compiled.stderr)[-5000:])
    command = [
        "taskset", "-c", active["capture"]["cpu_list"], str(completion), "-m", str(model),
        "-p", prompt, "-n", str(generated_tokens), "-t", str(active["capture"]["threads"]),
        "-tb", str(active["capture"]["threads"]), "--temp", "0", "--seed", str(seed),
        "--no-display-prompt", "--simple-io", "--no-warmup", "--no-conversation", "--color", "off",
    ]
    native = run(command, timeout=1200, cwd=llama_root)
    overridden = run(command, timeout=1200, cwd=llama_root, env={
        "LD_PRELOAD": str(override), "LD_DEBUG": "bindings",
    })
    if native.returncode or overridden.returncode:
        raise RuntimeError("native or regenerated model execution failed")
    binding_fragment = (
        "libggml-cpu.so.0 [0] to " + str(override) + " [0]: normal symbol `ggml_gemv_q4_K_8x8_q8_K'"
    )
    binding_count = overridden.stderr.count(binding_fragment)
    if binding_count == 0:
        raise RuntimeError("fail-closed dispatch check: regenerated GEMV was not dynamically bound")
    native_hash = hashlib.sha256(native.stdout.encode()).hexdigest()
    overridden_hash = hashlib.sha256(overridden.stdout.encode()).hexdigest()
    report = {
        "schema_version": "vladder-q4k-model-verification-v7.0",
        "status": "PASS" if native.stdout == overridden.stdout else "FAIL",
        "contract": "E1 generated-token byte identity",
        "active_path_manifest_sha256": hashlib.sha256(active_manifest_path.read_bytes()).hexdigest(),
        "parity_report_sha256": hashlib.sha256(parity_report_path.read_bytes()).hexdigest(),
        "model_sha256": active["model"]["sha256"],
        "override_sha256": hashlib.sha256(override.read_bytes()).hexdigest(),
        "regenerated_source_sha256": parity["regenerated_source_sha256"],
        "compile_command": compile_command,
        "command": command,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "seed": seed,
        "generated_tokens_requested": generated_tokens,
        "native_output_sha256": native_hash,
        "regenerated_output_sha256": overridden_hash,
        "generated_output": native.stdout,
        "dispatch": {"fail_closed": True, "binding_count": binding_count, "symbol": "ggml_gemv_q4_K_8x8_q8_K"},
        "claim": "The independently regenerated E1 baseline executed in the pinned Qwen model and produced byte-identical output.",
    }
    (out_dir / "native.stdout.txt").write_text(native.stdout)
    (out_dir / "native.stderr.txt").write_text(native.stderr)
    (out_dir / "regenerated.stdout.txt").write_text(overridden.stdout)
    (out_dir / "regenerated.stderr.txt").write_text(overridden.stderr)
    write_json(out_dir / "q4k-model-verification.json", report)
    if report["status"] != "PASS":
        raise RuntimeError("regenerated model output differs from native output")
    return report
