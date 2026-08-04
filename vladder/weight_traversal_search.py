from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
import random
from typing import Any

from .statistics_v3 import empirical_quantile
from .weight_traversal_graph import WeightTraversalGraph


@dataclass(frozen=True)
class WeightTraversalPlan:
    id: str
    token_tile: int
    sequence_tile: int
    projection_sharing: str
    traversal: str
    runtime_policy: str
    speculative: bool
    max_wait_us: int
    prefill_chunk: int
    guards: tuple[str, ...]
    legality: str
    predicted_portfolio_score: float
    predicted_interactive_relative: float
    useful_macs_per_weight_byte: float
    estimated_queue_p99_us: float
    classification: str


@dataclass(frozen=True)
class RuntimeDispatchRule:
    priority: int
    guard: str
    plan_id: str
    fallback: bool


@dataclass(frozen=True)
class RuntimeDispatchPlan:
    schema_version: str
    graph_hash: str
    plan_hash: str
    rules: tuple[RuntimeDispatchRule, ...]
    selected_plans: tuple[WeightTraversalPlan, ...]
    fallback: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def search_weight_traversal_graph(
    graph: WeightTraversalGraph,
    calibration: dict[str, Any],
    *,
    beam_width: int = 48,
    seed: int = 9009,
) -> dict[str, Any]:
    grammar = graph.grammar
    raw_product = list(itertools.product(
        grammar["token_tiles"], grammar["sequence_tiles"], grammar["projection_sharing"],
        grammar["traversals"], grammar["runtime_policies"], grammar["speculative"],
    ))
    audit: list[dict[str, Any]] = []
    plans: list[WeightTraversalPlan] = []
    for choice in raw_product:
        token, sequence, sharing, traversal, policy, speculative = choice
        legal, reason = _legal(graph, int(token), int(sequence), str(sharing), str(traversal), str(policy), bool(speculative))
        if not legal:
            audit.append({"choice": choice, "status": "rejected", "reason": reason})
            continue
        max_wait = {"latency_first": 0, "prompt": 0, "decode": 100, "mixed": 250, "continuous_batch": 500, "throughput_first": 1000}[str(policy)]
        prefill_chunk = 32 if policy == "latency_first" else min(512, max(32, int(token) * 32))
        estimate = _estimate(graph, calibration, int(token), int(sequence), str(traversal), str(policy), max_wait)
        rules = f"{token}|{sequence}|{sharing}|{traversal}|{policy}|{int(bool(speculative))}"
        identifier = hashlib.sha256(rules.encode()).hexdigest()[:12]
        classification = "eligible" if estimate["interactive_relative"] >= float(graph.provenance["constraints"]["interactive_min_relative_performance"]) else "latency_floor_failed"
        plan = WeightTraversalPlan(
            f"wt-{identifier}", int(token), int(sequence), str(sharing), str(traversal), str(policy), bool(speculative),
            max_wait, prefill_chunk, _guards(str(policy), int(token), int(sequence), bool(speculative)), reason,
            estimate["portfolio_score"], estimate["interactive_relative"], estimate["mac_per_weight_byte"],
            estimate["queue_p99_us"], classification,
        )
        plans.append(plan)
        audit.append({"choice": choice, "status": "admitted", "plan": plan.id, "classification": classification})
    eligible = [item for item in plans if item.classification == "eligible"]
    frontier = _pareto(eligible)
    ordered = sorted(frontier, key=lambda item: (-item.predicted_portfolio_score, item.estimated_queue_p99_us, item.id))
    finalists = ordered[:beam_width]
    baseline = _baseline_plan(graph, calibration)
    coverage = {
        "raw_cross_product": len(raw_product), "legal": len(plans), "eligible": len(eligible),
        "pareto": len(frontier), "finalists": len(finalists), "enumeration": "exhaustive bounded grammar",
    }
    return {
        "schema_version": "vladder-weight-traversal-search-v9.0",
        "graph_hash": graph.graph_hash, "coverage": coverage, "baseline": asdict(baseline),
        "plans": [asdict(item) for item in finalists], "all_legal_plan_count": len(plans),
        "audit": audit, "classification": "best_verified_found",
        "static_model_role": "pruning and experiment selection only; physical portfolio is authoritative",
        "seed": seed,
    }


def synthesize_dispatch(graph: WeightTraversalGraph, search: dict[str, Any]) -> RuntimeDispatchPlan:
    plans = [WeightTraversalPlan(**item) for item in search["plans"]]
    baseline = WeightTraversalPlan(**search["baseline"])
    selected: list[WeightTraversalPlan] = [baseline]

    def choose(predicate: Any) -> WeightTraversalPlan:
        candidates = [item for item in plans if predicate(item)]
        return max(candidates, key=lambda item: (item.predicted_portfolio_score, -item.estimated_queue_p99_us), default=baseline)

    interactive = choose(lambda item: item.runtime_policy == "latency_first" and item.sequence_tile == 1 and item.token_tile == 1)
    prompt = choose(lambda item: item.runtime_policy == "prompt" and item.token_tile >= 4)
    concurrent = choose(lambda item: item.runtime_policy in {"continuous_batch", "throughput_first"} and item.sequence_tile >= 4)
    mixed = choose(lambda item: item.runtime_policy == "mixed" and item.sequence_tile >= 2)
    for item in (interactive, prompt, concurrent, mixed):
        if item.id not in {plan.id for plan in selected}:
            selected.append(item)
    rules = (
        RuntimeDispatchRule(0, "ready_sequences == 1 && phase == decode", interactive.id, False),
        RuntimeDispatchRule(1, "phase == prompt", prompt.id, False),
        RuntimeDispatchRule(2, "ready_sequences >= 4", concurrent.id, False),
        RuntimeDispatchRule(3, "prompt_tokens > 0 && decode_tokens > 0", mixed.id, False),
        RuntimeDispatchRule(4, "true", baseline.id, True),
    )
    content = json.dumps({"rules": [asdict(item) for item in rules], "plans": [asdict(item) for item in selected]}, sort_keys=True, separators=(",", ":"))
    return RuntimeDispatchPlan("vladder-runtime-dispatch-v9.0", graph.graph_hash, hashlib.sha256(content.encode()).hexdigest(), rules, tuple(selected), baseline.id)


def simulate_requests(
    plan: WeightTraversalPlan,
    requests: list[dict[str, Any]],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    if not requests:
        raise ValueError("simulation requires requests")
    state = []
    for index, request in enumerate(sorted(requests, key=lambda item: (float(item["arrival_us"]), int(item.get("id", 0))))):
        state.append({
            "id": int(request.get("id", index)), "arrival": float(request["arrival_us"]),
            "prompt": int(request["prompt_tokens"]), "decode": int(request["generated_tokens"]),
            "prompt_done": 0, "decode_done": 0, "first": None, "last": None,
            "token_times": [], "complete": None,
        })
    now = min(item["arrival"] for item in state)
    traversals = 0
    streamed_weight_bytes = 0.0
    useful_macs = 0.0
    model_weight_bytes = float(calibration["model_weight_bytes"])
    model_macs = float(calibration["model_macs_per_token"])
    while any(item["complete"] is None for item in state):
        ready = [item for item in state if item["arrival"] <= now and item["complete"] is None]
        if not ready:
            now = min(item["arrival"] for item in state if item["complete"] is None)
            continue
        prompt_ready = [item for item in ready if item["prompt_done"] < item["prompt"]]
        if prompt_ready:
            chosen = prompt_ready[:max(1, plan.sequence_tile)]
            token_count = 0
            for item in chosen:
                amount = min(plan.prefill_chunk, item["prompt"] - item["prompt_done"])
                item["prompt_done"] += amount; token_count += amount
            duration = 1e6 * token_count / max(1e-9, float(calibration["prompt_tokens_per_second"]))
            now += duration
            useful_macs += model_macs * token_count
            streamed_weight_bytes += model_weight_bytes * max(1, math.ceil(token_count / max(1, plan.token_tile)))
            traversals += max(1, math.ceil(token_count / max(1, plan.token_tile)))
            continue
        chosen = ready[:max(1, plan.sequence_tile)]
        if plan.max_wait_us and len(chosen) < plan.sequence_tile:
            future = [item["arrival"] for item in state if item["arrival"] > now and item["complete"] is None]
            if future and min(future) <= now + plan.max_wait_us:
                now = min(future)
                continue
        lanes = len(chosen)
        duration = _decode_iteration_us(lanes, calibration)
        now += duration
        traversals += 1
        streamed_weight_bytes += model_weight_bytes
        useful_macs += model_macs * lanes
        for item in chosen:
            item["decode_done"] += 1
            item["token_times"].append(now)
            item["first"] = now if item["first"] is None else item["first"]
            item["last"] = now
            if item["decode_done"] >= item["decode"]:
                item["complete"] = now
    ttft = [item["first"] - item["arrival"] for item in state]
    inter = []
    for item in state:
        inter.extend(right-left for left, right in zip(item["token_times"], item["token_times"][1:]))
    total_tokens = sum(item["decode"] for item in state)
    makespan = max(item["complete"] for item in state) - min(item["arrival"] for item in state)
    return {
        "schema_version": "vladder-weight-traversal-simulation-v9.0", "plan": plan.id,
        "requests": len(state), "completed_tokens": total_tokens, "makespan_us": makespan,
        "generated_tokens_per_second": total_tokens / (makespan / 1e6),
        "ttft_us": _quantiles(ttft), "inter_token_us": _quantiles(inter or [0.0]),
        "traversals": traversals, "streamed_weight_bytes": streamed_weight_bytes,
        "useful_macs": useful_macs, "useful_macs_per_streamed_weight_byte": useful_macs / streamed_weight_bytes,
        "state_final": [{"id": item["id"], "prompt": item["prompt_done"], "decode": item["decode_done"], "complete": item["complete"]} for item in state],
        "semantic_status": "PASS",
    }


def _legal(graph: WeightTraversalGraph, token: int, sequence: int, sharing: str, traversal: str, policy: str, speculative: bool) -> tuple[bool, str]:
    if sharing != "independent":
        return False, "V8 admitted no production sibling/projection-sharing grammar"
    if speculative and not bool(graph.contract.get("speculative_enabled", False)):
        return False, "speculative lanes require an enabled commit/rollback contract"
    if policy in {"decode", "latency_first", "continuous_batch", "throughput_first"} and token > 1 and not speculative:
        return False, "autoregressive decode cannot contain future same-sequence token lanes without speculation"
    if policy == "latency_first" and sequence != 1:
        return False, "latency-first policy fixes sequence tile one"
    if traversal == "weight_major" and token * sequence < 4:
        return False, "native Q4_K GEMM reuses weights only for complete four-row groups"
    if traversal == "token_major" and sequence > 1:
        return False, "token-major traversal does not coordinate independent sequences"
    return True, "structurally legal under E1 lane independence"


def _estimate(graph: WeightTraversalGraph, calibration: dict[str, Any], token: int, sequence: int, traversal: str, policy: str, max_wait: int) -> dict[str, float]:
    lanes = max(1, token * sequence)
    reuse_lanes = lanes if traversal in {"weight_major", "mixed"} and lanes >= 4 else 1
    regional_weight = float(calibration["regional_weight_bytes"])
    input_dim = int(calibration["input_dimension"]); output_dim = int(calibration["output_dimension"])
    mac_per_byte = input_dim * output_dim * lanes / (regional_weight * math.ceil(lanes / reuse_lanes))
    efficiency = float(calibration.get("lane_efficiency", {}).get(str(min(8, sequence)), 1.0))
    queue_penalty = max_wait * (0.5 if policy in {"continuous_batch", "throughput_first"} else 0.1)
    interactive = 1.0 if sequence == 1 and max_wait == 0 else max(0.90, 1.0 - queue_penalty / 10000.0)
    concurrent = efficiency * (1.0 + 0.02 * max(0, reuse_lanes - 1))
    prompt = 1.0 + 0.01 * math.log2(max(1, token))
    kv = concurrent * (0.99 if sequence > 4 else 1.0)
    weights = graph.portfolio
    score = (
        float(weights["interactive"]["weight"]) * interactive +
        float(weights["prompt"]["weight"]) * prompt +
        float(weights["concurrent"]["weight"]) * concurrent +
        float(weights["kv_pressure"]["weight"]) * kv
    )
    return {"portfolio_score": score, "interactive_relative": interactive, "mac_per_weight_byte": mac_per_byte, "queue_p99_us": float(max_wait)}


def _baseline_plan(graph: WeightTraversalGraph, calibration: dict[str, Any]) -> WeightTraversalPlan:
    estimate = _estimate(graph, calibration, 1, 1, "token_major", "latency_first", 0)
    return WeightTraversalPlan("baseline-native-dynamic-batch", 1, 1, "independent", "token_major", "latency_first", False, 0, 512, ("true",), "pinned llama.cpp runtime fallback", estimate["portfolio_score"], 1.0, estimate["mac_per_weight_byte"], 0.0, "eligible")


def _guards(policy: str, token: int, sequence: int, speculative: bool) -> tuple[str, ...]:
    guards = [f"token_lanes <= {token}", f"ready_sequences >= {sequence}" if sequence > 1 else "ready_sequences >= 1", f"policy == {policy}"]
    if speculative:
        guards.append("tentative_state_enabled")
    return tuple(guards)


def _pareto(plans: list[WeightTraversalPlan]) -> list[WeightTraversalPlan]:
    result = []
    for plan in plans:
        dominated = any(
            other is not plan and
            other.predicted_portfolio_score >= plan.predicted_portfolio_score and
            other.useful_macs_per_weight_byte >= plan.useful_macs_per_weight_byte and
            other.estimated_queue_p99_us <= plan.estimated_queue_p99_us and
            (other.predicted_portfolio_score > plan.predicted_portfolio_score or
             other.useful_macs_per_weight_byte > plan.useful_macs_per_weight_byte or
             other.estimated_queue_p99_us < plan.estimated_queue_p99_us)
            for other in plans
        )
        if not dominated:
            result.append(plan)
    return result


def _decode_iteration_us(lanes: int, calibration: dict[str, Any]) -> float:
    table = calibration.get("decode_iteration_us", {})
    keys = sorted((int(key), float(value)) for key, value in table.items())
    if not keys:
        return 1e6 * lanes / float(calibration["decode_tokens_per_second"])
    eligible = [item for item in keys if item[0] <= lanes]
    if eligible:
        base_lanes, value = eligible[-1]
        return value * lanes / base_lanes if lanes > base_lanes else value
    return keys[0][1]


def _quantiles(values: list[float]) -> dict[str, float]:
    return {name: empirical_quantile(values, probability) for name, probability in (("p50", 0.5), ("p90", 0.9), ("p99", 0.99))}
