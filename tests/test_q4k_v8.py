from __future__ import annotations

import unittest

from vladder.q4k_physical import PHYSICAL_NODE_KINDS, _classify
from vladder.q4k_v8 import _grammar_decisions, _improvement_ceilings
from vladder.q4k_v8_variants import _linear_regression


class Q4KPhysicalV8Tests(unittest.TestCase):
    def test_physical_ir_declares_all_required_resource_classes(self) -> None:
        required = {
            "WeightCacheLineFetch", "ScaleMetadataExtract", "NibbleShift",
            "IntegerMultiplyAccumulate", "FloatAccumulate", "OutputStore",
            "VectorRegisterLiveRange", "ExecutionPortReservation", "LoopBackedge",
        }
        self.assertTrue(required <= PHYSICAL_NODE_KINDS)

    def test_source_mapping_separates_decode_dot_and_output(self) -> None:
        self.assertEqual(_classify(110, "vpsrlw", "%ymm1, %ymm2, %ymm3"), ("C", "NibbleShift"))
        self.assertEqual(_classify(172, "vpmaddubsw", "%ymm1, %ymm2, %ymm3")[0], "E")
        self.assertEqual(_classify(222, "vmovups", "%ymm1, (%rax)"), ("H", "OutputStore"))

    def test_ceiling_report_does_not_convert_envelopes_to_proven_headroom(self) -> None:
        attribution = {
            "stages": {
                code: {
                    "marginal_share_range_percent": [0.0, 20.0],
                    "marginal_identified": False,
                }
                for code in "ABCDEFGH"
            }
        }
        report = _improvement_ceilings(attribution, {"observed_over_strongest_bound": 2.0})
        self.assertEqual(report["total_conservative_percent"], 0.0)
        self.assertEqual(report["three_percent_plausible"], "uncertain")
        self.assertTrue(all(not item["recoverability_demonstrated"] for item in report["stages"].values()))

    def test_admission_promotes_only_measured_work_reuse_interaction(self) -> None:
        stages = {
            code: {
                "marginal_share_range_percent": [0.0, 40.0],
                "critical_path_estimate_percent": 20.0,
                "marginal_identified": False,
            }
            for code in "ABCDEFGH"
        }
        ceilings = {
            "stages": {
                code: {"optimistic_regional_ceiling_percent": 5.0}
                for code in "ABCDEFGH"
            },
            "total_conservative_percent": 0.0,
            "total_optimistic_percent": 25.0,
        }
        cache = {
            "llc": {"mean_process_median_ns": 100.0},
            "gate_rows4": {"mean_process_median_ns": 360.0},
        }
        report = _grammar_decisions(stages | {"stages": stages}, ceilings, cache, {"classification": "memory_sensitive_mixed"})
        self.assertEqual(report["admitted"], ["work_reuse_token_tiles"])
        decisions = {item["family"]: item["classification"] for item in report["decisions"]}
        self.assertEqual(decisions["decode_network_synthesis"], "requires_more_measurement")
        self.assertEqual(decisions["layout_changes"], "reject")

    def test_frequency_regression_is_reported_as_nuisance_only(self) -> None:
        records = []
        for index in range(8):
            records.append({
                "frequency_khz_mean": 4_700_000 + index * 10_000,
                "temperature_millic_mean": 65_000 + index * 500,
                "median_ns": 400_000 - index * 250,
            })
        result = _linear_regression(records)
        self.assertEqual(result["status"], "PASS")
        self.assertIn("nuisance", result["use"])


if __name__ == "__main__":
    unittest.main()
