from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest

from vladder.toolchain import Toolchain, alive2_check
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

    def test_canonical_ir_identity_does_not_require_alive2_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ir = root / "identity.ll"
            ir.write_text(
                "define i32 @transform_ref(i32 %x) {\n"
                "  ret i32 %x\n"
                "}\n\n"
                "define i32 @transform_candidate(i32 %x) {\n"
                "  ret i32 %x\n"
                "}\n"
            )
            toolchain = Toolchain("clang", "clang", None, None, None, None, None, None)
            proof = alive2_check(toolchain, ir, root / "proof", "identity")
            self.assertEqual(proof["status"], "correct")
            self.assertEqual(proof["method"], "canonical-llvm-ir-identity")
            self.assertFalse(proof["alive2_invoked"])


if __name__ == "__main__":
    unittest.main()
