import unittest

from vladder.hardware_manifest import HardwareManifest, compatibility_errors
from vladder.statistics_v3 import empirical_quantile, rank_hft, summarize_samples


class MeasurementV3Tests(unittest.TestCase):
    def test_quantiles_and_bootstrap_are_deterministic(self):
        blocks = [list(range(1, 101)), list(range(2, 102))]
        first = summarize_samples(blocks, bootstrap_rounds=50, seed=7)
        second = summarize_samples(blocks, bootstrap_rounds=50, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(empirical_quantile([1, 2, 3], 0.5), 2)

    def test_manifest_mismatch_is_rejected(self):
        base = {"cpu_model": "x", "governors": {"0": "performance"}}
        other = {**base, "governors": {"0": "powersave"}}
        left = HardwareManifest("v", "t", 0, base, "a")
        right = HardwareManifest("v", "t", 0, other, "b")
        self.assertTrue(any("governors" in error for error in compatibility_errors([left, right])))

    def test_tail_regression_blocks_hft_winner(self):
        baseline = {"p50": 100.0, "p99_9": 200.0, "p99_99": 250.0}
        candidate = {"p50": 85.0, "p99_9": 180.0, "p99_99": 260.0}
        result = rank_hft(baseline, candidate)
        self.assertFalse(result["accepted"])


if __name__ == "__main__":
    unittest.main()
