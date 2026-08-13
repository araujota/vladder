from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from vladder.orchestrator import (
    OptimizationRequest,
    _proof_badge,
    build_plan,
    inventory_external_authorities,
    run_portfolio,
    run_optimization,
    sign_remote_result,
    terminal_status,
    verify_remote_result,
    write_plan,
)
from vladder.paired_benchmark import compose_application_cost, run_paired_benchmark
from vladder.review_workflow import create_campaign_review_template, validate_review
from vladder.schema_registry import validate_artifact


ROOT = Path(__file__).resolve().parents[1]


class EvidenceOrchestratorTests(unittest.TestCase):
    def _request(self, output: Path, source: Path, symbol: str = "transform", project: Path = ROOT) -> OptimizationRequest:
        return OptimizationRequest(
            project=project,
            source=source,
            symbol=symbol,
            compile_commands=None,
            contract=None,
            workload=None,
            profile=None,
            output_directory=output,
            plan_only=True,
        )

    def test_c_plan_is_graph_coverage_and_scaffold_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._request(root / "out", ROOT / "examples" / "clamp.c")
            plan = write_plan(request, emit_progress=False)
            self.assertEqual(plan["classification"]["kind"], "c")
            self.assertGreater(plan["grammar_coverage"]["executable_family_count"], 0)
            self.assertIn(plan["economic_decision"]["recommendation"], {"CONTINUE", "STOP", "ESCALATE"})
            for artifact in plan["scaffolds"].values():
                self.assertTrue(Path(artifact).exists())
            validation = validate_artifact("optimization-plan", root / "out" / "optimization-plan.json")
            self.assertEqual(validation["status"], "pass")

    def test_cpp_forecast_maps_external_authorities_and_contract_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "owner.cpp"
            source.write_text(
                "#include <vector>\n"
                "void publish(std::vector<int>& out, const int* p, int n) {\n"
                "  std::lock_guard guard(mu); for (int i=0;i<n;++i) out.push_back(p[i]); send(1,p,n,0);\n"
                "}\n"
            )
            plan = build_plan(self._request(root / "out", source, "publish", root))
            categories = {item["category"] for item in plan["external_authority_inventory"]}
            self.assertTrue({"allocation", "synchronization", "network_io"}.issubset(categories))
            self.assertTrue(plan["contract_candidate"]["suggested_patch"])
            self.assertEqual(plan["cross_translation_unit"]["closure_status"], "compile_command_missing")
            self.assertEqual(plan["economic_decision"]["recommendation"], "ESCALATE")

    def test_cpp_scaffold_preserves_typed_borrowed_view_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._request(root / "out", ROOT / "examples" / "cpp_regions" / "supported_span.cpp")
            plan = write_plan(request, emit_progress=False)
            projection = plan["classification"]["signature_projection"]
            self.assertTrue(projection["captured"])
            self.assertEqual([item["name"] for item in projection["parameters"]], ["dst", "src"])
            adapter = Path(plan["scaffolds"]["typed_application_adapter"])
            text = adapter.read_text()
            self.assertIn("std::span<float> dst", text)
            self.assertIn("std::span<const float> src", text)
            self.assertIn("TODO_REQUIRED: define an oracle", text)

    def test_project_oracle_discovery_is_candidate_not_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Cargo.toml").write_text("[package]\nname='fixture'\nversion='0.1.0'\n")
            source = root / "src.rs"
            source.write_text("pub fn sum(x: &[u8]) -> u64 { x.iter().map(|v| *v as u64).sum() }\n")
            plan = build_plan(self._request(root / "out", source, "sum", root))
            tests = [item for item in plan["project_evidence"]["candidates"] if item["kind"] == "correctness_test"]
            self.assertTrue(tests)
            self.assertTrue(all(item["binding_status"] == "candidate_not_authoritative" for item in tests))
            self.assertIn("discovery is a setup aid", plan["project_evidence"]["claim_boundary"])

    def test_project_evidence_discovers_hash_metric_and_counter_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "benchmarks"
            scripts.mkdir()
            runner = scripts / "replay_benchmark.py"
            runner.write_text(
                "result = {'observable_hash': digest, 'duration_ns': elapsed, 'cache_misses': misses}\n"
            )
            source = root / "kernel.c"
            source.write_text("int sum(const int *p, int n) { int x=0; for(int i=0;i<n;++i)x+=p[i]; return x; }\n")
            plan = build_plan(self._request(root / "out", source, "sum", root))
            kinds = {item["kind"] for item in plan["project_evidence"]["candidates"]}
            self.assertTrue({"observable_field", "metric_field", "counter_field"}.issubset(kinds))
            self.assertTrue(all(
                item["binding_status"] == "candidate_not_authoritative"
                for item in plan["project_evidence"]["candidates"]
            ))

    def test_terminal_status_never_confuses_local_promotion_with_integration(self):
        summary = {"states": {
            "meaningful_semantic_coverage": True,
            "candidate_generated": True,
            "candidate_proved": True,
            "physically_benchmarked": True,
            "application_integrated": False,
            "production_promoted": True,
        }}
        self.assertEqual(terminal_status(summary), "INTEGRATION_REQUIRED")
        summary["states"]["application_integrated"] = True
        self.assertEqual(terminal_status(summary), "PROMOTABLE")

    def test_bounded_c_proof_badge_preserves_composed_local_scope(self):
        badge = _proof_badge({"proof_class": "bounded_c_region", "decisive_artifacts": []})
        self.assertEqual(badge["badge"], "COMPOSED_LOCAL_PROOF")
        self.assertIn("owning wrappers", badge["claim"])

    def test_plan_stage_is_content_addressed_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._request(root / "out", ROOT / "examples" / "clamp.c")
            first = write_plan(request, emit_progress=False)
            second = write_plan(request, emit_progress=False)
            self.assertEqual(first["plan_id"], second["plan_id"])
            self.assertEqual(first["cache"]["plan"], "computed")
            self.assertEqual(second["cache"]["plan"], "reused")

    def test_source_change_invalidates_only_matching_plan_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "kernel.c"
            source.write_text("void transform(float*d,const float*s,unsigned n){for(unsigned i=0;i<n;++i)d[i]=s[i];}\n")
            request = self._request(root / "out", source, project=root)
            first = write_plan(request, emit_progress=False)
            source.write_text("void transform(float*d,const float*s,unsigned n){for(unsigned i=0;i<n;++i)d[i]=s[i]+1;}\n")
            second = write_plan(request, emit_progress=False)
            self.assertEqual(first["cache"]["plan"], "computed")
            self.assertEqual(second["cache"]["plan"], "computed")
            self.assertNotEqual(first["cache"]["stage_key"], second["cache"]["stage_key"])

    def test_selected_project_oracles_become_resume_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._request(root / "out", ROOT / "examples" / "clamp.c")
            first = write_plan(request, emit_progress=False)
            evidence_path = Path(first["scaffolds"]["project_evidence"])
            evidence = yaml.safe_load(evidence_path.read_text())
            evidence["selected"]["correctness_test"] = {"command": ["ctest"], "observable_hash_field": "hash"}
            evidence["selected"]["benchmark"] = {"command": ["bench"], "metric_field": "metric"}
            evidence_path.write_text(yaml.safe_dump(evidence, sort_keys=False))
            second = write_plan(request, emit_progress=False)
            states = {item["state"]: item["reachable"] for item in second["forecast"]["evidence_states"]}
            self.assertTrue(states["physical_measurement"])
            self.assertTrue(states["application_integration"])
            self.assertEqual(second["cache"]["plan"], "computed")
            self.assertEqual(yaml.safe_load(evidence_path.read_text())["selected"], evidence["selected"])

    def test_explicit_contract_is_authoritative_without_scaffold_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract.yaml"
            contract.write_text(yaml.safe_dump({"aliasing": "disjoint", "determinism": "required"}))
            request = OptimizationRequest(
                project=ROOT,
                source=ROOT / "examples" / "clamp.c",
                symbol="transform",
                compile_commands=None,
                contract=contract,
                workload=None,
                profile=None,
                output_directory=root / "out",
                plan_only=True,
            )
            plan = build_plan(request)
            self.assertEqual(plan["contract_candidate"]["facts"]["aliasing"], "disjoint")
            self.assertEqual(plan["contract_candidate"]["authority"], "explicit contract")
            self.assertFalse(plan["contract_candidate"]["suggested_patch"])

    def test_remote_result_identity_and_hmac_fail_closed(self):
        request = {
            "hardware_manifest_sha256": "a" * 64,
            "workload_manifest_sha256": "b" * 64,
            "binary_sha256": "c" * 64,
            "candidate_sha256": "d" * 64,
        }
        result = {"schema_version": "vladder-remote-result-v1", **request, "metric": 10.0}
        signed = sign_remote_result(result, "secret")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "remote-result.json"
            path.write_text(json.dumps(signed))
            self.assertEqual(validate_artifact("remote-result", path)["status"], "pass")
        self.assertEqual(verify_remote_result(signed, request, "secret")["status"], "pass")
        signed["metric"] = 1.0
        self.assertEqual(verify_remote_result(signed, request, "secret")["status"], "fail")

    def test_portfolio_deduplicates_semantically_equivalent_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "two.c"
            source.write_text(
                "void first(float*d,const float*s,unsigned n){for(unsigned i=0;i<n;++i)d[i]=s[i]+1;}\n"
                "void second(float*d,const float*s,unsigned n){for(unsigned i=0;i<n;++i)d[i]=s[i]+1;}\n"
            )
            report = run_portfolio(root, root / "out", max_regions=10, workers=2)
            self.assertEqual(report["region_count"], 2)
            self.assertEqual(report["unique_semantic_roots"], 1)
            self.assertEqual(report["duplicate_count"], 1)
            self.assertEqual(report["workers"], 2)
            validation = validate_artifact("optimization-campaign", root / "out" / "portfolio-summary.json")
            self.assertEqual(validation["status"], "pass")

    def test_campaign_review_prepopulates_objective_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for index, promoted in enumerate((False, True)):
                path = root / f"summary-{index}.json"
                path.write_text(json.dumps({
                    "schema_version": "vladder-promotion-summary-v1",
                    "workflow_kind": "c" if index == 0 else "cpp",
                    "workflow_key": str(index),
                    "proof_class": "bounded_z3",
                    "disposition": "promotable" if promoted else "measured_regression",
                    "promotion_permitted": promoted,
                    "candidate_identity": f"candidate-{index}",
                    "states": {"candidate_generated": True, "physically_benchmarked": True, "application_integrated": promoted},
                    "blockers": [] if promoted else ["below effect floor"],
                    "next_action": "retain" if promoted else "stop",
                    "claim_boundary": "local",
                }))
                paths.append(path)
            review_path = root / "campaign.json"
            review = create_campaign_review_template(paths, review_path, project_name="fixture", project_revision="1234567")
            self.assertEqual(review["scope"]["region_count"], 2)
            self.assertNotIn("TODO", review["evidence"]["benchmark_summary"])
            self.assertEqual(validate_review(review_path)["status"], "pass")

    def test_application_composition_accounts_for_share_overlap_and_amortization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "composition.yaml"
            manifest.write_text(yaml.safe_dump({"regions": [
                {
                    "id": "hot-loop",
                    "baseline_runtime_share_percent": 40.0,
                    "regional_speedup_percent": 25.0,
                    "invocation_frequency_scale": 1.0,
                    "queue_overlap_fraction": 0.0,
                    "amortized_overhead_percent": 0.5,
                }
            ]}))
            report = compose_application_cost(manifest, root / "report.json")
            self.assertEqual(report["status"], "pass")
            self.assertGreater(report["predicted_end_to_end_speedup_percent"], 0.0)
            self.assertTrue(report["confirmation_required"])

    def test_paired_benchmark_stops_when_interval_is_decisive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "runner.py"
            runner.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print(json.dumps({'metric': 100 if sys.argv[1] == 'baseline' else 80, 'hash': 'same'}))\n"
            )
            runner.chmod(0o755)
            manifest = root / "benchmark.yaml"
            manifest.write_text(yaml.safe_dump({
                "executable": str(runner),
                "baseline_args": ["baseline"],
                "candidate_args": ["candidate"],
                "metric_key": "metric",
                "observable_key": "hash",
                "minimum_processes": 2,
                "maximum_processes": 6,
                "bootstrap_rounds": 250,
                "minimum_effect_percent": 1.0,
                "stopping_rule": {"target_ci_width_percent": 0.1},
            }))
            report = run_paired_benchmark(manifest, root / "out")
            self.assertEqual(report["process_count"], 2)
            self.assertTrue(report["experiment_design"]["stopped_early"])
            self.assertEqual(report["semantic_parity"], "PASS")

    def test_can_optimize_cli_emits_concise_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable, "-m", "vladder", "can-optimize", "transform",
                    "--source", str(ROOT / "examples" / "clamp.c"),
                    "--project", str(ROOT), "--out-dir", directory, "--quiet",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("vLadder feasibility:", completed.stdout)
            self.assertTrue((Path(directory) / "optimization-plan.json").exists())

    def test_optimize_stops_cleanly_at_early_cpp_blocker(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable, "-m", "vladder", "optimize",
                    str(ROOT / "examples" / "cpp_regions" / "supported_span.cpp"),
                    "--function", "transform", "--project", str(ROOT),
                    "--out-dir", directory, "--quiet",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            disposition = json.loads((Path(directory) / "disposition.json").read_text())
            self.assertEqual(disposition["terminal_status"], "NO_COVERAGE")
            self.assertTrue(disposition["failures"])

    def test_canonical_cpp_route_uses_lazy_executable_source_search(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "compact.cpp"
            source.write_text(
                "#include <cstddef>\n#include <cstdint>\n"
                "std::size_t compact(std::uint32_t* __restrict out_indices, "
                "std::uint64_t* __restrict out_values, std::size_t out_capacity, "
                "const std::uint64_t* __restrict current, const std::uint64_t* __restrict baseline, "
                "std::size_t n) noexcept {\n"
                "  if (n > 64 || out_capacity < n) return SIZE_MAX;\n"
                "  std::size_t output_count = 0;\n"
                "  for (std::size_t i=0;i<n;++i) if (current[i] != baseline[i]) {\n"
                "    out_indices[output_count] = static_cast<std::uint32_t>(i);\n"
                "    out_values[output_count] = current[i]; ++output_count; }\n"
                "  return output_count;\n}\n"
            )
            compile_commands = root / "compile_commands.json"
            compile_commands.write_text(json.dumps([{
                "directory": str(root),
                "file": str(source),
                "arguments": ["clang++", "-std=c++20", "-c", str(source)],
            }]))
            request = OptimizationRequest(
                project=root,
                source=source,
                symbol="compact",
                compile_commands=compile_commands,
                contract=None,
                workload=None,
                profile=None,
                output_directory=root / "out",
                plan_only=False,
            )
            report = run_optimization(request, emit_progress=False)
            self.assertEqual(report["disposition"]["terminal_status"], "NO_BENCHMARK")
            self.assertTrue(report["summary"]["states"]["candidate_proved"])
            self.assertTrue((root / "out/executable-search/executable-search-trace.json").is_file())


if __name__ == "__main__":
    unittest.main()
