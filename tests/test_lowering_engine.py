from __future__ import annotations

import json
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from vladder import LoweringEngine, LoweringMode, LoweringRequest, LoweringStatus, VelocityLadder
from vladder.capabilities import load_registry
from vladder.cli import main
from vladder.lowerers import FACT_OVERRIDES, PARAMETER_REQUIREMENTS
from vladder.lowering import validate_lowering_registry


PARAMETER_VALUES = {
    "factor": 4,
    "tile_size": 16,
    "permutation": [1, 0],
    "peel_count": 1,
    "depth": 2,
    "distance": 4,
    "block_size": 32,
    "block_shape": [4, 8],
    "alignment": 64,
    "capacity": 64,
    "dimension": "n",
    "value": 128,
    "minimum": 1,
    "maximum": 8,
    "predicate": "common_case",
    "flags": ["-funroll-loops"],
    "token_count": 4,
    "sequence_count": 4,
    "vector_bytes": 32,
    "flush_period": 255,
}


class LoweringEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry()
        self.engine = LoweringEngine(self.registry)

    def _request(self, family: dict, rule: str, mode: LoweringMode = LoweringMode.PLAN) -> LoweringRequest:
        facts = {str(item): True for item in family["contract_facts"]}
        facts.update({item: True for item in FACT_OVERRIDES.get(rule, ())})
        parameters = {name: PARAMETER_VALUES[name] for name in PARAMETER_REQUIREMENTS.get(rule, ())}
        return LoweringRequest(
            str(family["id"]),
            rule,
            facts,
            parameters,
            mode,
            input_identity=f"fixture:{family['id']}:{rule}",
        )

    def test_registry_has_callable_complete_plan_coverage(self) -> None:
        coverage = validate_lowering_registry(self.registry)
        declared = sum(len(family["rules"]) for family in self.registry.families)
        self.assertEqual(coverage["status"], "pass")
        self.assertEqual(coverage["family_count"], 15)
        self.assertEqual(coverage["rule_count"], declared)
        self.assertEqual(coverage["plan_coverage"], declared)

    def test_every_rule_lowers_deterministically(self) -> None:
        seen: set[tuple[str, str]] = set()
        for family in self.registry.families:
            for rule in family["rules"]:
                request = self._request(family, str(rule))
                first = self.engine.lower(request)
                second = self.engine.lower(request)
                self.assertEqual(first.status, LoweringStatus.PLANNED, (family["id"], rule, first.diagnostics))
                self.assertIsNotNone(first.plan)
                self.assertEqual(first.to_dict(), second.to_dict())
                self.assertEqual(first.plan.family, family["id"])
                self.assertEqual(first.plan.rule, rule)
                self.assertEqual(len(first.plan.operations), 4)
                seen.add((str(family["id"]), str(rule)))
        self.assertEqual(len(seen), 89)

    def test_missing_contract_facts_reject_before_lowering(self) -> None:
        result = self.engine.lower(
            LoweringRequest("memory-alias", "add-restrict", {"pointer provenance": True})
        )
        self.assertEqual(result.status, LoweringStatus.REJECTED)
        self.assertIsNone(result.plan)
        self.assertIn("missing contract fact: alias sets", result.diagnostics)
        self.assertIn("missing contract fact: object bounds", result.diagnostics)

    def test_missing_rule_parameter_rejects(self) -> None:
        family = self.registry.family("loop-schedule")
        request = self._request(family, "unroll")
        result = self.engine.lower(
            LoweringRequest(request.family, request.rule, request.contract_facts, {})
        )
        self.assertEqual(result.status, LoweringStatus.REJECTED)
        self.assertEqual(result.diagnostics, ("missing parameter: factor",))

    def test_source_mode_routes_or_fails_closed(self) -> None:
        hardware = self.registry.family("hardware-codegen")
        routed = self.engine.lower(self._request(hardware, "avx2", LoweringMode.SOURCE))
        self.assertEqual(routed.status, LoweringStatus.ROUTED)
        self.assertEqual(routed.plan.backend, "vladder.candidates:generate_candidates")

        concurrency = self.registry.family("concurrency-memory-order")
        unsupported = self.engine.lower(
            self._request(concurrency, "release-acquire-pair", LoweringMode.SOURCE)
        )
        self.assertEqual(unsupported.status, LoweringStatus.UNSUPPORTED)
        self.assertIsNone(unsupported.plan.backend)

    def test_velocity_ladder_exposes_lowering_engine(self) -> None:
        family = self.registry.family("expression-algebra")
        result = VelocityLadder(self.registry).lower(self._request(family, "strength-reduce"))
        self.assertEqual(result.status, LoweringStatus.PLANNED)

    def test_bad_lowerer_and_backend_routes_fail_registry_validation(self) -> None:
        source = Path(self.registry.source)
        data = json.loads(source.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            expression = next(item for item in data["families"] if item["id"] == "expression-algebra")
            expression["lowerer"] = "vladder.missing:NoLowerer"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "cannot import lowerer"):
                load_registry(path)

            data = json.loads(source.read_text())
            expression = next(item for item in data["families"] if item["id"] == "expression-algebra")
            expression["source_routes"]["strength-reduce"] = "vladder.missing:no_backend"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "cannot import backend route"):
                load_registry(path)

            data = json.loads(source.read_text())
            expression = next(item for item in data["families"] if item["id"] == "expression-algebra")
            expression["rules"].append("unimplemented-rule")
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "rule coverage mismatch"):
                load_registry(path)

    def test_cli_validates_and_emits_a_plan(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["lower", "validate"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["plan_coverage"], 89)

        output = io.StringIO()
        with redirect_stdout(output):
            status = main(
                [
                    "lower",
                    "plan",
                    "--family",
                    "hardware-codegen",
                    "--rule",
                    "avx2",
                    "--fact",
                    "target ISA",
                    "--fact",
                    "OS vector state",
                    "--fact",
                    "fallback availability",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "planned")


if __name__ == "__main__":
    unittest.main()
