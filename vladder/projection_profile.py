from __future__ import annotations

from dataclasses import dataclass
import re
import statistics
from typing import Any


PROJECTION_RE = re.compile(
    r"^VLADDER_PROJECTION\|name=(?P<name>[^|]*)\|backend=(?P<backend>[^|]+)\|weight_type=(?P<weight_type>[^|]+)\|activation_type=(?P<activation_type>[^|]+)"
    r"\|input=(?P<input>\d+)\|outputs=(?P<outputs>\d+)\|tokens=(?P<tokens>\d+)"
    r"\|prep_cycles=(?P<prep_cycles>\d+)\|prep_us=(?P<prep_us>\d+)"
    r"\|sync_cycles=(?P<sync_cycles>\d+)\|sync_us=(?P<sync_us>\d+)"
    r"\|fused_cycles=(?P<fused_cycles>\d+)\|fused_us=(?P<fused_us>\d+)$"
)


@dataclass(frozen=True)
class ProjectionSubstageSample:
    name: str
    category: str
    backend: str
    weight_type: str
    activation_type: str
    input: int
    outputs: int
    tokens: int
    prep_cycles: int
    prep_us: int
    sync_cycles: int
    sync_us: int
    fused_cycles: int
    fused_us: int


def parse_projection_profile(log: str) -> dict[str, Any]:
    samples: list[ProjectionSubstageSample] = []
    for line in log.splitlines():
        match = PROJECTION_RE.match(line)
        if not match:
            continue
        values = match.groupdict()
        samples.append(ProjectionSubstageSample(
            values["name"], _category(values["name"]), values["backend"], values["weight_type"], values["activation_type"],
            int(values["input"]), int(values["outputs"]), int(values["tokens"]),
            int(values["prep_cycles"]), int(values["prep_us"]), int(values["sync_cycles"]),
            int(values["sync_us"]), int(values["fused_cycles"]), int(values["fused_us"]),
        ))
    if not samples:
        raise ValueError("projection profile contained no Q4_K samples")
    regimes: dict[str, Any] = {}
    for token_count in sorted({sample.tokens for sample in samples}):
        selected = [sample for sample in samples if sample.tokens == token_count]
        phases = "single_token_decode" if token_count == 1 else "prefill_or_token_tile"
        category_report: dict[str, Any] = {}
        for category in sorted({sample.category for sample in selected}):
            group = [sample for sample in selected if sample.category == category]
            category_report[category] = _summary(group)
        regimes[str(token_count)] = {
            "phase_class": phases,
            "sample_count": len(selected),
            "projection_categories": category_report,
            "all_projections": _summary(selected),
        }
    return {
        "schema_version": "vladder-projection-profile-v5.0",
        "measurement_class": "instrumented synchronized substage attribution; not ranking evidence",
        "sample_count": len(samples),
        "backends": sorted({sample.backend for sample in samples}),
        "token_count_regimes": regimes,
        "limitations": [
            "activation preparation is thread-0 conversion time, not the maximum across workers",
            "synchronization is thread-0 wait at the preparation barrier",
            "weight load, metadata/scale decode, unpacking, dot product, and accumulation remain one fused region",
            "the profiler adds barriers to the normally dispatched backend; it must be disabled during throughput ranking",
        ],
    }


def _summary(samples: list[ProjectionSubstageSample]) -> dict[str, Any]:
    prep = [sample.prep_us for sample in samples]
    sync = [sample.sync_us for sample in samples]
    fused = [sample.fused_us for sample in samples]
    total = [a + b + c for a, b, c in zip(prep, sync, fused)]
    total_sum = sum(total)
    return {
        "count": len(samples),
        "activation_prepare_us": _stats(prep),
        "prepare_sync_us": _stats(sync),
        "fused_weight_decode_dot_accumulate_us": _stats(fused),
        "instrumented_total_us": _stats(total),
        "summed_us": {"activation_prepare": sum(prep), "prepare_sync": sum(sync), "fused_weight_decode_dot_accumulate": sum(fused), "total": total_sum},
        "fraction": {
            "activation_prepare": sum(prep) / total_sum if total_sum else 0.0,
            "prepare_sync": sum(sync) / total_sum if total_sum else 0.0,
            "fused_weight_decode_dot_accumulate": sum(fused) / total_sum if total_sum else 0.0,
        },
    }


def _stats(values: list[int]) -> dict[str, float]:
    return {"median": statistics.median(values), "mean": statistics.fmean(values), "min": min(values), "max": max(values)}


def _category(name: str) -> str:
    if re.match(r"ffn_(?:gate|up)-\d+$", name):
        return "ffn_gate_up"
    if re.match(r"ffn_out-\d+$", name):
        return "ffn_down"
    if re.match(r"(?:Qcur|Kcur|Vcur)-\d+$", name):
        return "qkv"
    if name == "result_output":
        return "logits"
    return "attention_output_or_other"
