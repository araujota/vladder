from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from vladder import LifetimeRequest, VelocityLadder
from vladder.capabilities import load_registry
from vladder.lifetime_attribution import LifetimeEvent, attribute_lifetimes, load_lifetime_trace
from vladder.lifetime_grammar import discover_lifetime_candidates, with_candidate_invalidators
from vladder.lifetime_graph import NODE_KINDS, load_lifetime_flow_graph
from vladder.lifetime_realization import build_agent_realization_contract
from vladder.lifetime_verification import verify_lifetime_candidate
from vladder.lifetime_workflow import evaluate_lifetime_corpus
from vladder.lowering import LoweringEngine, LoweringRequest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples" / "lifetime" / "lifetime_corpus.yaml"
TRACE = ROOT / "examples" / "lifetime" / "lifetime_trace.json"


class LifetimeV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_lifetime_flow_graph(MANIFEST)
        cls.events = load_lifetime_trace(TRACE, cls.graph)
        cls.attribution = attribute_lifetimes(cls.graph, cls.events)
        cls.candidates = discover_lifetime_candidates(cls.graph, cls.attribution)

    def test_graph_is_complete_valid_and_deterministic(self):
        repeated = load_lifetime_flow_graph(str(MANIFEST))
        self.assertEqual(self.graph.graph_hash, repeated.graph_hash)
        self.assertEqual(self.graph.manifest_hash, repeated.manifest_hash)
        self.assertEqual(len(self.graph.graph_hash), 64)
        self.assertTrue({node.kind for node in self.graph.nodes} <= NODE_KINDS)
        self.assertTrue(self.graph.scopes.contains("logical_record", "fragment"))
        self.assertFalse(self.graph.scopes.contains("frame", "fragment"))

    def test_attribution_finds_redundancy_retention_and_transfer(self):
        self.assertEqual(self.attribution["logical_record_serialized_body"].realization_redundancy_ratio, 4.0)
        self.assertGreater(self.attribution["one_shot_retained_lookup"].retention_waste_ratio, 0.8)
        self.assertEqual(self.attribution["receiver_decoded_state"].transfer_redundancy_ratio, 3.0)
        self.assertEqual(self.attribution["mutable_fragment_validation"].realization_redundancy_ratio, 1.0)

    def test_grammar_recovers_expected_families_and_rejects_observer(self):
        observed = {(candidate.information_id, candidate.family): candidate for candidate in self.candidates}
        for item in self.graph.information:
            if item.expected_family:
                self.assertIn((item.id, item.expected_family), observed)
        rejected = observed[("independently_observed_intermediate", "intermediate-realization-elimination")]
        self.assertEqual(rejected.legality, "rejected")
        self.assertIn("independent observer", " ".join(rejected.diagnostics))

    def test_expanded_legal_lattice_records_proof_passes_and_counterexample_negatives(self):
        statuses = set()
        for candidate in self.candidates:
            if candidate.legality != "legal":
                continue
            with self.subTest(candidate=candidate.candidate_id):
                result = verify_lifetime_candidate(self.graph, candidate, self.events)
                statuses.add(result.status)
                if result.status == "FAIL":
                    self.assertTrue(result.counterexamples)
                self.assertIn("outside Alive2", result.alive2_scope)
        self.assertEqual(statuses, {"PASS", "FAIL"})

    def test_missing_invalidation_produces_z3_counterexample(self):
        candidate = next(item for item in self.candidates if item.information_id == "immutable_scene_index")
        broken = with_candidate_invalidators(candidate, ())
        result = verify_lifetime_candidate(self.graph, broken, self.events)
        self.assertEqual(result.status, "FAIL")
        obligation = next(item for item in result.obligations if item.name == "invalidation completeness")
        self.assertEqual(obligation.status, "fail")
        self.assertIn("SAT", obligation.detail)

    def test_premature_retirement_fails_transition_replay(self):
        candidate = next(item for item in self.candidates if item.information_id == "immutable_scene_index")
        scopes = {"planning_event": "s0:p0", "scene_generation": "s0", "process": "p0"}
        events = tuple(
            LifetimeEvent(index, index, "immutable_scene_index", "scene:0", event, scopes, None, None, None, None, 0)
            for index, event in enumerate(("construct", "publish", "retire", "consume"))
        )
        result = verify_lifetime_candidate(self.graph, candidate, events)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any(item.get("reason") == "read outside valid realization lifetime" for item in result.counterexamples))

    def test_agent_contract_is_explicit_and_composable(self):
        candidate = next(item for item in self.candidates if item.information_id == "logical_record_serialized_body")
        verification = verify_lifetime_candidate(self.graph, candidate, self.events)
        contract = build_agent_realization_contract(self.graph, candidate, verification)
        self.assertEqual(contract.status, "ready_for_agent_realization")
        self.assertEqual(contract.source_regeneration, "agent_adapter_required; generic repository source emission is not claimed")
        self.assertIn("expression-algebra", contract.lower_level_handoff)
        self.assertTrue(contract.invalidation_matrix)

    def test_central_registry_has_executable_lifetime_lowering(self):
        registry = load_registry()
        family = registry.family("lifetime-realization")
        self.assertEqual(len(family["rules"]), 5)
        result = LoweringEngine(registry).lower(LoweringRequest(
            "lifetime-realization",
            "serialization-body-reuse",
            {
                "semantic source authority": True,
                "scope containment": True,
                "complete mutation classification": True,
                "fallback equivalence": True,
            },
            input_identity=self.graph.graph_hash,
        ))
        self.assertEqual(result.status.value, "planned")
        self.assertEqual(result.plan.operations[1].opcode, "lifetime-realization.serialization-body-reuse")

    def test_public_api_and_isolated_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            request = LifetimeRequest(MANIFEST, TRACE, output / "api", action="analyze")
            result = VelocityLadder().lifetime(request)
            self.assertEqual(result.return_code, 0)
            self.assertEqual(result.report["status"], "pass")
            evaluation = evaluate_lifetime_corpus(MANIFEST, TRACE, output / "evaluation")
            self.assertEqual(evaluation["status"], "pass")
            self.assertEqual(evaluation["discovery"]["precision"], 1.0)
            self.assertEqual(evaluation["discovery"]["recall"], 1.0)
            self.assertGreaterEqual(evaluation["significant_microbenchmark_wins"], 2)
            self.assertIn("not NeuralFusion", evaluation["scope"])


if __name__ == "__main__":
    unittest.main()
