from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

from vladder.agent_workflow import initialize_workflow_manifest, run_agent_workflow
from vladder.device_protocol import enumerate_dma_routes, verify_device_protocol
from vladder.device_topology import (
    emit_dma_protocol_template,
    emit_presentation_protocol_template,
    emit_vulkan_queue_protocol_template,
    probe_device_topology,
)
from vladder.gpu_ir import (
    GPUExecutionPlan,
    capture_gpu_kernel,
    enumerate_gpu_plans,
    estimate_gpu_cost,
    load_gpu_architecture,
)
from vladder.gpu_physical import normalize_gpu_counters, rank_gpu_candidates
from vladder.cuda_runtime import probe_cuda_architecture, run_cuda_artifact
from vladder.cuda_synthesis import (
    extract_cuda_pointwise_region,
    optimize_cuda_pointwise,
    prove_cuda_schedule,
    render_cuda_schedule,
)
from vladder.gpu_workflow import (
    capture_gpu_workflow,
    gpu_support_matrix,
    rank_gpu_workflow,
    synthesize_gpu_workflow,
    verify_gpu_workflow,
)


ROOT = Path(__file__).resolve().parents[1]
GPU = ROOT / "examples" / "gpu"


def _cuda_device_available() -> bool:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    result = subprocess.run(
        [nvidia_smi, "-L"], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


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
            "barriers": [{
                "src": "produce", "dst": "consume", "resource": "buffer",
                "src_stage": "compute", "dst_stage": "compute",
                "src_access": "shader_write", "dst_access": "shader_read",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "queue.yaml"
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
            evidence = verify_device_protocol(manifest_path, root / "proof")
        self.assertEqual(evidence.status, "PASS")

    def test_queue_barrier_with_wrong_stage_scope_fails(self) -> None:
        raw = yaml.safe_load((GPU / "protocols" / "queue-valid.yaml").read_text())
        raw["barriers"][0]["dst_stage"] = "transfer"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "queue.yaml"
            manifest.write_text(yaml.safe_dump(raw, sort_keys=False))
            evidence = verify_device_protocol(manifest, root / "proof")
        self.assertEqual(evidence.status, "FAIL")
        hazard = next(item for item in evidence.issues if item.category == "hazard")
        self.assertFalse(hazard.counterexample["memory_visibility"])

    def test_binary_semaphore_requires_consume_before_resignal(self) -> None:
        base = {
            "kind": "queue", "name": "binary-semaphore", "resources": [], "barriers": [],
            "semaphores": [{"id": "ready", "type": "binary"}],
            "operations": [
                {"id": "signal-0", "queue": "q0", "signals": [{"semaphore": "ready"}]},
                {"id": "wait-0", "queue": "q1", "waits": [{"semaphore": "ready"}]},
                {"id": "signal-1", "queue": "q0", "signals": [{"semaphore": "ready"}]},
                {"id": "wait-1", "queue": "q1", "waits": [{"semaphore": "ready"}]},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_path = root / "valid.yaml"
            valid_path.write_text(yaml.safe_dump(base, sort_keys=False))
            valid = verify_device_protocol(valid_path, root / "valid-proof")
            invalid_raw = json.loads(json.dumps(base))
            invalid_raw["operations"].pop(1)
            invalid_path = root / "invalid.yaml"
            invalid_path.write_text(yaml.safe_dump(invalid_raw, sort_keys=False))
            invalid = verify_device_protocol(invalid_path, root / "invalid-proof")
        self.assertEqual(valid.status, "PASS")
        self.assertEqual(invalid.status, "FAIL")
        self.assertTrue(any(item.category == "binary_semaphore" for item in invalid.issues))

    def test_presentation_state_machine_accepts_two_complete_cycles(self) -> None:
        events = []
        for _ in range(2):
            events.extend({"type": event, "image": "image0"} for event in (
                "acquire", "render_complete", "present", "scanout", "release"
            ))
        raw = {
            "kind": "presentation",
            "name": "two-cycles",
            "images": ["image0"],
            "present_mode": "fifo",
            "deadline_policy": "next_vblank",
            "events": events,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "presentation.yaml"
            manifest.write_text(yaml.safe_dump(raw, sort_keys=False))
            evidence = verify_device_protocol(manifest, root / "proof")
        self.assertEqual(evidence.status, "PASS")
        lifecycle = next(item for item in evidence.obligations if item["id"] == "presentation.lifecycle.image0")
        self.assertEqual(lifecycle["detail"]["completed_cycles"], 2)

    def test_dma_route_search_accounts_for_topology(self) -> None:
        raw = yaml.safe_load((GPU / "protocols" / "dma-valid.yaml").read_text())
        routes = enumerate_dma_routes(raw)
        self.assertEqual(routes[0]["route"], ["gpu0", "nic0"])
        self.assertTrue(routes[0]["direct"])
        self.assertGreater(routes[0]["estimated_time_ns"], 900)

    def test_live_bound_protocol_templates_validate_capabilities_and_fail_closed(self) -> None:
        topology = {
            "topology_hash": "observed-topology",
            "devices": [
                {
                    "id": "gpu0", "type": "gpu", "capabilities": ["cuda"],
                    "vulkan_binding": {
                        "matched": True, "device_uuid": "gpu-uuid",
                        "timeline_semaphore": True, "synchronization2": True,
                        "queue_families": [{"index": 2, "queue_count": 2, "flags": ["compute", "transfer"]}],
                    },
                },
                {"id": "host0", "type": "host-memory", "capabilities": ["host_staging"]},
                {"id": "nic0", "type": "nic", "capabilities": ["network_endpoint"]},
            ],
            "links": [
                {"from": "gpu0", "to": "host0", "direct": False, "bidirectional": True},
                {"from": "host0", "to": "nic0", "direct": False, "bidirectional": True},
            ],
            "routes": {"nic0": [{"route": ["gpu0", "host0", "nic0"], "direct": False}]},
            "presentation": {
                "capability_hash": "drm-observation", "connectors": [
                    {"id": "card0-DP-1", "status": "disconnected", "pci_bdf": "0000:01:00.0", "modes": []}
                ],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_path = root / "queue.yaml"
            queue = emit_vulkan_queue_protocol_template(topology, queue_path)
            queue_evidence = verify_device_protocol(queue_path, root / "queue-proof")
            queue["operations"][0]["required_capabilities"] = ["graphics"]
            bad_queue_path = root / "bad-queue.yaml"
            bad_queue_path.write_text(yaml.safe_dump(queue, sort_keys=False))
            bad_queue = verify_device_protocol(bad_queue_path, root / "bad-queue-proof")
            presentation_path = root / "presentation.yaml"
            emit_presentation_protocol_template(topology, presentation_path)
            presentation = verify_device_protocol(presentation_path, root / "presentation-proof")
            dma_path = root / "dma.yaml"
            dma = emit_dma_protocol_template(topology, "nic0", dma_path)
            dma_evidence = verify_device_protocol(dma_path, root / "dma-proof")
        self.assertEqual(queue_evidence.status, "PASS")
        self.assertEqual(bad_queue.status, "FAIL")
        self.assertEqual(presentation.status, "FAIL")
        self.assertFalse(dma["transfer"]["direct"])
        self.assertEqual(dma_evidence.status, "FAIL")

    @unittest.skipUnless(
        shutil.which("nvcc") and shutil.which("vulkaninfo") and
        Path("/sys/bus/pci/devices").is_dir() and _cuda_device_available(),
        "live CUDA/Vulkan/Linux topology unavailable",
    )
    def test_live_topology_joins_cuda_and_vulkan_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = probe_device_topology(Path(directory) / "topology.json")
        gpu = next(item for item in report["devices"] if item["type"] == "gpu")
        self.assertTrue(gpu["vulkan_binding"]["matched"])
        self.assertTrue(gpu["vulkan_binding"]["queue_families"])
        if not gpu["gpu_direct_rdma_supported"]:
            self.assertFalse(report["direct_gpudirect_targets"])
        self.assertIn(report["presentation"]["status"], {"PASS", "NO_CONNECTED_CONNECTOR"})

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
        self.assertTrue(support["protocol_graphs"]["queue"].startswith("operational"))
        self.assertIn("native runner", support["claim_boundary"])

    def test_cuda_pointwise_schedule_has_literal_and_partition_proof(self) -> None:
        source = GPU / "cuda" / "affine.cu"
        region = extract_cuda_pointwise_region(source, "vladder_transform")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate.cu"
            candidate.write_text(render_cuda_schedule(region, 4))
            proof = prove_cuda_schedule(
                region,
                threads=128,
                elements_per_thread=4,
                logical_extent=1003,
                candidate_source=candidate,
                output_directory=root / "proof",
            )
        self.assertEqual(proof["status"], "PASS")
        self.assertEqual(
            {item["id"] for item in proof["obligations"]},
            {
                "cuda.schedule.coverage", "cuda.schedule.injective",
                "cuda.schedule.size_t_no_wrap", "cuda.expression.literal_identity",
            },
        )

    @unittest.skipUnless(
        shutil.which("nvcc") and _cuda_device_available(),
        "CUDA device toolchain unavailable",
    )
    def test_cuda_pointwise_full_physical_path_fails_closed_without_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe = probe_cuda_architecture(root / "architecture.yaml", measure_bandwidth=False)
            architecture = load_gpu_architecture(probe["architecture"])
            report = optimize_cuda_pointwise(
                GPU / "cuda" / "affine.cu",
                "vladder_transform",
                architecture,
                root / "optimization",
                logical_extent=1 << 18,
                thread_sizes=(128,),
                unroll_factors=(1,),
                baseline_threads=256,
                warmup=2,
                iterations=5,
                static_finalists=1,
                processes=2,
                minimum_effect_percent=100.0,
                bootstrap_rounds=100,
                seed=9,
                collect_counters=False,
            )
            candidate = report["synthesis"]["static_finalists"][0]
            baseline_result = run_cuda_artifact(Path(report["synthesis"]["baseline"]["artifact"]))
            candidate_result = run_cuda_artifact(Path(candidate["artifact"]))
        self.assertEqual(report["ranking"]["runner_backend"], "cuda-artifact-v1")
        self.assertEqual(report["ranking"]["candidates"][0]["semantic_parity"], "PASS")
        self.assertEqual(baseline_result["output_hash"], candidate_result["output_hash"])
        self.assertFalse(report["promotion"]["promotable"])
        self.assertIsNone(report["replacement"])


if __name__ == "__main__":
    unittest.main()
