from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable, Sequence


@dataclass(frozen=True)
class TokenSuiteContract:
    model: str
    quantization: str
    head_dimension: int
    context_lengths: tuple[int, ...]
    vocabulary_size: int
    tolerance_abs: float
    tolerance_rel: float
    deterministic: bool
    sampling_seed_semantics: str
    nan_policy: str


def rope_qk_reference(
    q: Sequence[float], k: Sequence[float], cos: Sequence[float], sin: Sequence[float]
) -> tuple[list[float], list[float]]:
    if len(q) != len(k) or len(q) % 2 or len(cos) * 2 != len(q) or len(sin) != len(cos):
        raise ValueError("RoPE requires equal even Q/K vectors and one trig pair per complex pair")
    q_out = [0.0] * len(q)
    k_out = [0.0] * len(k)
    for pair in range(len(cos)):
        i = pair * 2
        c, s = cos[pair], sin[pair]
        q_out[i], q_out[i + 1] = q[i] * c - q[i + 1] * s, q[i] * s + q[i + 1] * c
        k_out[i], k_out[i + 1] = k[i] * c - k[i + 1] * s, k[i] * s + k[i + 1] * c
    return q_out, k_out


def quantized_gemv_epilogue_reference(
    weights: Sequence[int], scales: Sequence[float], x: Sequence[float], block: int,
    bias: float = 0.0, gate: float = 1.0,
) -> float:
    if block <= 0 or len(weights) != len(x) or len(weights) % block or len(scales) != len(weights) // block:
        raise ValueError("invalid quantized block geometry")
    accumulator = 0.0
    for i, (weight, value) in enumerate(zip(weights, x)):
        accumulator += float(weight) * scales[i // block] * value
    activated = accumulator + bias
    return (activated / (1.0 + math.exp(-activated))) * gate


def attention_materialized_reference(
    q: Sequence[float], keys: Sequence[Sequence[float]], values: Sequence[Sequence[float]], scale: float
) -> list[float]:
    _validate_attention(q, keys, values)
    scores = [sum(a * b for a, b in zip(q, key)) * scale for key in keys]
    maximum = max(scores)
    weights = [math.exp(score - maximum) for score in scores]
    denominator = sum(weights)
    return [sum(weight * value[d] for weight, value in zip(weights, values)) / denominator for d in range(len(values[0]))]


def attention_online_reference(
    q: Sequence[float], keys: Sequence[Sequence[float]], values: Sequence[Sequence[float]], scale: float
) -> list[float]:
    _validate_attention(q, keys, values)
    maximum = -math.inf
    denominator = 0.0
    output = [0.0] * len(values[0])
    for key, value in zip(keys, values):
        score = sum(a * b for a, b in zip(q, key)) * scale
        next_maximum = max(maximum, score)
        old_weight = 0.0 if maximum == -math.inf else math.exp(maximum - next_maximum)
        new_weight = math.exp(score - next_maximum)
        denominator = denominator * old_weight + new_weight
        for d in range(len(output)):
            output[d] = output[d] * old_weight + value[d] * new_weight
        maximum = next_maximum
    return [value / denominator for value in output]


def sample_logits_reference(
    logits: Sequence[float], history: Iterable[int], repetition_penalty: float,
    temperature: float, top_k: int, top_p: float, min_p: float, seed: int,
) -> int:
    if not logits or temperature <= 0.0 or repetition_penalty <= 0.0:
        raise ValueError("invalid sampler contract")
    adjusted = list(logits)
    for token in set(history):
        if 0 <= token < len(adjusted):
            adjusted[token] = adjusted[token] / repetition_penalty if adjusted[token] > 0 else adjusted[token] * repetition_penalty
    if temperature == 0.0 or top_k == 1:
        return max(range(len(adjusted)), key=lambda i: (adjusted[i], -i))
    ordered = sorted(range(len(adjusted)), key=lambda i: (-adjusted[i], i))
    if top_k > 0:
        ordered = ordered[:top_k]
    maximum = adjusted[ordered[0]] / temperature
    weighted = [(token, math.exp(adjusted[token] / temperature - maximum)) for token in ordered]
    peak = max(weight for _, weight in weighted)
    weighted = [(token, weight) for token, weight in weighted if weight >= peak * min_p]
    total = sum(weight for _, weight in weighted)
    cumulative = 0.0
    kept = []
    for token, weight in weighted:
        kept.append((token, weight))
        cumulative += weight / total
        if cumulative >= top_p:
            break
    threshold = random.Random(seed).random() * sum(weight for _, weight in kept)
    cumulative_weight = 0.0
    for token, weight in kept:
        cumulative_weight += weight
        if threshold <= cumulative_weight:
            return token
    return kept[-1][0]


def max_error(reference: Sequence[float], candidate: Sequence[float]) -> dict[str, float]:
    if len(reference) != len(candidate):
        raise ValueError("shape mismatch")
    absolute = 0.0
    relative = 0.0
    for expected, actual in zip(reference, candidate):
        delta = abs(expected - actual)
        absolute = max(absolute, delta)
        relative = max(relative, delta / max(abs(expected), 1e-30))
    return {"max_abs": absolute, "max_rel": relative}


def _validate_attention(q: Sequence[float], keys: Sequence[Sequence[float]], values: Sequence[Sequence[float]]) -> None:
    if not keys or len(keys) != len(values):
        raise ValueError("attention requires matching nonempty K/V context")
    if any(len(key) != len(q) for key in keys) or not values[0] or any(len(value) != len(values[0]) for value in values):
        raise ValueError("attention shape mismatch")
