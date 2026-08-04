from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from vladder.hft_operators import (
    BookState, MarketEvent, PRICE_BASE, RiskState, SPSCRing, book_as_aos,
    book_from_aos, decode_event, encode_decision, encode_decision_template,
    encode_event, ewma_recompute, generate_trace, read_trace, risk_gate,
    risk_gate_mask, run_pipeline, update_book, write_trace,
)
from vladder.token_operators import (
    attention_materialized_reference, attention_online_reference, max_error,
    quantized_gemv_epilogue_reference, rope_qk_reference, sample_logits_reference,
)


class TokenOperatorsV3Tests(unittest.TestCase):
    def test_rope_qk_multi_output(self) -> None:
        q, k = rope_qk_reference([1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0], [1.0, 0.0], [0.0, 1.0])
        self.assertEqual(q, [1.0, 2.0, -4.0, 3.0])
        self.assertEqual(k, [4.0, 3.0, -1.0, 2.0])

    def test_online_attention_matches_materialized(self) -> None:
        q = [0.25, -0.5, 1.0]
        keys = [[1.0, 0.0, 0.5], [-1.0, 2.0, 0.25], [0.0, 0.0, 0.0]]
        values = [[1.0, 2.0], [3.0, -1.0], [0.5, 4.0]]
        expected = attention_materialized_reference(q, keys, values, 1 / math.sqrt(3))
        actual = attention_online_reference(q, keys, values, 1 / math.sqrt(3))
        self.assertLess(max_error(expected, actual)["max_abs"], 1e-12)

    def test_quantized_epilogue_and_sampling_reproducibility(self) -> None:
        first = quantized_gemv_epilogue_reference([1, -2, 3, -4], [0.5, 0.25], [1.0] * 4, 2, 0.1)
        self.assertTrue(math.isfinite(first))
        args = ([0.0, 3.0, 2.0, -1.0], [1], 1.1, 0.8, 3, 0.9, 0.01, 55)
        self.assertEqual(sample_logits_reference(*args), sample_logits_reference(*args))

    def test_attention_context_buckets_and_long_run_drift(self) -> None:
        for context in (128, 512):
            q = [0.25, -0.5, 0.75, 1.0]
            keys = [[math.sin((j + d) * 0.01) for d in range(4)] for j in range(context)]
            values = [[math.cos((j - d) * 0.02) for d in range(4)] for j in range(context)]
            expected = attention_materialized_reference(q, keys, values, 0.5)
            actual = attention_online_reference(q, keys, values, 0.5)
            error = max_error(expected, actual)
            self.assertLess(error["max_abs"], 1e-12)
            self.assertLess(error["max_rel"], 1e-11)


class HFTOperatorsV3Tests(unittest.TestCase):
    def test_schema_and_book_transition(self) -> None:
        event = MarketEvent(1, 0, PRICE_BASE + 17, 44, 1)
        self.assertEqual(decode_event(encode_event(event)), event)
        book = BookState.empty()
        top, mask = update_book(book, event)
        self.assertEqual((top.best_bid_ticks, top.best_bid_qty), (PRICE_BASE + 17, 44))
        self.assertEqual(mask, 1 << 17)

    def test_deterministic_trace_round_trip_and_pipeline(self) -> None:
        trace = generate_trace("held_out", 128, 404)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trace.bin"
            write_trace(str(path), trace, 404)
            loaded, seed = read_trace(str(path))
        self.assertEqual((loaded, seed), (trace, 404))
        left = run_pipeline(trace)
        right = run_pipeline(trace)
        self.assertEqual(left, right)

    def test_adversarial_trace_and_ring_wraparound(self) -> None:
        outputs, state = run_pipeline(generate_trace("adversarial", 200, 505))
        self.assertEqual(len(outputs), 200)
        self.assertLessEqual(len(state["ring_drained"]), 8)
        ring = SPSCRing(4)
        for cycle in range(100):
            self.assertTrue(ring.enqueue(bytes([cycle & 255])))
            self.assertEqual(ring.dequeue(), bytes([cycle & 255]))

    def test_duplicate_sequence_is_rejected_without_state_change(self) -> None:
        event = MarketEvent(1, 0, PRICE_BASE, 7, 1)
        messages = [encode_event(event), encode_event(event)]
        outputs, state = run_pipeline(messages)
        self.assertEqual([output.status for output in outputs], [0, -2])
        self.assertEqual(state["book"]["last_sequence"], 1)

    def test_layout_risk_feature_and_encode_alternatives(self) -> None:
        book = BookState.empty(); book.bid_qty[63] = 9; book.ask_qty[0] = 11; book.last_sequence = 7
        self.assertEqual(book_from_aos(book_as_aos(book), 7), book)
        event = MarketEvent(1, 0, PRICE_BASE + 63, 101, 8)
        left, right = RiskState(), RiskState()
        self.assertEqual(risk_gate(event, left, 1000, 200), risk_gate_mask(event, right, 1000, 200))
        self.assertEqual(left, right)
        self.assertEqual(encode_decision(event, True, 0, 3), encode_decision_template(event, True, 0, 3))
        values = [100.0, 101.0, 99.0, 102.0]
        incremental = 0.0
        for value in values: incremental += 0.125 * (value - incremental)
        self.assertEqual(ewma_recompute(values), incremental)

    def test_full_crossed_book_and_risk_boundaries(self) -> None:
        book = BookState.empty()
        sequence = 1
        for level in range(64):
            update_book(book, MarketEvent(1, 0, PRICE_BASE + level, level + 1, sequence)); sequence += 1
            top, _ = update_book(book, MarketEvent(1, 1, PRICE_BASE + level, level + 2, sequence)); sequence += 1
        self.assertGreater(top.best_bid_ticks, top.best_ask_ticks)
        state = RiskState(position=990, reserved=0)
        self.assertEqual(risk_gate(MarketEvent(1, 0, PRICE_BASE, 10, sequence), state, 1000, 10), (True, 0))
        self.assertEqual(risk_gate(MarketEvent(1, 0, PRICE_BASE, 1, sequence + 1), state, 1000, 10), (False, 2))


if __name__ == "__main__":
    unittest.main()
