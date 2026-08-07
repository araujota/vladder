from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
import subprocess
import xml.etree.ElementTree as ET

import yaml

from vladder.heterogeneous_plan import audit_heterogeneous_project, rank_heterogeneous_plans, synthesize_heterogeneous_plans


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "gpu" / "plans"


class HeterogeneousPlanV2Tests(unittest.TestCase):
    def test_all_plan_families_emit_proved_deterministic_graphs(self):
        for name in ("gpu-compaction.yaml", "sparse-policy.yaml", "sparse-exact-size-policy.yaml", "queue-overlap.yaml", "presentation-policy.yaml"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                first = synthesize_heterogeneous_plans(EXAMPLES / name, output / "first")
                second = synthesize_heterogeneous_plans(EXAMPLES / name, output / "second")
                self.assertGreater(first["candidate_count"], 0)
                self.assertEqual(
                    [item["graph"]["graph_hash"] for item in first["candidates"]],
                    [item["graph"]["graph_hash"] for item in second["candidates"]],
                )
                for candidate in first["candidates"]:
                    self.assertEqual(candidate["proof"]["status"], "PROVED")
                    graphml = Path(candidate["artifacts"]["graphml"])
                    self.assertTrue(graphml.exists())
                    ET.parse(graphml)
                    self.assertFalse(candidate["promotable"])

    def test_generated_cpp_and_cuda_compile_when_toolchains_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            sparse = synthesize_heterogeneous_plans(EXAMPLES / "sparse-policy.yaml", output / "sparse")
            if shutil.which("clang++") or shutil.which("g++"):
                self.assertTrue(all(item["artifacts"]["compile_status"] == "pass" for item in sparse["candidates"]))
            gpu = synthesize_heterogeneous_plans(EXAMPLES / "gpu-compaction.yaml", output / "gpu")
            expected = "pass" if shutil.which("nvcc") else "nvcc_required"
            self.assertTrue(all(item["artifacts"]["compile_status"] == expected for item in gpu["candidates"]))

    def test_generated_sparse_policy_executes_exact_and_fail_unchanged_paths(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            self.skipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = synthesize_heterogeneous_plans(EXAMPLES / "sparse-policy.yaml", root / "out")
            candidate = report["candidates"][0]
            source = Path(candidate["artifacts"]["source"])
            function = candidate["id"].replace("-", "_")
            harness = root / "harness.cpp"
            harness.write_text(
                f'#include "{source}"\n'
                "int main() {\n"
                "  const std::uint64_t current[4] = {1, 9, 3, 8};\n"
                "  const std::uint64_t baseline[4] = {1, 2, 3, 4};\n"
                "  std::uint32_t indices[4] = {99, 99, 99, 99}; std::uint64_t values[4] = {77, 77, 77, 77}; std::uint8_t bitmap[1] = {0};\n"
                f"  auto ok = {function}(indices, values, bitmap, 4, current, baseline, 4);\n"
                "  if (!ok.ok || ok.extent != 2 || indices[0] != 1 || indices[1] != 3 || values[0] != 9 || values[1] != 8) return 1;\n"
                "  indices[0] = 99; values[0] = 77;\n"
                f"  auto fail = {function}(indices, values, bitmap, 1, current, baseline, 4);\n"
                "  return fail.ok || fail.extent != 2 || indices[0] != 99 || values[0] != 77;\n"
                "}\n"
            )
            executable = root / "harness"
            subprocess.run([compiler, "-std=c++20", "-O2", str(harness), "-o", str(executable)], check=True)
            subprocess.run([str(executable)], check=True)

    def test_exact_size_policy_preserves_canonical_ties_across_evaluation_orders(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            self.skipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = synthesize_heterogeneous_plans(EXAMPLES / "sparse-exact-size-policy.yaml", root / "out")
            self.assertEqual(report["candidate_count"], 4)
            for index, candidate in enumerate(report["candidates"]):
                source = Path(candidate["artifacts"]["source"])
                function = candidate["id"].replace("-", "_")
                harness = root / f"exact-{index}.cpp"
                harness.write_text(
                    f'#include "{source}"\n'
                    f"int main() {{ auto a = {function}(10, 8, 8, 20); auto b = {function}(7, 7, 7, 7); return a.encoding != 1 || a.bytes != 8 || b.encoding != 0 || b.bytes != 7; }}\n"
                )
                executable = root / f"exact-{index}"
                subprocess.run([compiler, "-std=c++20", "-O2", str(harness), "-o", str(executable)], check=True)
                subprocess.run([str(executable)], check=True)

    def test_queue_search_exposes_modeled_overlap_and_verified_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            report = synthesize_heterogeneous_plans(EXAMPLES / "queue-overlap.yaml", Path(directory))
            self.assertTrue(any(item["static_cost"]["modeled_overlap_ns"] > 0 for item in report["candidates"]))
            self.assertTrue(all(item["realization_class"] == "executable_runtime_plan" for item in report["candidates"]))

    def test_missing_attribution_and_unbounded_recursion_fail_closed(self):
        raw = yaml.safe_load((EXAMPLES / "sparse-policy.yaml").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.yaml"
            missing.write_text(yaml.safe_dump({key: value for key, value in raw.items() if key != "attribution"}))
            with self.assertRaisesRegex(ValueError, "attribution"):
                synthesize_heterogeneous_plans(missing, root / "missing")
            raw["recursion"] = {"recursive_scc": ["policy"], "maximum_depth": 0}
            recursive = root / "recursive.yaml"
            recursive.write_text(yaml.safe_dump(raw))
            with self.assertRaisesRegex(ValueError, "maximum_depth"):
                synthesize_heterogeneous_plans(recursive, root / "recursive")

    def test_simulated_runner_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text("{}")
            candidate.write_text("{}")
            runner = root / "runner.py"
            runner.write_text(
                "import json,sys\n"
                "candidate='candidate' in sys.argv[1]\n"
                "print(json.dumps({'total_time_ns':80 if candidate else 100,'output_hash':'same','state_hash':'same','device_identity':'sim','evidence_class':'simulated'}))\n"
            )
            manifest = root / "rank.yaml"
            manifest.write_text(yaml.safe_dump({
                "hardware_identity": "sim",
                "baseline": {"id": "base", "plan": str(baseline)},
                "candidates": [{"id": "candidate", "plan": str(candidate)}],
                "runner": {"command": ["python3", str(runner), "{plan}"], "processes": 3, "bootstrap_rounds": 50, "minimum_effect_percent": 1, "evidence_class": "simulated"},
            }))
            report = rank_heterogeneous_plans(manifest, root / "rank")
            self.assertEqual(report["candidates"][0]["classification"], "simulated_or_unclassified_evidence")
            self.assertFalse(report["promotion"]["promotable"])

    def test_project_audit_recognizes_general_surfaces_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            shader = root / "compact.comp.glsl"
            shader.write_text("shared uint scan[32]; void main(){ uint mask=1; barrier(); uint offset=1; uint destination=scan[offset]; }\n")
            source = root / "pipeline.cpp"
            source.write_text("void f(){ auto dense_size=1; auto sparse_size=2; auto full_size=3; vkQueueSubmit(); vkQueuePresentKHR(); }\n")
            before = subprocess.run(["git", "status", "--porcelain=v1"], cwd=root, text=True, stdout=subprocess.PIPE, check=True).stdout
            report = audit_heterogeneous_project(root, Path(directory) / "audit")
            after = subprocess.run(["git", "status", "--porcelain=v1"], cwd=root, text=True, stdout=subprocess.PIPE, check=True).stdout
            self.assertEqual(before, after)
            self.assertTrue(report["no_write_validation"])
            self.assertIn("gpu-stable-compaction", report["family_counts"])
            self.assertIn("queue-overlap", report["family_counts"])
            self.assertIn("presentation-policy", report["family_counts"])
            self.assertIn("sparse-update-policy", report["family_counts"])


if __name__ == "__main__":
    unittest.main()
