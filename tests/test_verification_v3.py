from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest

from vladder.toolchain import Toolchain, alive2_check, alive2_refinement_check
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

    def test_two_module_refinement_preserves_module_context_and_sanitizes_metadata(self) -> None:
        module = """\
source_filename = "fixture.cpp"
%struct.Result = type { i32, i32 }

define %struct.Result @selected(i32 %value) !dbg !3 {
entry:
  %next = add i32 %value, 1, !noundef !4, !dbg !5
  %a = insertvalue %struct.Result poison, i32 %value, 0
  %b = insertvalue %struct.Result %a, i32 %next, 1
  ret %struct.Result %b, !dbg !6
}

!llvm.dbg.cu = !{!0}
!0 = distinct !DICompileUnit(language: DW_LANG_C_plus_plus, file: !1, producer: "fixture", isOptimized: true, runtimeVersion: 0, emissionKind: FullDebug)
!1 = !DIFile(filename: "fixture.cpp", directory: ".")
!2 = !DISubroutineType(types: !{})
!3 = distinct !DISubprogram(name: "selected", scope: !1, file: !1, line: 1, type: !2, scopeLine: 1, unit: !0)
!4 = !{}
!5 = !DILocation(line: 2, column: 1, scope: !3)
!6 = !DILocation(line: 3, column: 1, scope: !3)
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ll"
            target = root / "target.ll"
            source.write_text(module)
            target.write_text(module)
            toolchain = Toolchain("clang", "clang", None, None, None, None, None, None)
            proof = alive2_refinement_check(
                toolchain, source, target, root / "proof", "aggregate", function="selected"
            )
            self.assertEqual(proof["status"], "correct")
            self.assertFalse(proof["alive2_invoked"])
            sanitized = Path(proof["source_ir"]).read_text()
            self.assertNotIn("!!", sanitized)
            self.assertNotIn("!noundef", sanitized)
            self.assertIn("%struct.Result", sanitized)


if __name__ == "__main__":
    unittest.main()
