from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from vladder.agent_workflow import run_agent_workflow, summarize_report
from vladder.consent import CANONICAL_TRAINING_DATA, set_consent
from vladder.cpp_adapters import generate_cpp_adapter_bundle
from vladder.cpp_regions import inspect_cpp_matrix, inspect_cpp_region
from vladder.lifetime_workflow import synthesize_lifetime_flow
from vladder.paired_benchmark import compose_benchmark_effects, run_paired_benchmark
from vladder.shader_workflow import inspect_shader, synthesize_shader
from vladder.state_protocol import verify_state_protocol
from vladder.toolchain import discover_toolchain


ROOT = Path(__file__).resolve().parents[1]


def _compile_database(root: Path, source: Path) -> Path:
    compiler = discover_toolchain().compiler
    value = [{
        "directory": str(ROOT),
        "file": str(source.resolve()),
        "arguments": [compiler, "-std=c++20", "-c", str(source.resolve()), "-o", str(root / "unit.o")],
    }]
    path = root / "compile_commands.json"
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


class AgenticRc6Tests(unittest.TestCase):
    def test_cpp_closure_generates_explicit_nonproof_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = ROOT / "examples" / "cpp_regions" / "adapter_protocol.cpp"
            database = _compile_database(root, source)
            report = inspect_cpp_region(source, "send_packet", database, root / "inspect")
            bundle = generate_cpp_adapter_bundle(root / "inspect" / "cpp-support.json", root / "adapter")
            self.assertEqual(bundle["status"], "adapter_skeleton_generated")
            self.assertFalse(bundle["promotion_ready"])
            self.assertGreater(bundle["unresolved_count"], 0)
            manifest = yaml.safe_load(Path(bundle["manifest"]).read_text())
            self.assertTrue(manifest["promotion_blocked"])
            self.assertIn("TODO_REQUIRED", manifest["application_contract"].values())
            self.assertIn("not proof", Path(bundle["agent_task"]).read_text())

    def test_cpp_matrix_reuses_only_matching_content_addressed_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = ROOT / "examples" / "cpp_regions" / "accepted_byte_parser.cpp"
            database = _compile_database(root, source)
            manifest = root / "audit.yaml"
            manifest.write_text(yaml.safe_dump({
                "compile_commands": str(database),
                "regions": [{"id": "parser", "source": str(source), "function": "parse_word"}],
            }))
            first = inspect_cpp_matrix(manifest, root / "audit")
            second = inspect_cpp_matrix(manifest, root / "audit")
            self.assertEqual(first["cache"]["computed_regions"], 1)
            self.assertEqual(second["cache"]["reused_regions"], 1)
            self.assertEqual(second["regions"][0]["evidence_origin"], "revalidated_cache")

    def test_member_adapter_starts_from_ast_state_projection_without_claiming_invariant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = ROOT / "examples" / "cpp_regions" / "accepted_state_transition.cpp"
            database = _compile_database(root, source)
            report = inspect_cpp_region(source, "add", database, root / "inspect")
            if report.get("candidate_symbols") and report.get("status") != "supported":
                symbol = report["candidate_symbols"][0]["symbol"]
                report = inspect_cpp_region(source, "add", database, root / "selected", symbol=symbol)
                report_path = root / "selected" / "cpp-support.json"
            else:
                report_path = root / "inspect" / "cpp-support.json"
            bundle = generate_cpp_adapter_bundle(report_path, root / "adapter")
            manifest = yaml.safe_load(Path(bundle["manifest"]).read_text())
            projection = manifest["inferred_state_projection"]
            self.assertTrue(projection["fields"])
            self.assertFalse(projection["complete_class_invariant"])
            self.assertTrue(Path(bundle["state_protocol_template"]).exists())

    def test_versioned_cache_proves_and_missing_invalidator_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = verify_state_protocol(ROOT / "examples" / "protocols" / "versioned_cache.yaml", root / "good")
            self.assertEqual(good["status"], "PASS")
            broken = yaml.safe_load((ROOT / "examples" / "protocols" / "versioned_cache.yaml").read_text())
            broken["non_invalidators"] = []
            broken_path = root / "broken.yaml"
            broken_path.write_text(yaml.safe_dump(broken))
            bad = verify_state_protocol(broken_path, root / "bad")
            self.assertEqual(bad["status"], "FAIL")
            obligation = next(item for item in bad["obligations"] if item["name"] == "complete mutation classification")
            self.assertEqual(obligation["solver_result"], "SAT")

    def test_weak_lifetime_trace_fails_attribution_instead_of_empty_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = (ROOT / "examples" / "lifetime" / "lifetime_trace.json").read_text().splitlines()[0]
            trace = root / "weak.jsonl"
            trace.write_text(first + "\n")
            report = synthesize_lifetime_flow(
                ROOT / "examples" / "lifetime" / "lifetime_corpus.yaml", trace, root / "out"
            )
            self.assertEqual(report["status"], "insufficient_attribution")
            self.assertEqual(report["candidate_count"], 0)
            self.assertTrue((root / "out" / "trace-quality.json").exists())

    def test_paired_runner_randomizes_and_bootstraps_exact_observables(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "bench.py"
            script.write_text(
                "import json,sys\n"
                "metric=100.0 if sys.argv[1]=='baseline' else 80.0\n"
                "print(json.dumps({'metric':metric,'observable_hash':'same'}))\n"
            )
            manifest = root / "paired.yaml"
            manifest.write_text(yaml.safe_dump({
                "executable": sys.executable,
                "baseline_args": [str(script), "baseline"],
                "candidate_args": [str(script), "candidate"],
                "processes": 6,
                "repetitions_per_process": 1,
                "observable_key": "observable_hash",
                "exact_observables": True,
                "minimum_effect_percent": 5.0,
                "bootstrap_rounds": 100,
                "seed": 4,
            }))
            report = run_paired_benchmark(manifest, root / "out")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["semantic_parity"], "PASS")
            self.assertGreater(report["paired_effect_95_percent"][0], 20.0)
            self.assertGreater(len({tuple(item["order"]) for item in report["pairs"]}), 1)

    def test_overlap_is_rejected_without_interaction_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "composition.yaml"
            manifest.write_text(yaml.safe_dump({"effects": [
                {"id": "parent", "covers": ["parent", "child"], "effect_percent": 8},
                {"id": "child", "covers": ["child"], "effect_percent": 4},
            ]}))
            report = compose_benchmark_effects(manifest, root / "report.json")
            self.assertEqual(report["status"], "rejected_overlap")
            self.assertFalse(report["composable"])

    @unittest.skipUnless(
        all(shutil.which(tool) for tool in ("glslangValidator", "spirv-val", "spirv-opt", "spirv-dis")),
        "SPIR-V toolchain unavailable",
    )
    def test_spirv_workflow_generates_valid_but_unproved_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inspection = inspect_shader(ROOT / "examples" / "shaders" / "scale.comp", root / "inspect")
            self.assertEqual(inspection["validation"]["status"], "pass")
            report = synthesize_shader(ROOT / "examples" / "shaders" / "scale.comp", root / "synthesize")
            valid = [item for item in report["candidates"] if item.get("structural_validation") == "PASS"]
            self.assertTrue(valid)
            self.assertIsNone(report["winner"])
            self.assertTrue(all(not item["promotable"] for item in valid))

    def test_workflow_is_resumable_and_marks_revalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "workflow.yaml"
            manifest.write_text(yaml.safe_dump({
                "schema_version": "vladder-agent-workflow-v1",
                "name": "cache-proof",
                "region": {
                    "kind": "protocol", "action": "verify",
                    "manifest": str(ROOT / "examples" / "protocols" / "versioned_cache.yaml"),
                },
                "contract": {"identity": "cache-v1", "exact": True},
                "workload": {"identity": "protocol-only"},
            }))
            first = run_agent_workflow(manifest, root / "out")
            second = run_agent_workflow(manifest, root / "out")
            self.assertEqual(first["evidence_origin"], "newly_computed")
            self.assertEqual(second["evidence_origin"], "revalidated")
            self.assertTrue(second["states"]["candidate_proved"])
            self.assertFalse(second["states"]["production_promoted"])
            self.assertLessEqual(len(second["decisive_artifacts"]), 5)

    def test_terminal_promotion_summary_ubiquitously_submits_when_opted_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consent_path = root / "consent.json"
            set_consent(
                CANONICAL_TRAINING_DATA, "opt_in", path=consent_path,
                confirmed_user_choice=True,
            )
            manifest = root / "workflow.yaml"
            manifest.write_text(yaml.safe_dump({
                "schema_version": "vladder-agent-workflow-v1",
                "name": "terminal-training-record",
                "region": {
                    "kind": "protocol", "action": "verify",
                    "manifest": str(ROOT / "examples" / "protocols" / "versioned_cache.yaml"),
                },
                "contract": {"identity": "cache-v1", "exact": True},
                "workload": {"identity": "protocol-only"},
            }))
            sync_result = {
                "status": "pass",
                "record_forms": ["workflow_disposition", "proof_and_promotion_state"],
            }
            with patch.dict("os.environ", {"VLADDER_CONSENT_FILE": str(consent_path)}):
                with patch("vladder.agent_workflow.sync_promotion_summary", return_value=sync_result) as sync:
                    first = run_agent_workflow(manifest, root / "out")
                    second = run_agent_workflow(manifest, root / "out")
                    imported = summarize_report(
                        root / "out" / "stage" / "protocol-proof.json",
                        root / "imported-summary.json",
                    )
            self.assertEqual(sync.call_count, 3)
            for summary in (first, second, imported):
                contribution = summary["optional_contributions"]["canonical_training_data"]
                self.assertEqual(contribution["status"], "continuous_contribution_completed")
                self.assertEqual(contribution["trigger"], "terminal_promotion_summary")
                self.assertTrue(contribution["record_complete"])
                self.assertTrue(summary["states"]["workflow_completed"])
                self.assertTrue(summary["workflow_key"])

    def test_terminal_promotion_summary_never_submits_after_opt_out(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consent_path = root / "consent.json"
            set_consent(
                CANONICAL_TRAINING_DATA, "opt_out", path=consent_path,
                confirmed_user_choice=True,
            )
            report_path = root / "protocol-proof.json"
            verify_state_protocol(
                ROOT / "examples" / "protocols" / "versioned_cache.yaml", root / "protocol",
            )
            generated_report = root / "protocol" / "protocol-proof.json"
            report_path.write_bytes(generated_report.read_bytes())
            with patch.dict("os.environ", {"VLADDER_CONSENT_FILE": str(consent_path)}):
                with patch("vladder.agent_workflow.sync_promotion_summary") as sync:
                    summary = summarize_report(report_path, root / "summary.json")
            sync.assert_not_called()
            contribution = summary["optional_contributions"]["canonical_training_data"]
            self.assertEqual(contribution["status"], "disabled_by_user")
            self.assertFalse(contribution["network_action_performed"])


if __name__ == "__main__":
    unittest.main()
