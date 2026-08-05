from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .statistics_v3 import empirical_quantile


SPIRV_RECIPES: dict[str, list[str]] = {
    "cleanup": [
        "--eliminate-dead-code-aggressive",
        "--eliminate-local-single-block",
        "--eliminate-local-single-store",
        "--simplify-instructions",
        "--cfg-cleanup",
    ],
    "access-chain": [
        "--combine-access-chains",
        "--redundancy-elimination",
        "--simplify-instructions",
        "--compact-ids",
    ],
    "size": ["-Os"],
}


def _tool(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise RuntimeError(f"required shader tool is unavailable: {name}")
    return value


def _run(command: list[str], *, cwd: Path | None = None, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"shader command failed: {' '.join(command)}\n{result.stderr[-3000:]}")
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_shader(source: Path, output_directory: Path, *, target_env: str = "vulkan1.2") -> dict[str, Any]:
    source = source.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    module = output_directory / "baseline.spv"
    compile_command: list[str] | None = None
    if source.suffix == ".spv":
        shutil.copyfile(source, module)
    else:
        stage = "comp" if source.suffix in {".comp", ".glsl"} else None
        if not stage:
            raise ValueError("portable shader workflow currently accepts .comp, .glsl compute, or .spv")
        compile_command = [
            _tool("glslangValidator"), "-V", "--target-env", target_env, "-S", stage,
            str(source), "-o", str(module),
        ]
        _run(compile_command)
    validation = _run([_tool("spirv-val"), "--target-env", target_env, str(module)])
    disassembly = output_directory / "baseline.spvasm"
    _run([_tool("spirv-dis"), str(module), "-o", str(disassembly)])
    text = disassembly.read_text(errors="replace")
    entries = re.findall(r'OpEntryPoint\s+GLCompute\s+%\w+\s+"([^"]+)"', text)
    local_sizes = [list(map(int, match)) for match in re.findall(r"OpExecutionMode\s+%\w+\s+LocalSize\s+(\d+)\s+(\d+)\s+(\d+)", text)]
    report = {
        "schema_version": "vladder-shader-inspection-v1",
        "status": "pass",
        "language": "spirv-compute",
        "source": str(source),
        "source_sha256": _sha256(source),
        "module": str(module),
        "module_sha256": _sha256(module),
        "module_bytes": module.stat().st_size,
        "disassembly": str(disassembly),
        "target_env": target_env,
        "entry_points": entries,
        "local_sizes": local_sizes,
        "compile_command": compile_command,
        "validation": {"status": "pass", "stdout": validation.stdout, "stderr": validation.stderr},
        "proof_classification": "structurally_valid_spirv",
        "semantic_equivalence": "NOT_ESTABLISHED",
        "next_action": "synthesize bounded SPIR-V candidates, then provide an application output and device-timestamp runner",
    }
    (output_directory / "shader-inspection.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def synthesize_shader(
    source: Path,
    output_directory: Path,
    *,
    target_env: str = "vulkan1.2",
    runner_manifest: Path | None = None,
) -> dict[str, Any]:
    output_directory = output_directory.resolve()
    inspection = inspect_shader(source, output_directory / "inspection", target_env=target_env)
    baseline = Path(inspection["module"])
    candidates: list[dict[str, Any]] = []
    seen = {inspection["module_sha256"]}
    for recipe, arguments in SPIRV_RECIPES.items():
        candidate_dir = output_directory / "candidates" / recipe
        candidate_dir.mkdir(parents=True, exist_ok=True)
        module = candidate_dir / "candidate.spv"
        command = [_tool("spirv-opt"), f"--target-env={target_env}", *arguments, str(baseline), "-o", str(module)]
        try:
            _run(command)
            _run([_tool("spirv-val"), "--target-env", target_env, str(module)])
            assembly = candidate_dir / "candidate.spvasm"
            _run([_tool("spirv-dis"), str(module), "-o", str(assembly)])
            module_hash = _sha256(module)
            duplicate = module_hash in seen
            seen.add(module_hash)
            candidates.append({
                "id": recipe,
                "status": "duplicate" if duplicate else "output_oracle_required",
                "module": str(module),
                "module_sha256": module_hash,
                "module_bytes": module.stat().st_size,
                "recipe": arguments,
                "command": command,
                "structural_validation": "PASS",
                "semantic_equivalence": "NOT_ESTABLISHED",
                "promotable": False,
            })
        except RuntimeError as error:
            candidates.append({"id": recipe, "status": "tool_failure", "error": str(error), "promotable": False})

    runner_report = None
    if runner_manifest:
        runner_report = _evaluate_shader_runner(
            baseline, candidates, runner_manifest.resolve(), output_directory / "runner-evidence"
        )
        by_id = {item["candidate_id"]: item for item in runner_report["candidates"]}
        for candidate in candidates:
            evidence = by_id.get(candidate["id"])
            if evidence:
                candidate["runner_evidence"] = evidence
                candidate["semantic_equivalence"] = evidence["output_equivalence"]
                candidate["promotable"] = bool(evidence["physically_promotable"])
                candidate["status"] = evidence["classification"]

    winners = [item for item in candidates if item.get("promotable")]
    winners.sort(key=lambda item: float(item.get("runner_evidence", {}).get("effect_percent", 0.0)), reverse=True)
    report = {
        "schema_version": "vladder-shader-synthesis-v1",
        "status": "pass" if candidates else "fail",
        "inspection": inspection,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "winner": winners[0] if winners else None,
        "runner_evidence": runner_report,
        "proof_boundary": {
            "spirv_validation": "structural legality only",
            "optimizer_recipe": "tool-generated candidate, not formal equivalence",
            "output_oracle": "required for semantic differential evidence",
            "device_timestamps": "required for physical promotion",
            "host_protocols": "Vulkan/CUDA/driver/queue/presentation semantics remain explicit application adapters",
        },
        "next_action": (
            "integrate the winning module and run composed-system confirmation"
            if winners else
            "provide --runner-manifest with exact output hashes and device timestamps; no candidate is promotable yet"
        ),
    }
    (output_directory / "shader-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _evaluate_shader_runner(
    baseline: Path,
    candidates: list[dict[str, Any]],
    manifest_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("command"), list):
        raise ValueError("shader runner manifest requires a command list containing {module}")
    command = [str(item) for item in raw["command"]]
    if not any("{module}" in item for item in command):
        raise ValueError("shader runner command must contain {module}")
    processes = int(raw.get("processes", 10))
    minimum = float(raw.get("minimum_effect_percent", 1.0))
    seed = int(raw.get("seed", 0))
    timeout = float(raw.get("timeout_seconds", 120.0))
    baseline_samples: dict[str, list[float]] = {}
    results: list[dict[str, Any]] = []
    rng = random.Random(seed)

    def invoke(module: Path) -> tuple[float, str]:
        expanded = [item.replace("{module}", str(module)) for item in command]
        completed = _run(expanded, cwd=manifest_path.parent, timeout=timeout)
        for line in reversed(completed.stdout.splitlines()):
            if line.strip().startswith("{"):
                value = json.loads(line)
                return float(value["gpu_time_ns"]), str(value["output_hash"])
        raise ValueError("shader runner did not emit gpu_time_ns and output_hash JSON")

    for candidate in candidates:
        if candidate.get("status") in {"duplicate", "tool_failure"}:
            continue
        cid = str(candidate["id"])
        module = Path(candidate["module"])
        base_times: list[float] = []
        candidate_times: list[float] = []
        mismatches: list[dict[str, str]] = []
        for index in range(processes):
            order = ["baseline", "candidate"]
            rng.shuffle(order)
            observed: dict[str, tuple[float, str]] = {}
            for variant in order:
                observed[variant] = invoke(baseline if variant == "baseline" else module)
            base_times.append(observed["baseline"][0])
            candidate_times.append(observed["candidate"][0])
            if observed["baseline"][1] != observed["candidate"][1]:
                mismatches.append({"baseline": observed["baseline"][1], "candidate": observed["candidate"][1]})
        effects = [(base / cand - 1.0) * 100.0 for base, cand in zip(base_times, candidate_times)]
        interval = _bootstrap(effects, seed + len(results))
        effect = statistics.median(effects)
        accepted = not mismatches and interval[0] >= minimum
        results.append({
            "candidate_id": cid,
            "output_equivalence": "PASS" if not mismatches else "FAIL",
            "output_mismatches": mismatches,
            "baseline_gpu_time_ns": base_times,
            "candidate_gpu_time_ns": candidate_times,
            "effect_percent": effect,
            "effect_95_percent": interval,
            "minimum_effect_percent": minimum,
            "physically_promotable": accepted,
            "classification": "gpu_candidate_win" if accepted else ("verification_failed" if mismatches else "statistical_tie"),
        })
    output_directory.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "vladder-shader-runner-evidence-v1",
        "runner_manifest": str(manifest_path),
        "timing_source": raw.get("timing_source", "application_declared_device_timestamp"),
        "candidates": results,
    }
    (output_directory / "shader-runner.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _bootstrap(effects: list[float], seed: int, rounds: int = 2000) -> list[float]:
    rng = random.Random(seed)
    values = []
    for _ in range(rounds):
        values.append(statistics.median(effects[rng.randrange(len(effects))] for _ in effects))
    return [empirical_quantile(values, 0.025), empirical_quantile(values, 0.975)]


def gpu_support_matrix() -> dict[str, Any]:
    tools = {name: shutil.which(name) for name in (
        "glslangValidator", "spirv-val", "spirv-opt", "spirv-dis", "nvcc", "cuobjdump", "nvdisasm"
    )}
    return {
        "schema_version": "vladder-gpu-support-v1",
        "spirv_compute": {
            "status": "operational" if all(tools[name] for name in ("glslangValidator", "spirv-val", "spirv-opt", "spirv-dis")) else "toolchain_required",
            "semantic_scope": "module validation plus application output oracle",
        },
        "cuda": {
            "status": "runner_and_toolchain_required" if not tools["nvcc"] else "external_runner_required",
            "semantic_scope": "device kernel outputs and host protocol require a concrete CUDA runner",
        },
        "tools": tools,
    }
