from __future__ import annotations

import hashlib
import json
import random
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .statistics_v3 import empirical_quantile


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _parse_result(stdout: str, metric_key: str, observable_key: str | None) -> tuple[float, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            value = json.loads(line)
            if metric_key not in value:
                raise ValueError(f"benchmark JSON has no metric key {metric_key!r}")
            return float(value[metric_key]), value.get(observable_key) if observable_key else None
    raise ValueError("benchmark stdout contains no JSON object")


def _invoke(
    executable: Path,
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: float,
    cpu: int | None,
    metric_key: str,
    observable_key: str | None,
) -> dict[str, Any]:
    import os

    command = [str(executable), *arguments]
    if cpu is not None and shutil.which("taskset"):
        command = ["taskset", "-c", str(cpu), *command]
    completed = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, **environment},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"benchmark command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr[-2000:]}"
        )
    metric, observable = _parse_result(completed.stdout, metric_key, observable_key)
    return {"metric": metric, "observable": observable, "command": command}


def _bootstrap_paired(effects: list[float], rounds: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(rounds):
        block = [effects[rng.randrange(len(effects))] for _ in effects]
        samples.append(statistics.median(block))
    return [empirical_quantile(samples, 0.025), empirical_quantile(samples, 0.975)]


def run_paired_benchmark(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("paired benchmark manifest must be a mapping")
    executable = Path(str(raw.get("executable", "")))
    if not executable.is_absolute():
        executable = (manifest_path.parent / executable).resolve()
    if not executable.exists():
        raise ValueError(f"benchmark executable does not exist: {executable}")
    baseline_args = [str(item) for item in raw.get("baseline_args", [])]
    candidate_args = [str(item) for item in raw.get("candidate_args", [])]
    processes = int(raw.get("processes", raw.get("maximum_processes", 10)))
    minimum_processes = int(raw.get("minimum_processes", processes))
    maximum_processes = int(raw.get("maximum_processes", processes))
    repetitions = int(raw.get("repetitions_per_process", 1))
    if minimum_processes < 2 or maximum_processes < minimum_processes or repetitions < 1:
        raise ValueError("paired benchmarking requires at least two processes and one repetition")
    direction = str(raw.get("direction", "lower"))
    if direction not in {"lower", "higher"}:
        raise ValueError("direction must be lower or higher")
    metric_key = str(raw.get("metric_key", "metric"))
    observable_key = str(raw["observable_key"]) if raw.get("observable_key") else None
    exact_observables = bool(raw.get("exact_observables", observable_key is not None))
    timeout = float(raw.get("timeout_seconds", 120.0))
    seed = int(raw.get("seed", 0))
    minimum_effect = float(raw.get("minimum_effect_percent", 1.0))
    bootstrap_rounds = int(raw.get("bootstrap_rounds", 2000))
    cpu = int(raw["cpu"]) if raw.get("cpu") is not None else None
    cwd = Path(str(raw.get("cwd", manifest_path.parent)))
    if not cwd.is_absolute():
        cwd = (manifest_path.parent / cwd).resolve()
    environment = {str(key): str(value) for key, value in (raw.get("environment") or {}).items()}

    rng = random.Random(seed)
    pairs: list[dict[str, Any]] = []
    observable_failures: list[dict[str, Any]] = []
    stopping = raw.get("stopping_rule") if isinstance(raw.get("stopping_rule"), dict) else {}
    target_width = float(stopping.get("target_ci_width_percent", 0.0))
    stopped_early = False
    stopping_reason = "maximum_processes_reached"
    for process_index in range(maximum_processes):
        order = ["baseline", "candidate"]
        rng.shuffle(order)
        samples = {"baseline": [], "candidate": []}
        observables = {"baseline": [], "candidate": []}
        for variant in order:
            args = baseline_args if variant == "baseline" else candidate_args
            for _ in range(repetitions):
                result = _invoke(
                    executable, args, cwd=cwd, environment=environment, timeout=timeout, cpu=cpu,
                    metric_key=metric_key, observable_key=observable_key,
                )
                samples[variant].append(result["metric"])
                observables[variant].append(result["observable"])
        baseline_value = statistics.median(samples["baseline"])
        candidate_value = statistics.median(samples["candidate"])
        effect = (
            (baseline_value / candidate_value - 1.0) * 100.0
            if direction == "lower" else
            (candidate_value / baseline_value - 1.0) * 100.0
        )
        if exact_observables and observables["baseline"] != observables["candidate"]:
            observable_failures.append({
                "process": process_index,
                "baseline": observables["baseline"],
                "candidate": observables["candidate"],
            })
        pairs.append({
            "process": process_index,
            "order": order,
            "baseline": samples["baseline"],
            "candidate": samples["candidate"],
            "baseline_median": baseline_value,
            "candidate_median": candidate_value,
            "effect_percent": effect,
            "observables": observables,
        })
        if len(pairs) < minimum_processes:
            continue
        interim_effects = [item["effect_percent"] for item in pairs]
        interim_interval = _bootstrap_paired(interim_effects, max(250, min(bootstrap_rounds, 1000)), seed + 1000 + process_index)
        decisive = interim_interval[0] >= minimum_effect or interim_interval[1] < minimum_effect
        narrow_enough = target_width <= 0.0 or interim_interval[1] - interim_interval[0] <= target_width
        if decisive and narrow_enough:
            stopped_early = len(pairs) < maximum_processes
            stopping_reason = "confidence_interval_decisive"
            break

    effects = [item["effect_percent"] for item in pairs]
    interval = _bootstrap_paired(effects, bootstrap_rounds, seed + 1)
    point = statistics.median(effects)
    semantic_pass = not observable_failures
    accepted = semantic_pass and interval[0] >= minimum_effect
    tie = semantic_pass and interval[0] < minimum_effect <= interval[1]
    candidate_identity = str(raw.get("candidate_identity", _canonical_hash(candidate_args)))
    retained_identity = raw.get("retained_candidate_identity")
    evidence_class = (
        "retained_revalidated" if accepted and retained_identity == candidate_identity else
        "newly_discovered" if accepted else
        "verification_failed" if not semantic_pass else
        "statistical_tie" if tie else
        "measured_regression" if point < 0 else
        "insufficient_effect"
    )
    report = {
        "schema_version": "vladder-paired-benchmark-v1",
        "status": "pass" if accepted else "not_promoted",
        "executable": str(executable),
        "same_executable": True,
        "metric_key": metric_key,
        "direction": direction,
        "process_count": len(pairs),
        "experiment_design": {
            "minimum_processes": minimum_processes,
            "maximum_processes": maximum_processes,
            "stopped_early": stopped_early,
            "stopping_reason": stopping_reason,
            "target_ci_width_percent": target_width or None,
        },
        "repetitions_per_process": repetitions,
        "randomized_order": True,
        "seed": seed,
        "paired_effect_percent": point,
        "paired_effect_95_percent": interval,
        "minimum_effect_percent": minimum_effect,
        "semantic_parity": "PASS" if semantic_pass else "FAIL",
        "observable_failures": observable_failures,
        "classification": evidence_class,
        "promotable_physical_evidence": accepted,
        "candidate_identity": candidate_identity,
        "retained_candidate_identity": retained_identity,
        "pairs": pairs,
        "manifest_hash": _canonical_hash(raw),
        "limitations": [
            "process startup is included in each sample unless the executable performs internal repetitions",
            "paired physical evidence does not establish semantic equivalence outside the declared observable projection",
        ],
    }
    (output_directory / "paired-benchmark.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def compose_benchmark_effects(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("effects"), list):
        raise ValueError("composition manifest requires an effects list")
    effects = raw["effects"]
    seen: dict[str, str] = {}
    overlaps: list[dict[str, str]] = []
    for item in effects:
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError("each effect requires an id")
        covered = {str(value) for value in item.get("covers", [item["id"]])}
        for region in covered:
            if region in seen:
                overlaps.append({"region": region, "first": seen[region], "second": str(item["id"])})
            else:
                seen[region] = str(item["id"])
    interaction = raw.get("interaction_run")
    if overlaps and not interaction:
        result = {
            "schema_version": "vladder-effect-composition-v1",
            "status": "rejected_overlap",
            "composable": False,
            "overlaps": overlaps,
            "reason": "overlapping regional effects cannot be compounded without a measured interaction run",
        }
    else:
        factors = [1.0 + float(item.get("effect_percent", 0.0)) / 100.0 for item in effects]
        combined = 1.0
        for factor in factors:
            combined *= factor
        result = {
            "schema_version": "vladder-effect-composition-v1",
            "status": "pass",
            "composable": True,
            "overlaps": overlaps,
            "combined_effect_percent": (combined - 1.0) * 100.0,
            "classification": "measured_interaction" if overlaps else "disjoint_regions",
            "interaction_run": interaction,
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def compose_application_cost(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("regions"), list):
        raise ValueError("application composition manifest requires a regions list")
    regions = raw["regions"]
    covered: dict[str, str] = {}
    overlaps: list[dict[str, str]] = []
    total_share = 0.0
    optimized_share = 0.0
    overhead_percent = 0.0
    rows = []
    for item in regions:
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError("every composed region requires an id")
        region_id = str(item["id"])
        coverage = {str(value) for value in item.get("covers", [region_id])}
        for owner in coverage:
            if owner in covered:
                overlaps.append({"region": owner, "first": covered[owner], "second": region_id})
            else:
                covered[owner] = region_id
        share = float(item.get("baseline_runtime_share_percent", 0.0)) / 100.0
        speedup = float(item.get("regional_speedup_percent", 0.0)) / 100.0
        invocation_scale = float(item.get("invocation_frequency_scale", 1.0))
        amortized_overhead = float(item.get("amortized_overhead_percent", 0.0)) / 100.0
        queue_overlap = min(1.0, max(0.0, float(item.get("queue_overlap_fraction", 0.0))))
        effective_share = share * invocation_scale * (1.0 - queue_overlap)
        new_share = effective_share / (1.0 + speedup) if speedup > -1.0 else float("inf")
        total_share += effective_share
        optimized_share += new_share
        overhead_percent += amortized_overhead
        rows.append({
            "id": region_id,
            "effective_runtime_share_percent": effective_share * 100.0,
            "regional_speedup_percent": speedup * 100.0,
            "queue_overlap_fraction": queue_overlap,
            "predicted_total_time_reduction_percent": (effective_share - new_share) * 100.0,
        })
    interaction = raw.get("interaction_run")
    if overlaps and not interaction:
        result = {
            "schema_version": "vladder-application-composition-v1",
            "status": "rejected_overlap",
            "composable": False,
            "overlaps": overlaps,
            "regions": rows,
            "reason": "overlapping regional effects require a measured interaction run",
        }
    elif total_share > 1.000001:
        result = {
            "schema_version": "vladder-application-composition-v1",
            "status": "invalid_runtime_share",
            "composable": False,
            "overlaps": overlaps,
            "regions": rows,
            "reason": "effective regional runtime shares exceed 100%",
        }
    else:
        predicted_new_time = (1.0 - total_share) + optimized_share + overhead_percent
        predicted_speedup = (1.0 / predicted_new_time - 1.0) * 100.0
        result = {
            "schema_version": "vladder-application-composition-v1",
            "status": "pass",
            "composable": True,
            "overlaps": overlaps,
            "regions": rows,
            "predicted_end_to_end_speedup_percent": predicted_speedup,
            "amortized_overhead_percent": overhead_percent * 100.0,
            "interaction_run": interaction,
            "confirmation_required": True,
            "claim_boundary": "Amdahl-style forecast only; a measured end-to-end run is required for promotion",
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
