from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import statistics
from typing import Any


PROFILE_RE = re.compile(r"^VLADDER_PROFILE\|node=(?P<node>\d+)\|op=(?P<op>[^|]+)\|fused=(?P<fused>\d+)\|cycles=(?P<cycles>\d+)\|us=(?P<us>\d+)\|name=(?P<name>.*)$")


@dataclass(frozen=True)
class ProfileSample:
    node: int
    op: str
    fused: int
    microseconds: int
    name: str


def parse_ggml_profile(log: str, normalized_graph: dict[str, Any], drop_first: bool = True, expected_samples: int | None = None) -> dict[str, Any]:
    graphs: list[list[ProfileSample]] = []
    current: list[ProfileSample] | None = None
    for line in log.splitlines():
        if line.startswith("VLADDER_PROFILE|graph_begin"):
            current = []
        elif line == "VLADDER_PROFILE|graph_end":
            if current is not None:
                graphs.append(current)
            current = None
        elif current is not None:
            match = PROFILE_RE.match(line)
            if match:
                current.append(ProfileSample(
                    int(match.group("node")), match.group("op"), int(match.group("fused")),
                    int(match.group("us")), match.group("name"),
                ))
    if expected_samples is not None and len(graphs) >= expected_samples:
        graphs = graphs[-expected_samples:]
        drop_first = False
    elif drop_first and len(graphs) > 1:
        graphs = graphs[1:]
    if not graphs:
        raise ValueError("profile log contained no complete graph samples")
    node_metadata = {int(node["index"]): node for node in normalized_graph["nodes"] if node["kind"] == "compute"}
    category_samples: dict[str, list[float]] = {}
    totals: list[float] = []
    executed_nodes: list[int] = []
    for graph in graphs:
        categories: dict[str, float] = {}
        for sample in graph:
            category = _category(sample, node_metadata.get(sample.node, {}))
            categories[category] = categories.get(category, 0.0) + sample.microseconds
        total = sum(categories.values())
        totals.append(total)
        executed_nodes.append(len(graph))
        for category in set(category_samples) | set(categories):
            category_samples.setdefault(category, []).append(categories.get(category, 0.0))
    category_report = {}
    median_total = statistics.median(totals)
    for category, values in sorted(category_samples.items()):
        median_us = statistics.median(values)
        category_report[category] = {
            "median_us": median_us,
            "mean_us": statistics.fmean(values),
            "median_decode_fraction": median_us / median_total if median_total else 0.0,
            "samples_us": values,
        }
    target_categories = {
        "residual_norm_fused", "residual", "norm", "qk_norm", "qkv_projection",
        "ffn_projection", "attention_output_projection", "activation", "rope",
    }
    target_values = [sum(category_samples.get(category, [0.0] * len(graphs))[index] for category in target_categories) for index in range(len(graphs))]
    target_median = statistics.median(target_values)
    return {
        "schema_version": "vladder-ggml-profile-v4.0",
        "graph_samples": len(graphs),
        "expected_samples": expected_samples,
        "drop_first_warmup": drop_first,
        "executed_nodes_per_graph": executed_nodes,
        "exclusive_graph_us": {"median": median_total, "mean": statistics.fmean(totals), "samples": totals},
        "categories": category_report,
        "stage1_to_stage3_addressable": {
            "categories": sorted(target_categories),
            "median_us": target_median,
            "median_decode_fraction": target_median / median_total if median_total else 0.0,
            "addressable_coverage_25pct": bool(median_total and target_median / median_total >= 0.25),
            "synthesized_candidate_coverage": None,
            "research_milestone_25pct": False,
            "milestone_reason": "coverage is baseline attribution; no compiled V4 candidate spans this region yet",
            "measurement_class": "instrumented synchronized exclusive wall time",
        },
        "limitations": [
            "profiling adds a second barrier and logging outside each timed node region",
            "exclusive node time is suitable for attribution but not tokens-per-second ranking",
            "cache and DRAM bytes require separate counter evidence",
        ],
    }


def _category(sample: ProfileSample, metadata: dict[str, Any]) -> str:
    shape = metadata.get("shape", [])
    if sample.op == "ADD" and sample.fused > 0:
        return "residual_norm_fused"
    if sample.op == "MUL_MAT":
        if re.match(r"(?:Qcur|Kcur|Vcur)-\d+$", sample.name):
            return "qkv_projection"
        if re.match(r"ffn_(?:gate|up|out)-\d+$", sample.name):
            return "ffn_projection"
        if sample.name == "result_output":
            return "logits_projection"
        return "attention_output_projection"
    if sample.op == "RMS_NORM":
        return "qk_norm" if shape and shape[0] == 128 else "norm"
    mapping = {
        "ROPE": "rope", "FLASH_ATTN_EXT": "attention", "GLU": "activation",
        "SET_ROWS": "kv_state_write", "GET_ROWS": "embedding_lookup", "ADD": "residual",
        "MUL": "elementwise", "CPY": "copy", "CONT": "copy", "SOFT_MAX": "softmax",
    }
    return mapping.get(sample.op, "other")
