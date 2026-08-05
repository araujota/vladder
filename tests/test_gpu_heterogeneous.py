from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from vladder.agent_workflow import initialize_workflow_manifest, run_agent_workflow
from vladder.device_protocol import enumerate_dma_routes, verify_device_protocol
from vladder.gpu_ir import (
    GPUExecutionPlan,
    capture_gpu_kernel,
    enumerate_gpu_plans,
    estimate_gpu_cost,
    load_gpu_architecture,
)
from vladder.gpu_physical import normalize_gpu_counters, rank_gpu_candidates
from vladder.gpu_workflow import (
    capture_gpu_workflow,
    gpu_support_matrix,
    rank_gpu_workflow,
    synthesize_gpu_workflow,
    verify_gpu_workflow,
)


ROOT = Path(__file__).resolve().parents[1]
GPU = ROOT / "examples" / "gpu"


class HeterogeneousGPUTests(unittest.TestCase):
    def test_ptx_capture_uses_shared_semantic_vocabulary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capture = capture_gpu_kernel(GPU / "vector_scale.ptx", Path(directory))
        self.assertEqual(capture.status, "captured")
        self.assertEqual(capture.resources.local_size, (256, 1, 1))
        self.assertEqual(capture.resources.registers_per_thread, 22)
        self.assertFalse(capture.unsupported_operations)
        kinds = {node.kind for node in capture.graph.nodes}
        self.assertTrue({"DispatchGrid", "Workgroup", "Subgroup", "Lane", "GlobalMemoryTransaction", "ResourceUse"} <= kinds)
        self.assertEqual(capture.graph.source_language, "ptx")
        self.assertIn("host queue and API behavior", capture.graph.excluded_claims)

    @unittest.skipUnless(
        shutil.which("nvcc") and Path("/usr/local/cuda/include/cuda_runtime.h").is_file(),
        "CUDA source toolchain unavailable",
    )
    def test_cuda_source_capture_resolves_toolkit_relative_nvcc(self) -> None:
        source_text = """\
extern \"C\" __global__ void scale(float *dst, const float *src, float factor, int n) {
    int i = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
    if (i < n) dst[i] = src[i] * factor;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scale.cu"
            source.write_text(source_text)
            capture = capture_gpu_kernel(source, root / "capture", entry_point="scale")
        self.assertEqual(capture.status, "captured")
        self.assertEqual(capture.dialect, "cuda-ptx")
        self.assertEqual(capture.entry_point, "scale")
        self.assertIn("cuda_source", capture.artifacts)

    @unittest.skipUnless(
        all(shutil.which(name) for name in ("glslangValidator", "spirv-val", "spirv-dis")),
        "SPIR-V toolchain unavailable",
    )
    def test_spirv_capture_is_complete_for_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capture = capture_gpu_kernel(ROOT / "examples" / "shaders" / "scale.comp", Path(directory))
        self.assertEqual(capture.status, "captured")
        self.assertFalse(capture.unsupported_operations)
        self.assertEqual(capture.resources.local_size, (64, 1, 1))
        self.assertGreater(capture.resources.global_loads, 0)
        self.assertGreater(capture.resources.global_stores, 0)

    def test_resource_model_reports_active_limit_and_never_promotes(self) -> None:
        architecture = load_gpu_architecture(GPU / "architectures" / "portable-test.yaml")
        with tempfile.TemporaryDirectory() as directory:
            capture = capture_gpu_kernel(GPU / "vector_scale.ptx", Path(directory))
        constrained = replace(capture, resources=replace(capture.resources, registers_per_thread=128))
        plan = GPUExecutionPlan("register-heavy", (256, 1, 1), 1, 1, "direct-global", "baseline-scope", 0, "launch_plan", (), ())
        cost = estimate_gpu_cost(constrained, architecture, plan)
        self.assertTrue(cost.feasible)
        self.assertIn("registers", cost.limiting_resources)
        self.assertLess(cost.occupancy, 1.0)
        self.assertIn("speed prediction", cost.assumptions[0])

    @unittest.skipUnless(
        all(shutil.which(name) for name in ("glslangValidator", "spirv-val", "spirv-dis")),
        "SPIR-V toolchain unavailable",
    )
    def test_spirv_geometry_uses_source_emitter_and_fails_closed_for_binary_only(self) -> None:
        architecture = load_gpu_architecture(GPU / "architectures" / "portable-test.yaml")
        with tempfile.TemporaryDirectory() as directory:
            capture = capture_gpu_kernel(ROOT / "examples" / "shaders" / "scale.comp", Path(directory))
            source_plans = enumerate_gpu_plans(capture, architecture, maximum_candidates=256)
            source_changed = [item for item in source_plans if item.local_size != capture.resources.local_size]
            self.assertTrue(any(item.realization_class == "source_rewrite" for item in source_changed))

            binary_capture = capture_gpu_kernel(
                Path(capture.artifacts["module"]),
                Path(directory) / "binary-capture",
            )
            binary_plans = enumerate_gpu_plans(binary_capture, architecture, maximum_candidates=256)
            binary_changed = [item for item in binary_plans if item.local_size != binary_capture.resources.local_size]
            self.assertTrue(binary_changed)
            self.assertTrue(all(item.realization_class == "adapter_required" for item in binary_changed))

    def test_queue_dma_and_presentation_counterexamples_fail_closed(self) -> None:
        cases = (
            ("queue-valid.yaml", "PASS"), ("queue-invalid.yaml", "FAIL"),
            ("dma-valid.yaml", "PASS"), ("dma-invalid.yaml", "FAIL"),
            ("presentation-valid.yaml", "PASS"), ("presentation-invalid.yaml", "FAIL"),
        )
        for name, expected in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                evidence = verify_device_protocol(GPU / "protocols" / name, Path(directory))
                self.assertEqual(evidence.status, expected)
                if expected == "FAIL":
                    self.assertTrue(evidence.issues)
                    self.assertTrue(any(item["status"] == "FAIL" for item in evidence.obligations))

    def test_interleaved_manifest_entries_preserve_same_queue_order(self) -> None:
        manifest = {
            "kind": "queue",
            "name": "interleaved-queue-order",
            "resources": [{"id": "buffer", "owner": "compute"}],
            "operations": [
                {"id": "produce", "queue": "q0", "queue_family": "compute", "accesses": [{"resource": "buffer", "mode": "write", "stage": "compute"}]},
                {"id": "unrelated", "queue": "q1", "queue_family": "compute", "accesses": []},
                {"id": "consume", "queue": "q0", "queue_family": "compute", "accesses": [{"resource": "buffer", "mode": "read", "stage": "compute"}]},
            ],
            "barriers": [{"src": "produce", "dst": "consume", "resource": "buffer"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "queue.yaml"
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
            evidence = verify_device_protocol(manifest_path, root / "proof")
        self.assertEqual(evidence.status, "PASS")

    def test_dma_route_search_accounts_for_topology(self) -> None:
        raw = yaml.safe_load((GPU / "protocols" / "dma-valid.yaml").read_text())
        routes = enumerate_dma_routes(raw)
        self.assertEqual(routes[0]["route"], ["gpu0", "nic0"])
        self.assertTrue(routes[0]["direct"])
        self.assertGreater(routes[0]["estimated_time_ns"], 900)

    def test_counter_replay_is_attribution_only(self) -> None:
        evidence = normalize_gpu_counters(GPU / "counters" / "baseline.yaml")
        self.assertTrue(evidence.profiler_distorts_timing)
        self.assertTrue(evidence.serialized_execution)
        self.assertFalse(evidence.to_dict()["timing_usable_for_ranking"])
        self.assertIn("dram_bytes", {item.category for item in evidence.counters})

    def test_simulated_runner_exercises_ranking_without_physical_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = rank_gpu_candidates(GPU / "ranking.yaml", Path(directory))
        candidate = report["candidates"][0]
        self.assertEqual(candidate["semantic_parity"], "PASS")
        self.assertEqual(candidate["classification"], "simulated_or_unclassified_evidence")
        self.assertFalse(candidate["promotable"])
        self.assertFalse(report["promotion"]["promotable"])
        self.assertFalse(candidate["counter_comparison"]["profiler_timing_usable_for_ranking"])

    @unittest.skipUnless(
        all(shutil.which(name) for name in ("glslangValidator", "spirv-val", "spirv-opt", "spirv-dis")),
        "SPIR-V toolchain unavailable",
    )
    def test_manifest_workflow_captures_synthesizes_verifies_and_ranks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = capture_gpu_workflow(GPU / "workflow.yaml", root / "capture")
            synthesis = synthesize_gpu_workflow(GPU / "workflow.yaml", root / "synthesis")
            proof = verify_gpu_workflow(GPU / "workflow.yaml", root / "proof")
            ranking = rank_gpu_workflow(GPU / "workflow.yaml", root / "ranking")
        self.assertEqual(capture["status"], "pass")
        self.assertEqual(capture["heterogeneous_graph"]["schema_version"], "semantic-flow-v2")
        self.assertGreater(synthesis["candidate_count"], 3)
        self.assertFalse(synthesis["promotion"]["promotable"])
        self.assertEqual(proof["status"], "PASS")
        self.assertFalse(ranking["promotion"]["promotable"])

    def test_agent_workflow_accepts_gpu_as_a_first_class_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = initialize_workflow_manifest("gpu", root / "template.yaml")
            self.assertEqual(generated["region"]["kind"], "gpu")
            manifest = root / "workflow.yaml"
            manifest.write_text(yaml.safe_dump({
                "schema_version": "vladder-agent-workflow-v1",
                "name": "gpu-capture",
                "region": {"kind": "gpu", "action": "capture", "manifest": str(GPU / "workflow.yaml")},
                "contract": {"identity": "gpu-fixture", "exact": True},
                "workload": {"identity": "fixture", "held_out": True},
            }))
            summary = run_agent_workflow(manifest, root / "out")
        self.assertEqual(summary["workflow_kind"], "gpu")
        self.assertTrue(summary["states"]["meaningful_semantic_coverage"])
        self.assertFalse(summary["states"]["production_promoted"])

    def test_support_matrix_names_tooling_and_claim_boundaries(self) -> None:
        support = gpu_support_matrix()
        self.assertEqual(support["grammar_version"], "heterogeneous-execution-v1")
        self.assertEqual(support["protocol_graphs"]["queue"], "operational")
        self.assertIn("device runner", support["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
