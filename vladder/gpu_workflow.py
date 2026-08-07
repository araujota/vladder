from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .device_protocol import DeviceProtocolEvidence, enumerate_dma_routes, verify_device_protocol
from .gpu_ir import (
    GPU_GRAMMAR_VERSION,
    GPUArchitecture,
    GPUKernelCapture,
    capture_gpu_kernel,
    enumerate_gpu_plans,
    load_gpu_architecture,
    materialize_gpu_plan,
    prove_gpu_execution_plan,
    rank_static_gpu_plans,
)
from .gpu_physical import rank_gpu_candidates
from .language_adapter import (
    ProtocolTransition,
    SemanticEffect,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    obligation,
)
from .shader_workflow import SPIRV_RECIPES, synthesize_shader


GPU_WORKFLOW_SCHEMA_VERSION = "vladder-gpu-workflow-v1"


def gpu_support_matrix() -> dict[str, Any]:
    tools = {
        name: shutil.which(name)
        for name in (
            "glslangValidator", "spirv-as", "spirv-val", "spirv-opt", "spirv-dis",
            "nvcc", "nvdisasm", "cuobjdump", "nvidia-smi", "vulkaninfo", "nsys",
            "ncu", "rocprofv3",
        )
    }
    device = _local_nvidia_identity()
    return {
        "schema_version": "vladder-heterogeneous-support-v1",
        "grammar_version": GPU_GRAMMAR_VERSION,
        "kernel_capture": {
            "spirv": "operational" if all(tools[name] for name in ("spirv-val", "spirv-opt", "spirv-dis")) else "toolchain_required",
            "ptx": "operational",
            "cuda": "operational" if tools["nvcc"] else "nvcc_required_use_ptx_capture",
        },
        "typed_spirv_semantics": {
            "logical": "operational",
            "unsigned_division_remainder": "operational_with_validity_domain",
            "dot_matrix": "operational_with_numeric_policy",
            "image": "operational_with_descriptor_contract",
            "cooperative_matrix": "operational_with_capability_shape_and_numeric_contract",
        },
        "executable_grammars": {
            "cuda-pointwise-schedule-v1": "operational" if tools["nvcc"] else "nvcc_required",
            "glsl-workgroup-source-rewrite": "operational" if tools["glslangValidator"] else "glslang_required",
            "gpu-stable-compaction-v2": "operational" if tools["nvcc"] else "source_generation_only_nvcc_required",
            "queue-overlap-v2": "operational_runtime_plan_application_binding_required",
            "sparse-update-policy-v2": "operational_generated_cpp",
            "presentation-policy-v2": "operational_runtime_plan_physical_display_runner_required",
            "opaque-ptx-code-shape": "adapter_required",
            "opaque-spirv-code-shape": "adapter_required",
        },
        "cuda_runtime": {
            "device_probe": "operational" if tools["nvcc"] else "nvcc_required",
            "jit_resource_inspection": "operational" if tools["nvcc"] else "nvcc_required",
            "exact_output_runner": "operational" if tools["nvcc"] else "nvcc_required",
            "clean_event_timing": "operational" if tools["nvcc"] else "nvcc_required",
            "nsight_counter_collection": "operational" if tools["ncu"] else "ncu_required",
        },
        "static_models": {
            "occupancy": "operational",
            "registers": "PTX declarations or runner/compiler metadata; unavailable from portable SPIR-V",
            "shared_memory": "operational for declared/compiler-reported bytes",
            "memory_transactions": "operational under architecture-manifest assumptions",
        },
        "protocol_graphs": {
            "queue": "operational with live Vulkan queue-family binding",
            "dma": "operational with live PCIe/IOMMU/NIC/RDMA route binding",
            "presentation": "operational with live DRM connector binding",
        },
        "topology_probe": {
            "cuda_vulkan_uuid_binding": "operational" if tools["vulkaninfo"] and tools["nvcc"] else "toolchain_required",
            "pcie_iommu_nic_rdma": "operational on Linux sysfs",
            "drm_connectors": "operational on Linux sysfs",
            "runtime_transfer_or_scanout": "application_runner_required",
        },
        "physical_ranking": "operational with exact-output and clean device-timestamp runner",
        "counter_adapters": {
            "CUPTI/Nsight": "manifest import" if not tools["ncu"] else "tool plus manifest import",
            "ROCprofiler": "manifest import" if not tools["rocprofv3"] else "tool plus manifest import",
            "Vulkan performance query": "application runner import",
        },
        "local_nvidia_device": device,
        "tools": tools,
        "claim_boundary": (
            "bounded CUDA pointwise has a native runner, and bounded stable compaction has a source/launch lowerer; queue, "
            "sparse, and presentation policies emit verified executable plans, while final driver "
            "scheduling, DMA completion, network delivery, and visible presentation require concrete runners"
        ),
    }


def capture_gpu_workflow(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path, output_directory, raw = _load_manifest(manifest_path, output_directory)
    capture, architecture = _capture_from_manifest(raw, manifest_path, output_directory / "kernel")
    protocol_evidence = _protocols_from_manifest(raw, manifest_path, output_directory / "protocols")
    composed = _compose_execution_graph(capture, architecture, protocol_evidence, raw)
    graph_path = output_directory / "heterogeneous-execution-graph.json"
    graph_path.write_text(json.dumps(composed.to_dict(), indent=2, sort_keys=True) + "\n")
    report = {
        "schema_version": GPU_WORKFLOW_SCHEMA_VERSION,
        "action": "capture",
        "status": "pass" if capture.status == "captured" else "partial",
        "manifest": str(manifest_path),
        "manifest_hash": canonical_hash(raw),
        "kernel": capture.to_dict(),
        "architecture": architecture.to_dict(),
        "protocols": [item.to_dict() for item in protocol_evidence],
        "heterogeneous_graph": composed.to_dict(),
        "artifacts": {"heterogeneous_graph": str(graph_path)},
        "next_action": "run gpu synthesize; resolve unsupported operations before claiming complete semantic capture" if capture.unsupported_operations else "run gpu synthesize",
    }
    _write_report(output_directory, report)
    return report


def synthesize_gpu_workflow(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path, output_directory, raw = _load_manifest(manifest_path, output_directory)
    capture, architecture = _capture_from_manifest(raw, manifest_path, output_directory / "kernel")
    logical_extent = raw.get("contract", {}).get("logical_extent")
    if isinstance(logical_extent, list):
        logical_extent = _product(int(item) for item in logical_extent)
    plans = enumerate_gpu_plans(
        capture,
        architecture,
        logical_extent=int(logical_extent) if logical_extent is not None else None,
        maximum_candidates=int(raw.get("search", {}).get("maximum_candidates", 256)),
    )
    static_rows = rank_static_gpu_plans(capture, architecture, plans)
    keep = int(raw.get("search", {}).get("static_finalists", 32))
    executable_rows = [item for item in static_rows if item["plan"]["realization_class"] != "adapter_required"]
    hypothesis_rows = [item for item in static_rows if item["plan"]["realization_class"] == "adapter_required"]
    finalists = [*executable_rows[:keep], *hypothesis_rows[:max(0, keep - len(executable_rows[:keep]))]]
    binary_report = None
    source = _resolve(str(raw["kernel"]["source"]), manifest_path.parent)
    if capture.dialect == "spirv" and bool(raw.get("search", {}).get("spirv_binary_recipes", True)):
        binary_report = synthesize_shader(source, output_directory / "spirv-binary", target_env=str(raw["kernel"].get("target_env", "vulkan1.2")))
    protocols = _protocols_from_manifest(raw, manifest_path, output_directory / "protocols")
    protocol_ok = all(item.status == "PASS" for item in protocols)
    candidate_summary = []
    plan_by_id = {item.id: item for item in plans}
    for ordinal, row in enumerate(finalists):
        plan = row["plan"]
        launch_proof = None
        materialization = None
        if logical_extent is not None and plan["realization_class"] == "launch_plan":
            launch_proof = prove_gpu_execution_plan(
                capture,
                architecture,
                plan_by_id[plan["id"]],
                int(logical_extent),
                output_directory / "plan-proofs" / f"{ordinal:03d}-{plan['id']}",
            )
        if logical_extent is not None and plan["realization_class"] in {"launch_plan", "source_rewrite"}:
            materialization = materialize_gpu_plan(
                capture,
                architecture,
                plan_by_id[plan["id"]],
                int(logical_extent),
                output_directory / "materialized" / f"{ordinal:03d}-{plan['id']}",
                target_env=str(raw["kernel"].get("target_env", "vulkan1.2")),
            )
            launch_proof = materialization["proof"]
        candidate_summary.append({
            **row,
            "semantic_verification": launch_proof or "emitter_and_candidate_proof_required",
            "materialization": materialization,
            "physical_status": "unranked",
            "promotable": False,
            "next_action": "provide source/binary adapter" if plan["realization_class"] == "adapter_required" else "bind the launch plan to the exact output/device timestamp runner",
        })
    report = {
        "schema_version": GPU_WORKFLOW_SCHEMA_VERSION,
        "action": "synthesize",
        "status": "pass",
        "manifest": str(manifest_path),
        "manifest_hash": canonical_hash(raw),
        "grammar_version": GPU_GRAMMAR_VERSION,
        "kernel": capture.to_dict(),
        "architecture": architecture.to_dict(),
        "candidate_count": len(plans) + (binary_report.get("candidate_count", 0) if binary_report else 0),
        "static_finalists": candidate_summary,
        "spirv_binary_candidates": binary_report,
        "protocols": [item.to_dict() for item in protocols],
        "protocol_verification": "PASS" if protocol_ok else "FAIL",
        "promotion": {"promotable": False, "reason": "static search never promotes; exact output proof and clean physical ranking are required"},
        "next_action": "fix protocol counterexamples before physical ranking" if not protocol_ok else "materialize executable finalists and run gpu rank",
    }
    (output_directory / "gpu-candidates.json").write_text(json.dumps(candidate_summary, indent=2, sort_keys=True) + "\n")
    _write_report(output_directory, report)
    return report


def verify_gpu_workflow(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path, output_directory, raw = _load_manifest(manifest_path, output_directory)
    capture, architecture = _capture_from_manifest(raw, manifest_path, output_directory / "kernel")
    protocols = _protocols_from_manifest(raw, manifest_path, output_directory / "protocols")
    kernel_complete = not capture.unsupported_operations
    protocols_pass = all(item.status == "PASS" for item in protocols)
    contract = raw.get("contract", {})
    exact_contract = bool(contract.get("exact_observables", False))
    semantic_obligations = list(
        capture.graph.contracts.get("dialect_facts", {}).get("semantic_obligations", ())
    )
    bindings = {
        "validity-domain": bool(contract.get("preserve_spirv_validity_domain", False)),
        "numeric-policy": bool(contract.get("numeric_policy")),
        "external-descriptor-contract": bool(contract.get("image_descriptor_contract", False)),
        "capability": bool(contract.get("cooperative_matrix_contract", False)),
    }
    unresolved_semantics = [
        item for item in semantic_obligations
        if item.get("status") == "FAIL"
        or (item.get("status") == "CONTRACT_REQUIRED" and not bindings.get(str(item.get("kind")), False))
    ]
    semantic_contract_complete = not unresolved_semantics
    report = {
        "schema_version": GPU_WORKFLOW_SCHEMA_VERSION,
        "action": "verify",
        "status": "PASS" if kernel_complete and protocols_pass and exact_contract and semantic_contract_complete else "INCOMPLETE",
        "kernel_capture_complete": kernel_complete,
        "unsupported_operations": list(capture.unsupported_operations),
        "protocols": [item.to_dict() for item in protocols],
        "architecture_hash": architecture.manifest_hash,
        "exact_observable_contract": exact_contract,
        "semantic_contract_complete": semantic_contract_complete,
        "semantic_contract_bindings": bindings,
        "unresolved_semantic_obligations": unresolved_semantics,
        "proof_classification": "bounded_kernel_capture_and_device_protocol_proof" if kernel_complete and protocols_pass and semantic_contract_complete else "partial_heterogeneous_evidence",
        "excluded_claims": ["final machine scheduling", "driver correctness", "physical performance", "undeclared device loss and external actors"],
        "next_action": "run exact output differential and clean physical ranking" if kernel_complete and protocols_pass and exact_contract and semantic_contract_complete else "resolve incomplete capture, protocol, numeric/validity, descriptor, or observable contract",
    }
    _write_report(output_directory, report)
    return report


def rank_gpu_workflow(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path, output_directory, raw = _load_manifest(manifest_path, output_directory)
    capture, architecture = _capture_from_manifest(raw, manifest_path, output_directory / "kernel")
    ranking = raw.get("physical_ranking")
    if isinstance(ranking, str):
        ranking_path = _resolve(ranking, manifest_path.parent)
    elif isinstance(ranking, dict):
        ranking_path = output_directory / "physical-ranking-manifest.yaml"
        ranking_path.write_text(yaml.safe_dump(ranking, sort_keys=False))
    else:
        raise ValueError("gpu workflow requires physical_ranking as a path or mapping")
    ranking_raw = yaml.safe_load(ranking_path.read_text())
    ranking_identity = str(ranking_raw.get("hardware_identity", "")) if isinstance(ranking_raw, dict) else ""
    if ranking_identity != architecture.device_uuid:
        report = {
            "schema_version": GPU_WORKFLOW_SCHEMA_VERSION,
            "action": "rank",
            "status": "rejected_hardware_identity",
            "architecture_device_uuid": architecture.device_uuid,
            "ranking_device_identity": ranking_identity,
            "promotion": {"promotable": False, "reason": "architecture and physical-ranking device identities differ"},
        }
        _write_report(output_directory, report)
        return report
    if capture.unsupported_operations:
        report = {
            "schema_version": GPU_WORKFLOW_SCHEMA_VERSION,
            "action": "rank",
            "status": "rejected_incomplete_kernel_capture",
            "unsupported_operations": list(capture.unsupported_operations),
            "promotion": {"promotable": False, "reason": "kernel semantic capture is incomplete"},
        }
        _write_report(output_directory, report)
        return report
    protocols = _protocols_from_manifest(raw, manifest_path, output_directory / "protocols")
    if any(item.status != "PASS" for item in protocols):
        report = {
            "schema_version": GPU_WORKFLOW_SCHEMA_VERSION,
            "action": "rank",
            "status": "rejected_protocol",
            "protocols": [item.to_dict() for item in protocols],
            "promotion": {"promotable": False, "reason": "device protocol proof failed"},
        }
        _write_report(output_directory, report)
        return report
    physical = rank_gpu_candidates(ranking_path, output_directory / "physical")
    report = {
        "schema_version": GPU_WORKFLOW_SCHEMA_VERSION,
        "action": "rank",
        "status": "pass",
        "protocols": [item.to_dict() for item in protocols],
        "physical": physical,
        "promotion": physical["promotion"],
        "bounded_classification": "best_verified_found" if physical["winner"] else "no_verified_physical_win",
    }
    _write_report(output_directory, report)
    return report


def _capture_from_manifest(raw: dict[str, Any], manifest_path: Path, output_directory: Path) -> tuple[GPUKernelCapture, GPUArchitecture]:
    kernel = raw.get("kernel")
    if not isinstance(kernel, dict) or "source" not in kernel:
        raise ValueError("GPU workflow manifest requires kernel.source")
    source = _resolve(str(kernel["source"]), manifest_path.parent)
    architecture_raw = raw.get("architecture")
    if isinstance(architecture_raw, str):
        architecture = load_gpu_architecture(_resolve(architecture_raw, manifest_path.parent))
    elif isinstance(architecture_raw, dict):
        architecture = load_gpu_architecture(architecture_raw)
    else:
        raise ValueError("GPU workflow manifest requires an architecture path or mapping")
    capture = capture_gpu_kernel(
        source,
        output_directory,
        dialect=str(kernel.get("dialect", "auto")),
        entry_point=kernel.get("entry_point"),
        target_env=str(kernel.get("target_env", "vulkan1.2")),
    )
    return capture, architecture


def _protocols_from_manifest(raw: dict[str, Any], manifest_path: Path, output_directory: Path) -> list[DeviceProtocolEvidence]:
    evidence: list[DeviceProtocolEvidence] = []
    for ordinal, item in enumerate(raw.get("protocols", [])):
        if isinstance(item, str):
            path = _resolve(item, manifest_path.parent)
        elif isinstance(item, dict):
            path = output_directory / f"inline-{ordinal}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(item, sort_keys=False))
        else:
            raise ValueError("protocol entries must be paths or mappings")
        result = verify_device_protocol(path, output_directory / f"protocol-{ordinal}")
        evidence.append(result)
        if result.kind == "dma":
            raw_protocol = yaml.safe_load(path.read_text())
            routes = enumerate_dma_routes(raw_protocol)
            (output_directory / f"protocol-{ordinal}" / "dma-route-candidates.json").write_text(json.dumps(routes, indent=2, sort_keys=True) + "\n")
    return evidence


def _compose_execution_graph(
    capture: GPUKernelCapture,
    architecture: GPUArchitecture,
    protocols: list[DeviceProtocolEvidence],
    raw: dict[str, Any],
) -> SemanticFlowGraph:
    provenance = {"adapter": GPU_WORKFLOW_SCHEMA_VERSION, "grammar": GPU_GRAMMAR_VERSION}
    child_obligation = obligation("heterogeneous.children.verified", "validation", "every selected child graph has its required proof before promotion", scope="heterogeneous-execution", proof_method="artifact hash and status binding", native_construct="kernel/protocol graph composition")
    identity_obligation = obligation("heterogeneous.hardware.identity", "target", "kernel, protocol, and physical measurements use the same declared device/topology identity", scope="workflow", proof_method="manifest hash and runner identity equality", native_construct="device UUID/topology manifest")
    nodes = [
        SemanticFlowNode("input", "Input", "host-and-device-inputs", (), "heterogeneous-state", {}, provenance, ()),
        SemanticFlowNode("placement", "ResourceUse", "physical-placement", ("input",), "placed-state", {"architecture_hash": architecture.manifest_hash, "device_uuid": architecture.device_uuid}, provenance, (identity_obligation,)),
        SemanticFlowNode("kernel", "Call", "device-kernel-graph", ("placement",), "device-results", {"graph_hash": capture.graph.graph_hash, "dialect": capture.dialect}, provenance, (child_obligation,)),
    ]
    previous = "kernel"
    for ordinal, protocol in enumerate(protocols):
        kind = {"queue": "QueueSubmit", "dma": "DMATransfer", "presentation": "Present"}[protocol.kind]
        node_id = f"protocol.{ordinal}"
        nodes.append(SemanticFlowNode(node_id, kind, f"{protocol.kind}-protocol-graph", (previous,), "heterogeneous-state", {"graph_hash": protocol.graph.graph_hash, "status": protocol.status}, provenance, (child_obligation,)))
        previous = node_id
    nodes.append(SemanticFlowNode("output", "Output", "declared-heterogeneous-observables", (previous,), "observable-state", raw.get("contract", {}), provenance, (child_obligation, identity_obligation)))
    edges = []
    for node in nodes:
        for ordinal, source in enumerate(node.inputs):
            edges.append(SemanticFlowEdge(f"{source}->{node.id}:{ordinal}", source, node.id, node.output_type or "state", "workflow", "declared-resource", "workflow-run", "declared-order", realization="heterogeneous", memory_region="multi-device", validity_scope="workflow-run"))
    effects = (
        SemanticEffect("heterogeneous.dispatch", "Dispatch", "execute", architecture.device_uuid, "device-results", "queue/protocol-order", ("kernel",), ("heterogeneous.hardware.identity",)),
        SemanticEffect("heterogeneous.observe", "Publish", "complete", "workflow-output", "declared-observables", "after-all-selected-protocols", ("output",), ("heterogeneous.children.verified",)),
    )
    transitions = tuple(
        ProtocolTransition(f"heterogeneous.protocol.{ordinal}", {"queue": "Queue", "dma": "DMA", "presentation": "Presentation"}[item.kind], "input-state", item.kind, "output-state", "child graph proof passes", ("heterogeneous.children.verified",), {"child_graph_hash": item.graph.graph_hash})
        for ordinal, item in enumerate(protocols)
    )
    return SemanticFlowGraph(
        str(raw.get("name", "heterogeneous-execution")), "heterogeneous", capture.compiler_identity,
        GPU_WORKFLOW_SCHEMA_VERSION, canonical_hash({"kernel": capture.graph.graph_hash, "protocols": [item.graph.graph_hash for item in protocols], "architecture": architecture.manifest_hash}),
        tuple(nodes), tuple(edges),
        {"architecture": architecture.to_dict(), "contract": raw.get("contract", {}), "child_graphs": [capture.graph.graph_hash, *[item.graph.graph_hash for item in protocols]]},
        ("whole-driver equivalence", "firmware scheduling", "undeclared external actors"),
        (child_obligation, identity_obligation), effects, transitions,
    )


def _load_manifest(manifest_path: Path, output_directory: Path) -> tuple[Path, Path, dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("GPU workflow manifest must be a mapping")
    return manifest_path, output_directory, raw


def _resolve(value: str, root: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _write_report(output_directory: Path, report: dict[str, Any]) -> None:
    (output_directory / "gpu-workflow.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _product(values: Any) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def _local_nvidia_identity() -> dict[str, Any] | None:
    tool = shutil.which("nvidia-smi")
    if not tool:
        return None
    result = subprocess.run(
        [tool, "--query-gpu=name,uuid,compute_cap,memory.total,driver_version,pci.bus_id", "--format=csv,noheader"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode or not result.stdout.strip():
        return None
    fields = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
    keys = ("name", "uuid", "compute_capability", "memory_total", "driver_version", "pci_bus_id")
    return dict(zip(keys, fields))
