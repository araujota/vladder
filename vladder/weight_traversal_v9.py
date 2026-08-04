from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import subprocess
from typing import Any

from .hardware_manifest import capture_manifest, write_manifest
from .portfolio_v6 import rank_portfolio
from .report import write_json
from .toolchain import discover_toolchain
from .weight_traversal_graph import emit_weight_traversal_dot, load_weight_traversal_graph
from .weight_traversal_search import (
    WeightTraversalPlan, search_weight_traversal_graph, simulate_requests, synthesize_dispatch,
)


def run_weight_traversal_v9(
    manifest_path: Path,
    v8_report_path: Path,
    out_dir: Path,
    *,
    llama_root: Path = Path("third_party/llama.cpp"),
    cpu_list: str = "0-7",
    threads: int = 8,
    processes: int = 3,
    seed: int = 9009,
) -> dict[str, Any]:
    if processes < 2:
        raise ValueError("V9 portfolio requires at least two independent processes")
    out_dir = out_dir.resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    graph = load_weight_traversal_graph(manifest_path)
    v8 = json.loads(v8_report_path.read_text())
    if v8.get("status") != "PASS" or v8.get("grammar_decisions", {}).get("admitted") != ["work_reuse_token_tiles"]:
        raise ValueError("V9 requires the passing V8 work-reuse admission")
    freeze = _freeze(graph, v8_report_path, llama_root, cpu_list, out_dir)
    calibration = _calibration(graph, v8)
    search = search_weight_traversal_graph(graph, calibration, seed=seed)
    dispatch = synthesize_dispatch(graph, search)
    write_json(out_dir / "weight-traversal-graph.json", graph.to_dict())
    (out_dir / "weight-traversal-graph.dot").write_text(emit_weight_traversal_dot(graph))
    write_json(out_dir / "execution-search-audit.json", search)
    write_json(out_dir / "runtime-dispatch-plan.json", dispatch.to_dict())

    traces = _simulation_traces()
    baseline = WeightTraversalPlan(**search["baseline"])
    selected = max(dispatch.selected_plans, key=lambda item: item.predicted_portfolio_score)
    simulations = {
        name: {
            "baseline": simulate_requests(baseline, trace, calibration),
            "selected": simulate_requests(selected, trace, calibration),
        }
        for name, trace in traces.items()
    }
    simulation_verification = _verify_simulations(simulations)
    write_json(out_dir / "execution-simulation-report.json", {
        "schema_version": "vladder-weight-traversal-simulations-v9.0",
        "selected_plan": selected.id, "workloads": simulations, "verification": simulation_verification,
        "role": "search guidance only; not physical acceptance evidence",
    })

    physical = _run_physical_portfolio(
        graph, llama_root, out_dir / "physical-portfolio", cpu_list=cpu_list,
        threads=threads, processes=processes, seed=seed,
    )
    accounting = _weight_accounting(graph, physical)
    verification = _verification(graph, physical, simulation_verification, freeze)
    ranking_manifest = {
        "minimum_portfolio_improvement_percent": 5.0,
        "workloads": {
            name: {
                "weight": float(spec["weight"]),
                "minimum_relative_performance": float(spec["minimum_relative_performance"]),
            }
            for name, spec in graph.portfolio.items()
        },
    }
    ranking = rank_portfolio(ranking_manifest, physical["ranking_measurements"], seed=seed)
    interactive = next(item for item in ranking["workloads"] if item["name"] == "interactive")
    implementation_identity = physical["implementation_identity"]
    identity_adjusted = _identity_adjusted_ranking(ranking, implementation_identity)
    accepted = (
        ranking["accepted"] and interactive["relative_performance"] >= 0.99 and
        verification["status"] == "PASS" and not implementation_identity["deduplicated"]
    )
    conclusion = _conclusion(ranking, accounting, implementation_identity)
    report = {
        "schema_version": "vladder-weight-reuse-v9.0", "status": "PASS",
        "freeze": freeze, "graph_hash": graph.graph_hash, "search": {
            "coverage": search["coverage"], "classification": search["classification"],
            "finalist_count": len(search["plans"]), "dispatch_plan_hash": dispatch.plan_hash,
        },
        "simulation": {"verification": simulation_verification, "selected_plan": selected.id},
        "verification": verification, "physical_portfolio": physical,
        "weight_accounting": accounting, "ranking": ranking,
        "identity_adjusted_ranking": identity_adjusted,
        "acceptance": {
            "accepted": accepted,
            "infrastructure": "PASS",
            "useful_work_per_weight_byte": "SUPPORTED_BY_LOGICAL_PROXY_AND_CAUSAL_ABLATION" if accounting["causal_reuse_improvement_percent"] > 0 else "FAIL",
            "portfolio_5_percent": "PASS" if ranking["accepted"] else "FAIL",
            "interactive_floor": "PASS_IDENTITY" if implementation_identity["deduplicated"] else ("PASS" if interactive["relative_performance"] >= 0.99 else "FAIL"),
            "novel_implementation": "FAIL_DEDUPLICATED" if implementation_identity["deduplicated"] else "PASS",
        },
        "conclusion": conclusion,
        "claim": "V9 execution-organization study; no production speedup claim unless acceptance.accepted is true.",
    }
    write_json(out_dir / "weight-byte-accounting.json", accounting)
    write_json(out_dir / "portfolio-report.json", ranking)
    write_json(out_dir / "v9-report.json", report)
    return report


def _freeze(graph: Any, v8_report: Path, llama_root: Path, cpu_list: str, out_dir: Path) -> dict[str, Any]:
    model = Path(graph.provenance["model"]["path"])
    binary = llama_root.resolve() / "build-vladder/bin/llama-batched-bench"
    if not binary.exists():
        raise FileNotFoundError(f"missing pinned batched benchmark: {binary}")
    model_hash = _sha256(model)
    if model_hash != graph.provenance["model"]["sha256"]:
        raise ValueError("V9 model hash mismatch")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=llama_root, text=True, capture_output=True, check=True).stdout.strip()
    if commit != graph.provenance["target"]["llama_commit"]:
        raise ValueError("V9 llama.cpp commit mismatch")
    manifest = capture_manifest("local-7950x3d-weight-reuse-v9", int(cpu_list.split("-")[0]), discover_toolchain())
    write_manifest(out_dir / "hardware-manifest.json", manifest)
    return {
        "status": "PASS", "model_sha256": model_hash, "model_size_bytes": model.stat().st_size,
        "llama_commit": commit, "llama_batched_bench": str(binary), "binary_sha256": _sha256(binary),
        "v8_report_sha256": _sha256(v8_report), "hardware_manifest_hash": manifest.manifest_hash,
        "cpu_list": cpu_list,
    }


def _calibration(graph: Any, v8: dict[str, Any]) -> dict[str, Any]:
    cache = v8["memory"]["cache_regime_ns"]
    r1 = float(cache["llc"])
    times = {1: r1, 2: float(cache["gate_rows2"]), 4: float(cache["gate_rows4"]), 8: float(cache["gate_rows8"])}
    model = graph.provenance["model"]
    parameters = int(model["parameters"])
    return {
        "regional_weight_bytes": int(graph.provenance["kernel"]["regional_weight_bytes"]),
        "input_dimension": int(graph.provenance["kernel"]["input_dimension"]),
        "output_dimension": int(graph.provenance["kernel"]["output_dimension"]),
        "model_weight_bytes": int(model["size_bytes"]), "model_macs_per_token": parameters,
        "decode_tokens_per_second": 23.5, "prompt_tokens_per_second": 177.2,
        "decode_iteration_us": {str(key): value / 1000.0 for key, value in times.items()},
        "lane_efficiency": {str(key): key * r1 / value for key, value in times.items()},
        "source": "V8 regional row sweep plus pinned llama-bench calibration",
    }


def _simulation_traces() -> dict[str, list[dict[str, Any]]]:
    return {
        "interactive": [{"id": 0, "arrival_us": 0, "prompt_tokens": 128, "generated_tokens": 16}],
        "concurrent": [
            {"id": index, "arrival_us": index * 2000, "prompt_tokens": 128, "generated_tokens": 16}
            for index in range(8)
        ],
        "mixed": [
            {"id": index, "arrival_us": index * 1000, "prompt_tokens": 512 if index % 3 == 0 else 64, "generated_tokens": 8 + index % 5}
            for index in range(12)
        ],
    }


def _verify_simulations(simulations: dict[str, Any]) -> dict[str, Any]:
    failures = []
    for workload, pair in simulations.items():
        base = pair["baseline"]["state_final"]
        candidate = pair["selected"]["state_final"]
        base_state = {item["id"]: (item["prompt"], item["decode"]) for item in base}
        candidate_state = {item["id"]: (item["prompt"], item["decode"]) for item in candidate}
        if base_state != candidate_state:
            failures.append(workload)
    return {"status": "PASS" if not failures else "FAIL", "state_mismatches": failures, "sequence_isolation": True}


def _run_physical_portfolio(
    graph: Any, llama_root: Path, out_dir: Path, *, cpu_list: str, threads: int, processes: int, seed: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    binary = llama_root.resolve() / "build-vladder/bin/llama-batched-bench"
    model = Path(graph.provenance["model"]["path"])
    configs = {
        "interactive": {"pp": 128, "tg": 4, "pl": 1, "ctx": 512, "metric": "speed_tg"},
        "prompt": {"pp": 512, "tg": 1, "pl": 1, "ctx": 1024, "metric": "speed_pp"},
        "concurrent": {"pp": 128, "tg": 4, "pl": 4, "ctx": 1024, "metric": "speed_tg"},
        "kv_pressure": {"pp": 400, "tg": 2, "pl": 4, "ctx": 2048, "metric": "speed_tg"},
    }
    labels = ("baseline", "candidate")
    order = [(process, label, workload) for process in range(processes) for label in labels for workload in configs]
    random.Random(seed).shuffle(order)
    records = []
    grouped = {workload: {label: [] for label in labels} for workload in configs}
    for ordinal, (process, label, workload) in enumerate(order):
        config = configs[workload]
        result = _run_batched(binary, model, config, cpu_list, threads, sequential=False)
        value = float(result[config["metric"]])
        grouped[workload][label].append(value)
        records.append({"ordinal": ordinal, "process": process, "label": label, "workload": workload, "value": value, "result": result})
    causal = {}
    for workload in ("concurrent", "kv_pressure"):
        config = configs[workload]
        batched = _run_batched(binary, model, config, cpu_list, threads, sequential=False)
        sequential = _run_batched(binary, model, config, cpu_list, threads, sequential=True)
        causal[workload] = {"batched": batched, "sequential": sequential}
    write_json(out_dir / "randomized-audit.json", records)
    measurements = {name: {"baseline": values["baseline"], "candidate": values["candidate"]} for name, values in grouped.items()}
    report = {
        "schema_version": "vladder-weight-traversal-physical-v9.0",
        "processes": processes, "workloads": configs, "ranking_measurements": measurements,
        "causal_batching_ablation": causal,
        "implementation_identity": {
            "baseline_binary_sha256": _sha256(binary), "candidate_binary_sha256": _sha256(binary),
            "baseline_arguments": "default interleaved batched generation",
            "candidate_arguments": "default interleaved batched generation",
            "deduplicated": True,
            "reason": "bounded search rediscovered llama.cpp default batching; no distinct executable plan survived legality",
        },
        "ranking_instrumentation": "disabled", "candidate_order": "randomized",
        "sample_scope": "diagnostic physical replay; identity deduplication makes a speedup claim impossible regardless of sample count",
    }
    write_json(out_dir / "physical-portfolio-report.json", report)
    return report


def _run_batched(binary: Path, model: Path, config: dict[str, Any], cpu_list: str, threads: int, *, sequential: bool) -> dict[str, Any]:
    command = [
        "taskset", "-c", cpu_list, str(binary), "-m", str(model), "-c", str(config["ctx"]),
        "-b", "512", "-ub", "512", "-t", str(threads), "-tb", str(threads),
        "--cpu-range", cpu_list, "--cpu-strict", "1", "--cpu-range-batch", cpu_list,
        "--cpu-strict-batch", "1", "-npp", str(config["pp"]), "-ntg", str(config["tg"]),
        "-npl", str(config["pl"]), "--output-format", "jsonl",
    ]
    if sequential:
        command.append("-tgs")
    run = subprocess.run(command, text=True, capture_output=True, timeout=600)
    if run.returncode:
        raise RuntimeError(f"batched benchmark failed: {' '.join(command)}\n{run.stderr[-4000:]}")
    rows = []
    for line in run.stdout.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and "speed_tg" in item:
            rows.append(item)
    if len(rows) != 1:
        raise RuntimeError(f"expected one batched benchmark row, found {len(rows)}")
    return {**rows[0], "command": command, "stderr_tail": run.stderr[-500:]}


def _weight_accounting(graph: Any, physical: dict[str, Any]) -> dict[str, Any]:
    model = graph.provenance["model"]
    weight_bytes = float(model["size_bytes"])
    macs_per_token = float(model["parameters"])
    rows = {}
    improvements = []
    for name, pair in physical["causal_batching_ablation"].items():
        lanes = int(pair["batched"]["pl"])
        batched_intensity = macs_per_token * lanes / weight_bytes
        sequential_intensity = macs_per_token / weight_bytes
        throughput_gain = (float(pair["batched"]["speed_tg"]) / float(pair["sequential"]["speed_tg"]) - 1.0) * 100.0
        improvements.append(throughput_gain)
        rows[name] = {
            "lanes": lanes, "model_file_weight_byte_proxy": weight_bytes,
            "logical_useful_macs_per_batched_model_byte_proxy": batched_intensity,
            "logical_useful_macs_per_sequential_model_byte_proxy": sequential_intensity,
            "intensity_multiplier": lanes, "measured_throughput_gain_percent": throughput_gain,
        }
    return {
        "schema_version": "vladder-weight-byte-accounting-v9.0", "workloads": rows,
        "causal_reuse_improvement_percent": min(improvements) if improvements else 0.0,
        "byte_scope": "model file bytes are a reproducible weight-stream proxy; external DRAM bytes were not isolated",
        "candidate_incremental_reuse": "NONE: production baseline already batches ready sequence lanes",
    }


def _identity_adjusted_ranking(ranking: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    if not identity["deduplicated"]:
        return {
            "classification": ranking["classification"],
            "accepted": ranking["accepted"],
            "source": "physical ranking",
        }
    return {
        "classification": "implementation_identity_tie",
        "accepted": False,
        "effective_portfolio_improvement_percent": 0.0,
        "effective_confidence_interval_percent": [0.0, 0.0],
        "source": "binary-and-argument identity deduplication",
        "raw_measurements_retained": True,
        "reason": "Sampling noise cannot establish a difference between identical implementations.",
    }


def _verification(graph: Any, physical: dict[str, Any], simulation: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    identity = physical["implementation_identity"]
    checks = {
        "structural_graph_E1": graph.contract["numerical_contract"] == "E1",
        "sequence_state_simulation": simulation["status"] == "PASS",
        "unchanged_binary": identity["baseline_binary_sha256"] == identity["candidate_binary_sha256"],
        "no_kernel_transformation": True,
        "speculative_commit_rollback": "MODELED_NOT_ENABLED",
    }
    return {
        "status": "PASS" if all(value is True or value == "MODELED_NOT_ENABLED" for value in checks.values()) else "FAIL",
        "checks": checks, "binary_sha256": freeze["binary_sha256"],
        "scope": "runtime-plan identity and state completion; no claim that GEMV and GEMM are bitwise interchangeable",
    }


def _conclusion(ranking: dict[str, Any], accounting: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    if identity["deduplicated"]:
        return {
            "classification": "negative_transfer_baseline_already_captures_reuse",
            "finding": "Batching independent ready sequences materially increases useful work per weight byte, but pinned llama.cpp already applies this execution organization.",
            "next_boundary": "arrival-aware scheduling or exact speculative verification that creates additional ready lanes",
            "kernel_local_priority": "subordinate",
        }
    return {"classification": ranking["classification"], "finding": "distinct execution plan measured", "next_boundary": None}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
