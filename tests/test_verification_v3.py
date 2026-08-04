from __future__ import annotations

import math
import unittest

from vladder.verification_v3 import differential_sequence, floating_error, prove_decode_pack_risk_and_book


class VerificationV3Tests(unittest.TestCase):
    def test_integer_and_state_smt_schemas(self) -> None:
        proof = prove_decode_pack_risk_and_book()
        self.assertEqual(proof["status"], "proved")

    def test_float_absolute_relative_and_ulp(self) -> None:
        error = floating_error([0.0, 1.0, -2.0], [0.0, math.nextafter(1.0, 2.0), -2.0])
        self.assertLessEqual(error["max_ulp"], 1)

    def test_sequence_failure_is_shrunk(self) -> None:
        result = differential_sequence(list(range(20)), lambda x: x * 2, lambda x: x * 2 if x != 13 else 99)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["minimal_sequence"], [13])


if __name__ == "__main__":
    unittest.main()
