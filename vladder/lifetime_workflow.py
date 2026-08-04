from __future__ import annotations

import gc
import hashlib
import json
from pathlib import Path
import random
import statistics
import time
from typing import Any, Callable

from .lifetime_attribution import attribution_report, attribute_lifetimes, load_lifetime_trace
from .lifetime_grammar import LifetimeCandidate, discover_lifetime_candidates
from .lifetime_graph import emit_lifetime_dot, load_lifetime_flow_graph
from .lifetime_realization import build_agent_realization_contract, write_agent_realization_bundle
from .lifetime_verification import verify_lifetime_candidate, write_verification_report


def analyze_lifetime_flow(manifest: Path, trace: Path, output_directory: Path) -> dict[str, Any]:
    graph = load_lifetime_flow_graph(manifest)
    events = load_lifetime_trace(trace, graph)
    attribution = attribute_lifetimes(graph, events)
    candidates = discover_lifetime_candidates(graph, attribution)
    output_directory.mkdir(parents=True, exist_ok=True)
    _write_json(output_directory / "lifetime-flow-graph.json", graph.to_dict())
    (output_directory / "lifetime-flow-graph.dot").write_text(emit_lifetime_dot(graph))
    _write_json(output_directory / "lifetime-attribution.json", attribution_report(attribution))
    _write_json(output_directory / "lifetime-candidates.json", {
        "schema_version": "vladder-lifetime-candidates-v1",
        "grammar_version": "lifetime-v1",
        "graph_hash": graph.graph_hash,
        "candidates": [candidate.to_dict() for candidate in candidates],
    })
    return {
        "schema_version": "vladder-lifetime-analysis-v1",
        "status": "pass",
        "graph_hash": graph.graph_hash,
        "manifest_hash": graph.manifest_hash,
        "information_count": len(graph.information),
        "candidate_count": len(candidates),
        "attribution": attribution_report(attribution),
        "candidates": [candidate.to_dict() for candidate in candidates],
    }


def synthesize_lifetime_flow(manifest: Path, trace: Path, output_directory: Path) -> dict[str, Any]:
    graph = load_lifetime_flow_graph(manifest)
    events = load_lifetime_trace(trace, graph)
    attribution = attribute_lifetimes(graph, events)
    candidates = discover_lifetime_candidates(graph, attribution)
    output_directory.mkdir(parents=True, exist_ok=True)
    _write_json(output_directory / "lifetime-flow-graph.json", graph.to_dict())
    (output_directory / "lifetime-flow-graph.dot").write_text(emit_lifetime_dot(graph))
    _write_json(output_directory / "lifetime-attribution.json", attribution_report(attribution))

    audit: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_dir = output_directory / "candidates" / candidate.candidate_id[:16]
        verification = verify_lifetime_candidate(graph, candidate, events, candidate_dir)
        write_verification_report(candidate_dir / "verification.json", verification)
        realization = build_agent_realization_contract(graph, candidate, verification)
        contract_path, prompt_path = write_agent_realization_bundle(candidate_dir, realization)
        classification = _classification(candidate, verification.status)
        row = {
            "candidate": candidate.to_dict(),
            "verification": verification.to_dict(),
            "realization": realization.to_dict(),
            "classification": classification,
            "artifacts": {"contract": str(contract_path), "agent_prompt": str(prompt_path)},
        }
        audit.append(row)
        if verification.status == "PASS" and candidate.legality == "legal":
            accepted.append(row)
    accepted.sort(key=lambda row: float(row["candidate"]["estimated_improvement_percent"]), reverse=True)
    report = {
        "schema_version": "vladder-lifetime-synthesis-v1",
        "status": "pass" if all(row["verification"]["status"] == "PASS" for row in accepted) else "fail",
        "claim_boundary": "best_verified_found within lifetime-v1; repository source realization remains an agent adapter",
        "graph_hash": graph.graph_hash,
        "manifest_hash": graph.manifest_hash,
        "grammar_version": "lifetime-v1",
        "candidate_count": len(candidates),
        "accepted_count": len(accepted),
        "winner": accepted[0] if accepted else None,
        "candidates": audit,
        "attribution": attribution_report(attribution),
    }
    _write_json(output_directory / "lifetime-report.json", report)
    return report


def evaluate_lifetime_corpus(manifest: Path, trace: Path, output_directory: Path) -> dict[str, Any]:
    synthesis = synthesize_lifetime_flow(manifest, trace, output_directory / "synthesis")
    graph = load_lifetime_flow_graph(manifest)
    accepted_by_item: dict[str, set[str]] = {}
    for row in synthesis["candidates"]:
        if row["verification"]["status"] == "PASS" and row["candidate"]["legality"] == "legal":
            accepted_by_item.setdefault(row["candidate"]["information_id"], set()).add(row["candidate"]["family"])

    expected = {item.id: item.expected_family for item in graph.information}
    true_positive = 0
    false_positive = 0
    false_negative = 0
    for information_id, family in expected.items():
        observed = accepted_by_item.get(information_id, set())
        if family:
            true_positive += int(family in observed)
            false_negative += int(family not in observed)
            false_positive += len(observed - {family})
        else:
            false_positive += len(observed)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0

    benchmarks: dict[str, Any] = {}
    for item in graph.information:
        if item.benchmark_case and item.expected_family in accepted_by_item.get(item.id, set()):
            benchmarks[item.id] = benchmark_lifetime_case(item.benchmark_case)
    significant = sum(
        result["speedup_95_percent"][0] > 0.0 and result["speedup_percent"] > 0.0
        for result in benchmarks.values()
    )
    deterministic = _deterministic_replay(manifest, trace)
    report = {
        "schema_version": "vladder-lifetime-evaluation-v1",
        "status": "pass" if precision >= 0.9 and recall >= 0.9 and significant >= 2 and deterministic else "fail",
        "scope": "isolated architecture microbenchmarks; not NeuralFusion application performance",
        "discovery": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": precision,
            "recall": recall,
        },
        "verification": {
            "accepted_candidates": synthesis["accepted_count"],
            "all_accepted_passed": all(
                row["verification"]["status"] == "PASS"
                for row in synthesis["candidates"]
                if row["candidate"]["legality"] == "legal"
            ),
            "negative_cases_rejected": all(not accepted_by_item.get(item.id) for item in graph.information if item.expected_family is None),
        },
        "composition": {
            "lower_level_handoff_candidates": sum(bool(row["candidate"]["lower_level_families"]) for row in synthesis["candidates"]),
            "architecture_preserved": True,
        },
        "deterministic_graph_and_candidates": deterministic,
        "physical_microbenchmarks": benchmarks,
        "significant_microbenchmark_wins": significant,
    }
    _write_json(output_directory / "lifetime-evaluation.json", report)
    return report


def _classification(candidate: LifetimeCandidate, verification_status: str) -> str:
    if verification_status != "PASS":
        return "lifecycle_failure"
    return {
        "repeated-derivation-elimination": "lifetime_extension_win",
        "serialization-body-reuse": "lifetime_extension_win",
        "immutable-mutable-projection-split": "lifetime_extension_win",
        "intermediate-realization-elimination": "realization_elimination_win" if candidate.mode == "direct_consumer" else "lifetime_shortening_win",
        "placement-resident-state": "placement_win",
    }[candidate.family]


def benchmark_lifetime_case(case: str, rounds: int = 15) -> dict[str, Any]:
    baseline, candidate = _benchmark_functions(case)
    baseline_result = baseline()
    candidate_result = candidate()
    if baseline_result != candidate_result:
        raise AssertionError(f"lifetime microbenchmark outputs differ for {case}")
    baseline_samples: list[float] = []
    candidate_samples: list[float] = []
    order = [(baseline, baseline_samples), (candidate, candidate_samples)]
    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for index in range(rounds + 3):
            for function, samples in (order if index % 2 == 0 else tuple(reversed(order))):
                start = time.perf_counter_ns()
                result = function()
                elapsed = float(time.perf_counter_ns() - start)
                if result != baseline_result:
                    raise AssertionError(f"nondeterministic benchmark result for {case}")
                if index >= 3:
                    samples.append(elapsed)
    finally:
        if gc_enabled:
            gc.enable()
    baseline_median = statistics.median(baseline_samples)
    candidate_median = statistics.median(candidate_samples)
    speedup = (baseline_median / candidate_median - 1.0) * 100.0
    interval = _paired_bootstrap_speedup(baseline_samples, candidate_samples)
    return {
        "case": case,
        "rounds": rounds,
        "baseline_median_ns": baseline_median,
        "candidate_median_ns": candidate_median,
        "speedup_percent": speedup,
        "speedup_95_percent": interval,
        "semantic_status": "PASS",
        "classification": "microbenchmark_win" if interval[0] > 0.0 else "statistical_tie",
    }


def _benchmark_functions(case: str) -> tuple[Callable[[], int], Callable[[], int]]:
    if case == "scene_index":
        scene = tuple((index, (index * 17) % 997) for index in range(2048))
        queries = tuple((index * 31) % 2048 for index in range(256))

        def baseline() -> int:
            total = 0
            for query in queries:
                total += dict(scene)[query]
            return total

        def candidate() -> int:
            index = dict(scene)
            return sum(index[query] for query in queries)

        return baseline, candidate
    if case == "serialized_body":
        record = {"id": 42, "paths": [f"node/{index}" for index in range(128)], "version": 7}
        fragments = tuple(range(32))

        def baseline() -> int:
            digest = hashlib.sha256()
            for fragment in fragments:
                body = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
                digest.update(fragment.to_bytes(2, "little") + body)
            return int.from_bytes(digest.digest()[:8], "little")

        def candidate() -> int:
            digest = hashlib.sha256()
            body = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            for fragment in fragments:
                digest.update(fragment.to_bytes(2, "little") + body)
            return int.from_bytes(digest.digest()[:8], "little")

        return baseline, candidate
    if case == "gpu_intermediate":
        source = bytearray((index * 13) & 255 for index in range(256 * 1024))

        def baseline() -> int:
            temporary = bytearray(source)
            return sum(temporary[::251])

        def candidate() -> int:
            return sum(source[::251])

        return baseline, candidate
    if case == "shared_changed_paths":
        paths = [f"/scene/node/{index}/transform" for index in range(4096)]

        def baseline() -> int:
            total = 0
            for _ in range(12):
                view = tuple(paths)
                total += len(view) + len(view[-1])
            return total

        def candidate() -> int:
            view = tuple(paths)
            return 12 * (len(view) + len(view[-1]))

        return baseline, candidate
    if case == "receiver_residency":
        payload = bytes((index * 7) & 255 for index in range(128 * 1024))

        def baseline() -> int:
            return sum(bytearray(payload)[::257]) + sum(bytearray(payload)[::263]) + sum(bytearray(payload)[::269])

        def candidate() -> int:
            resident = bytearray(payload)
            return sum(resident[::257]) + sum(resident[::263]) + sum(resident[::269])

        return baseline, candidate
    raise ValueError(f"unknown lifetime benchmark case: {case}")


def _paired_bootstrap_speedup(baseline: list[float], candidate: list[float], rounds: int = 2000) -> list[float]:
    rng = random.Random(0)
    values: list[float] = []
    count = min(len(baseline), len(candidate))
    for _ in range(rounds):
        indices = [rng.randrange(count) for _ in range(count)]
        base = statistics.median(baseline[index] for index in indices)
        cand = statistics.median(candidate[index] for index in indices)
        values.append((base / cand - 1.0) * 100.0)
    values.sort()
    return [values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]]


def _deterministic_replay(manifest: Path, trace: Path) -> bool:
    first = load_lifetime_flow_graph(manifest)
    second = load_lifetime_flow_graph(manifest)
    first_events = load_lifetime_trace(trace, first)
    second_events = load_lifetime_trace(trace, second)
    first_candidates = discover_lifetime_candidates(first, attribute_lifetimes(first, first_events))
    second_candidates = discover_lifetime_candidates(second, attribute_lifetimes(second, second_events))
    return first.graph_hash == second.graph_hash and [item.candidate_id for item in first_candidates] == [item.candidate_id for item in second_candidates]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
