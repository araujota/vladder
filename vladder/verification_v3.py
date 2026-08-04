from __future__ import annotations

import math
import struct
from typing import Any, Callable, Sequence, TypeVar


T = TypeVar("T")


def prove_decode_pack_risk_and_book() -> dict[str, Any]:
    import z3

    bytes_ = [z3.BitVec(f"b{i}", 8) for i in range(18)]
    shifted32 = z3.Concat(*bytes_[2:6])
    loaded32_le = z3.Concat(*reversed(bytes_[2:6]))
    bswap32 = z3.Concat(
        z3.Extract(7, 0, loaded32_le), z3.Extract(15, 8, loaded32_le),
        z3.Extract(23, 16, loaded32_le), z3.Extract(31, 24, loaded32_le),
    )
    shifted64 = z3.Concat(*bytes_[10:18])
    loaded64_le = z3.Concat(*reversed(bytes_[10:18]))
    bswap64 = z3.Concat(*[z3.Extract(i + 7, i, loaded64_le) for i in range(0, 64, 8)])
    quantity, position, reserved, max_order, max_position = z3.Ints("quantity position reserved max_order max_position")
    side = z3.Bool("side")
    signed = z3.If(side, -quantity, quantity)
    exposure = position + reserved + signed
    absolute_exposure = z3.If(exposure < 0, -exposure, exposure)
    short_circuit = z3.And(quantity <= max_order, absolute_exposure <= max_position)
    mask_form = z3.Not(z3.Or(quantity > max_order, absolute_exposure > max_position))
    level, old_bid, old_ask, next_quantity = z3.Ints("level old_bid old_ask next_quantity")
    is_bid = z3.Bool("is_bid")
    next_bid = z3.If(is_bid, next_quantity, old_bid)
    next_ask = z3.If(is_bid, old_ask, next_quantity)
    obligations = {
        "decode_u32": shifted32 == bswap32,
        "decode_u64": shifted64 == bswap64,
        "risk_predicate": short_circuit == mask_form,
        "book_non_target_side": z3.And(z3.Implies(is_bid, next_ask == old_ask), z3.Implies(z3.Not(is_bid), next_bid == old_bid)),
        "changed_mask_single_bit": z3.Implies(z3.And(level >= 0, level < 64), (z3.BitVecVal(1, 64) << z3.Int2BV(level, 64)) != 0),
    }
    results = {}
    for name, proposition in obligations.items():
        solver = z3.Solver(); solver.add(z3.Not(proposition)); result = solver.check()
        results[name] = {"status": "proved" if result == z3.unsat else "failed", "solver": str(result), "smt2": solver.to_smt2()}
    return {"status": "proved" if all(item["status"] == "proved" for item in results.values()) else "failed", "obligations": results}


def floating_error(reference: Sequence[float], candidate: Sequence[float]) -> dict[str, float]:
    if len(reference) != len(candidate):
        raise ValueError("shape mismatch")
    max_abs = max_rel = 0.0
    max_ulp = 0
    for expected, actual in zip(reference, candidate):
        if math.isnan(expected) or math.isnan(actual):
            if not (math.isnan(expected) and math.isnan(actual)):
                return {"max_abs": math.inf, "max_rel": math.inf, "max_ulp": math.inf}
            continue
        delta = abs(expected - actual)
        max_abs = max(max_abs, delta)
        max_rel = max(max_rel, delta / max(abs(expected), 1e-30))
        max_ulp = max(max_ulp, _ordered_f32(actual) - _ordered_f32(expected), _ordered_f32(expected) - _ordered_f32(actual))
    return {"max_abs": max_abs, "max_rel": max_rel, "max_ulp": float(max_ulp)}


def differential_sequence(
    sequence: Sequence[T], reference: Callable[[T], Any], candidate: Callable[[T], Any]
) -> dict[str, Any]:
    mismatch = _first_mismatch(sequence, reference, candidate)
    if mismatch is None:
        return {"status": "passed", "events": len(sequence)}
    reduced = list(sequence[: mismatch + 1])
    granularity = 2
    while len(reduced) > 1:
        chunk = max(1, len(reduced) // granularity)
        changed = False
        for start in range(0, len(reduced), chunk):
            trial = reduced[:start] + reduced[start + chunk:]
            if trial and _first_mismatch(trial, reference, candidate) is not None:
                reduced = trial; changed = True; break
        if not changed:
            if granularity >= len(reduced): break
            granularity = min(len(reduced), granularity * 2)
    return {"status": "failed", "first_mismatch": mismatch, "minimal_sequence": reduced}


def _first_mismatch(sequence: Sequence[T], reference: Callable[[T], Any], candidate: Callable[[T], Any]) -> int | None:
    for index, item in enumerate(sequence):
        if reference(item) != candidate(item):
            return index
    return None


def _ordered_f32(value: float) -> int:
    bits = struct.unpack("!I", struct.pack("!f", value))[0]
    return (~bits & 0xFFFFFFFF) if bits & 0x80000000 else (bits | 0x80000000)
