from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import random
import statistics
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .language_adapter import canonical_hash
from .statistics_v3 import empirical_quantile


GPU_COUNTER_SCHEMA_VERSION = "gpu-counter-evidence-v1"
GPU_RANKING_SCHEMA_VERSION = "gpu-physical-ranking-v1"


_COUNTER_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("occupancy", "active_warps", "waves_per"), "occupancy", "higher"),
    (("dram_bytes", "device_memory_bytes", "bytes_read", "bytes_write"), "dram_bytes", "lower"),
    (("global_load", "read_transactions", "tcc_ea_rdreq"), "global_load_transactions", "lower"),
    (("global_store", "write_transactions", "tcc_ea_wrreq"), "global_store_transactions", "lower"),
    (("l2_hit", "lts__t_sector_hit", "tcp_hit"), "l2_hit_rate", "higher"),
    (("l1_hit", "l1tex__t_sector_hit"), "l1_hit_rate", "higher"),
    (("shared_bank", "lds_bank"), "shared_bank_conflicts", "lower"),
    (("barrier", "wait_inst_barrier"), "barrier_stalls", "lower"),
    (("memory_stall", "long_scoreboard", "alu_stalled"), "memory_stalls", "lower"),
    (("branch_div", "divergent_branch"), "branch_divergence", "lower"),
    (("instructions", "inst_executed", "sq_insts"), "instructions", "lower"),
    (("throughput", "flop", "ipc"), "compute_throughput", "higher"),
    (("gpu_time", "duration"), "instrumented_gpu_time", "lower"),
)


@dataclass(frozen=True)
class NormalizedCounter:
    raw_name: str
    value: float
    unit: str
    category: str
    preferred_direction: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CounterEvidence:
    collector: str
    architecture: str
    device_identity: str
    replay_count: int
    profiler_distorts_timing: bool
    serialized_execution: bool
    counters: tuple[NormalizedCounter, ...]
    source_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GPU_COUNTER_SCHEMA_VERSION,
            **asdict(self),
            "counters": [item.to_dict() for item in self.counters],
            "timing_usable_for_ranking": not self.profiler_distorts_timing and not self.serialized_execution and self.replay_count <= 1,
            "claim_boundary": "counter evidence supports attribution and causal checks; clean uninstrumented timing selects physical winners",
        }


def normalize_gpu_counters(path_or_mapping: Path | dict[str, Any]) -> CounterEvidence:
    if isinstance(path_or_mapping, Path):
        path = path_or_mapping.resolve()
        raw = yaml.safe_load(path.read_text())
        source_hash = canonical_hash({"path": str(path), "contents": raw})
    else:
        raw = path_or_mapping
        source_hash = canonical_hash(raw)
    if not isinstance(raw, dict):
        raise ValueError("GPU counter evidence must be a mapping")
    metrics = raw.get("metrics", {})
    if isinstance(metrics, list):
        entries = [(str(item["name"]), float(item["value"]), str(item.get("unit", "count"))) for item in metrics]
    elif isinstance(metrics, dict):
        entries = []
        for name, value in metrics.items():
            if isinstance(value, dict):
                entries.append((str(name), float(value["value"]), str(value.get("unit", "count"))))
            else:
                entries.append((str(name), float(value), "count"))
    else:
        raise ValueError("counter metrics must be a mapping or list")
    counters = tuple(_normalize_counter(name, value, unit) for name, value, unit in entries)
    replay = int(raw.get("replay_count", 1))
    serialized = bool(raw.get("serialized_execution", False))
    distorted = bool(raw.get("profiler_distorts_timing", replay > 1 or serialized))
    return CounterEvidence(
        str(raw.get("collector", "application-runner")),
        str(raw.get("architecture", "unknown")),
        str(raw.get("device_identity", "unknown")),
        replay,
        distorted,
        serialized,
        counters,
        source_hash,
    )


def _normalize_counter(name: str, value: float, unit: str) -> NormalizedCounter:
    lowered = name.lower()
    for patterns, category, direction in _COUNTER_RULES:
        if any(pattern in lowered for pattern in patterns):
            return NormalizedCounter(name, value, unit, category, direction)
    return NormalizedCounter(name, value, unit, "vendor_specific", "context")


def rank_gpu_candidates(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("GPU ranking manifest must be a mapping")
    runner = raw.get("runner", {})
    command_template = runner.get("command")
    if not isinstance(command_template, list) or not any("{artifact}" in str(item) for item in command_template):
        raise ValueError("GPU runner command must be a list containing {artifact}")
    baseline = raw.get("baseline")
    candidates = raw.get("candidates", [])
    if not isinstance(baseline, dict) or not candidates:
        raise ValueError("GPU ranking requires one baseline and at least one candidate")
    processes = int(runner.get("processes", 10))
    minimum = float(runner.get("minimum_effect_percent", 1.0))
    rounds = int(runner.get("bootstrap_rounds", 2000))
    seed = int(runner.get("seed", 0))
    timeout = float(runner.get("timeout_seconds", 120.0))
    declared_evidence_class = str(runner.get("evidence_class", "unspecified"))
    physical_evidence_class = declared_evidence_class in {"hardware-device-timestamp", "application-device-timestamp"}
    expected_device = str(raw.get("hardware_identity", ""))
    exact_observables = bool(raw.get("contract", {}).get("exact_observables", True))
    if not exact_observables:
        raise ValueError("GPU physical promotion currently requires exact_observables=true")
    baseline_counter = _optional_counter(baseline.get("counter_evidence"), manifest_path.parent)
    results: list[dict[str, Any]] = []
    rng = random.Random(seed)

    def invoke(item: dict[str, Any]) -> dict[str, Any]:
        artifact = _resolve_path(str(item["artifact"]), manifest_path.parent)
        command = [
            str(value).replace("{artifact}", str(artifact)).replace("{candidate_id}", str(item.get("id", "candidate")))
            for value in command_template
        ]
        completed = subprocess.run(
            command,
            cwd=manifest_path.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if completed.returncode:
            raise RuntimeError(f"GPU runner failed: {' '.join(command)}\n{completed.stderr[-3000:]}")
        for line in reversed(completed.stdout.splitlines()):
            if line.strip().startswith("{"):
                payload = json.loads(line)
                required = {"gpu_time_ns", "output_hash", "device_identity"}
                if required - set(payload):
                    raise ValueError(f"GPU runner result is missing {sorted(required - set(payload))}")
                return payload
        raise ValueError("GPU runner emitted no JSON result")

    for candidate_index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError("candidate entries must be mappings")
        baseline_times: list[float] = []
        candidate_times: list[float] = []
        pairs: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []
        device_mismatches: list[dict[str, str]] = []
        evidence_class_mismatches: list[dict[str, str]] = []
        for process_index in range(processes):
            order = ["baseline", "candidate"]
            rng.shuffle(order)
            observed: dict[str, dict[str, Any]] = {}
            for variant in order:
                observed[variant] = invoke(baseline if variant == "baseline" else candidate)
            baseline_result, candidate_result = observed["baseline"], observed["candidate"]
            baseline_times.append(float(baseline_result["gpu_time_ns"]))
            candidate_times.append(float(candidate_result["gpu_time_ns"]))
            if baseline_result["output_hash"] != candidate_result["output_hash"]:
                mismatches.append({"process": process_index, "baseline": baseline_result["output_hash"], "candidate": candidate_result["output_hash"]})
            if baseline_result["device_identity"] != candidate_result["device_identity"] or (expected_device and baseline_result["device_identity"] != expected_device):
                device_mismatches.append({"baseline": str(baseline_result["device_identity"]), "candidate": str(candidate_result["device_identity"]), "expected": expected_device})
            observed_classes = {str(baseline_result.get("evidence_class", "unspecified")), str(candidate_result.get("evidence_class", "unspecified"))}
            if observed_classes != {declared_evidence_class}:
                evidence_class_mismatches.append({"declared": declared_evidence_class, "observed": ",".join(sorted(observed_classes))})
            pairs.append({"process": process_index, "order": order, "baseline": baseline_result, "candidate": candidate_result})
        effects = [(base / selected - 1.0) * 100.0 for base, selected in zip(baseline_times, candidate_times)]
        interval = _bootstrap(effects, seed + candidate_index, rounds)
        effect = statistics.median(effects)
        candidate_counter = _optional_counter(candidate.get("counter_evidence"), manifest_path.parent)
        counter_comparison = _compare_counters(baseline_counter, candidate_counter)
        parity = not mismatches
        identity_ok = not device_mismatches
        evidence_class_ok = physical_evidence_class and not evidence_class_mismatches
        promoted = parity and identity_ok and evidence_class_ok and interval[0] >= minimum
        if mismatches:
            classification = "verification_failed"
        elif device_mismatches:
            classification = "hardware_identity_mismatch"
        elif not evidence_class_ok:
            classification = "simulated_or_unclassified_evidence"
        elif promoted:
            classification = "gpu_candidate_win"
        elif interval[1] < 0:
            classification = "measured_regression"
        else:
            classification = "statistical_tie"
        results.append({
            "candidate_id": str(candidate.get("id", candidate_index)),
            "classification": classification,
            "promotable": promoted,
            "semantic_parity": "PASS" if parity else "FAIL",
            "hardware_identity": "PASS" if identity_ok else "FAIL",
            "physical_evidence_class": "PASS" if evidence_class_ok else "FAIL",
            "declared_evidence_class": declared_evidence_class,
            "effect_percent": effect,
            "effect_95_percent": interval,
            "minimum_effect_percent": minimum,
            "baseline_gpu_time_ns": baseline_times,
            "candidate_gpu_time_ns": candidate_times,
            "output_mismatches": mismatches,
            "device_mismatches": device_mismatches,
            "evidence_class_mismatches": evidence_class_mismatches,
            "pairs": pairs,
            "counter_comparison": counter_comparison,
        })
    winners = sorted((item for item in results if item["promotable"]), key=lambda item: item["effect_percent"], reverse=True)
    report = {
        "schema_version": GPU_RANKING_SCHEMA_VERSION,
        "status": "pass",
        "manifest": str(manifest_path),
        "manifest_hash": canonical_hash(raw),
        "hardware_identity": expected_device,
        "timing_policy": "randomized uninstrumented device timestamp pairs",
        "declared_evidence_class": declared_evidence_class,
        "physical_evidence_class": physical_evidence_class,
        "counter_policy": "attribution and causal support only; profiler timing is excluded from rank",
        "baseline_counter_evidence": baseline_counter.to_dict() if baseline_counter else None,
        "candidates": results,
        "winner": winners[0] if winners else None,
        "promotion": {
            "promotable": bool(winners),
            "reason": "exact parity, identical hardware, and clean timing interval pass" if winners else "no candidate passed all physical gates",
        },
    }
    (output_directory / "gpu-ranking.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _optional_counter(value: Any, root: Path) -> CounterEvidence | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return normalize_gpu_counters(value)
    return normalize_gpu_counters(_resolve_path(str(value), root))


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _compare_counters(baseline: CounterEvidence | None, candidate: CounterEvidence | None) -> dict[str, Any]:
    if baseline is None or candidate is None:
        return {"status": "not_supplied", "comparisons": []}
    identity_ok = baseline.device_identity == candidate.device_identity and baseline.architecture == candidate.architecture
    by_category_baseline = {item.category: item for item in baseline.counters if item.category != "vendor_specific"}
    by_category_candidate = {item.category: item for item in candidate.counters if item.category != "vendor_specific"}
    comparisons = []
    for category in sorted(set(by_category_baseline) & set(by_category_candidate)):
        base, selected = by_category_baseline[category], by_category_candidate[category]
        delta = ((selected.value / base.value) - 1.0) * 100.0 if base.value else None
        favorable = None
        if delta is not None:
            favorable = delta > 0 if selected.preferred_direction == "higher" else delta < 0
        comparisons.append({
            "category": category,
            "baseline": base.to_dict(),
            "candidate": selected.to_dict(),
            "delta_percent": delta,
            "favorable": favorable,
        })
    distorted = baseline.profiler_distorts_timing or candidate.profiler_distorts_timing or baseline.serialized_execution or candidate.serialized_execution
    return {
        "status": "pass" if identity_ok else "hardware_identity_mismatch",
        "hardware_identity_match": identity_ok,
        "profiler_timing_usable_for_ranking": not distorted and baseline.replay_count <= 1 and candidate.replay_count <= 1,
        "profiler_distortion": distorted,
        "comparisons": comparisons,
    }


def _bootstrap(effects: list[float], seed: int, rounds: int) -> list[float]:
    rng = random.Random(seed)
    values = [statistics.median(effects[rng.randrange(len(effects))] for _ in effects) for _ in range(rounds)]
    return [empirical_quantile(values, 0.025), empirical_quantile(values, 0.975)]
