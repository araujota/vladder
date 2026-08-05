from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import vladder
from vladder.api import BenchmarkPolicy, DeepGrammarRankRequest, OptimizationRequest
from vladder.capabilities import load_registry, require_executable
from vladder.replacement import verify_applied_replacement
from vladder.skill_tools import install_skill, validate_skill
from vladder.verification_policy import VerificationPolicy, evaluate_promotion


class ReleaseSurfaceTests(unittest.TestCase):
    def test_public_identity_and_registry(self):
        self.assertEqual(vladder.__version__, "1.0.0rc14")
        registry = load_registry()
        self.assertEqual(registry.version, "vladder-v1")
        self.assertGreaterEqual(len(registry.families), 10)
        self.assertIn("loop-schedule", registry.executable_families())
        with self.assertRaises(RuntimeError):
            require_executable(registry, ["concurrency-memory-order"])

    def test_strict_promotion_requires_every_proof_layer(self):
        candidate = {
            "candidate": "winner",
            "status": "PASS",
            "speedup_vs_baseline_pct": 4.0,
            "proof": {"status": "PROVED"},
            "memory_proof": {"status": "proved"},
            "alive2": {"status": "correct"},
        }
        self.assertTrue(evaluate_promotion(candidate, "strict", 2.0).promotable)
        candidate["alive2"] = {"status": "unsupported"}
        self.assertFalse(evaluate_promotion(candidate, "strict", 2.0).promotable)
        self.assertFalse(evaluate_promotion(candidate, "exploratory", 2.0).promotable)

    def test_library_request_translates_to_strict_cli(self):
        request = OptimizationRequest(
            Path("kernel.c"),
            "transform",
            Path("out"),
            benchmark=BenchmarkPolicy(element_count=64, repetitions=3, inner_calls=2, cpu=1),
        )
        argv = request.argv()
        self.assertEqual(argv[0], "optimize")
        self.assertIn("--alive2", argv)
        self.assertIn("--graph-inner-loop", argv)
        self.assertIn("strict", argv)

    def test_deep_rank_request_uses_one_canonical_workflow(self):
        argv = DeepGrammarRankRequest(Path("deep-out"), language="rust", cpu=2).argv()
        self.assertEqual(argv[:2], ["deep", "rank"])
        self.assertIn("rust", argv)
        self.assertIn("--cpu", argv)

    def test_bundled_skill_validates_and_installs_idempotently(self):
        self.assertEqual(validate_skill()["status"], "pass")
        with tempfile.TemporaryDirectory() as directory:
            first = install_skill(Path(directory))
            second = install_skill(Path(directory))
            self.assertEqual(first["status"], "pass")
            self.assertTrue(second["already_current"])

    def test_applied_replacement_closes_proof_chain(self):
        source = "#include <stddef.h>\nvoid transform(float *dst, const float *src, size_t n) { for (size_t i = 0; i < n; ++i) dst[i] = src[i] + 1.0f; }\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "optimized.c").write_text(source)
            (root / "applied.c").write_text(source)
            report = {
                "promotion": {"promotable": True},
                "winner": {
                    "candidate": "verified",
                    "status": "PASS",
                    "proof": {"status": "PROVED"},
                    "memory_proof": {"status": "proved"},
                    "alive2": {"status": "correct"},
                },
            }
            report_path = root / "perf.json"
            report_path.write_text(json.dumps(report))
            result = verify_applied_replacement(report_path, root / "applied.c", "transform")
            self.assertEqual(result["status"], "pass")
            self.assertTrue(result["function_identity"])


if __name__ == "__main__":
    unittest.main()
