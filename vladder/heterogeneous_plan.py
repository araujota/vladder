from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
import hashlib
import json
import math
import os
import random
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

import yaml
from z3 import And, Bool, BoolVal, If, Implies, Int, Not, Or, Solver, sat

from .device_protocol import verify_device_protocol
from .language_adapter import (
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    obligation,
)
from .statistics_v3 import empirical_quantile


HETEROGENEOUS_PLAN_SCHEMA = "vladder-heterogeneous-plan-v2"
HETEROGENEOUS_SEARCH_SCHEMA = "vladder-heterogeneous-search-v2"
HETEROGENEOUS_RANK_SCHEMA = "vladder-heterogeneous-rank-v2"
HETEROGENEOUS_AUDIT_SCHEMA = "vladder-heterogeneous-project-audit-v2"
PLAN_KINDS = frozenset({
    "gpu-stable-compaction",
    "queue-overlap",
    "sparse-update-policy",
    "presentation-policy",
})


def audit_heterogeneous_project(project_root: Path, output_directory: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    output_directory = output_directory.resolve()
    if output_directory == project_root or project_root in output_directory.parents:
        raise ValueError("read-only project audit output must be outside the target project")
    output_directory.mkdir(parents=True, exist_ok=True)
    before = _git_status(project_root)
    surfaces: list[dict[str, Any]] = []
    shader_files = sorted({*project_root.rglob("*.comp"), *project_root.rglob("*.comp.glsl"), *project_root.rglob("*.glsl")})
    for path in shader_files:
        if not path.is_file() or any(part in {".git", "third_party"} for part in path.parts):
            continue
        text = path.read_text(errors="replace")
        features = []
        if ("changed" in text or "mask" in text) and ("!=" in text or "^" in text):
            features.append("predicate-mask")
        if "shared" in text and "barrier" in text and ("offset" in text or "scan" in text):
            features.append("workgroup-prefix-scan")
        if ("scatter" in path.name or "destination" in text) and ("offset" in text or "atomic" in text):
            features.append("stable-or-indexed-scatter")
        if features:
            surfaces.append({
                "path": str(path.relative_to(project_root)),
                "source_hash": _file_hash(path),
                "domain": "gpu-algorithm",
                "features": features,
                "candidate_family": "gpu-stable-compaction" if any("scan" in item or "scatter" in item for item in features) else "typed-spirv-core",
                "closure": "local_shader_stage" if len(features) == 1 else "bounded_algorithm_stage",
                "adapter_requirements": ["descriptor/output contract", "multi-dispatch resource binding", "application device-timestamp runner"],
            })
    source_files = sorted({*project_root.rglob("*.cpp"), *project_root.rglob("*.cc"), *project_root.rglob("*.cxx"), *project_root.rglob("*.hpp")})
    for path in source_files:
        if not path.is_file() or any(part in {".git", "third_party", "build"} for part in path.parts):
            continue
        text = path.read_text(errors="replace")
        findings: list[tuple[str, str, list[str], str]] = []
        if all(token in text for token in ("dense_size", "sparse_size", "full_size")):
            findings.append(("sparse-update-policy", "exact-size-policy", ["statistics-to-encoding adapter", "payload encoder/decoder differential oracle"], "generated_cpp_policy_source"))
        if "vkQueueSubmit" in text or "vkQueueSubmit2" in text:
            findings.append(("queue-overlap", "queue-submission-owner", ["operation/resource extraction", "command-buffer binding", "device timestamp runner"], "executable_runtime_plan"))
        if "vkQueuePresentKHR" in text or "vkAcquireNextImageKHR" in text:
            findings.append(("presentation-policy", "presentation-owner", ["swapchain capability binding", "present-stage timestamp runner", "active display for visible claims"], "executable_runtime_plan"))
        for family, feature, adapters, realization in findings:
            surfaces.append({
                "path": str(path.relative_to(project_root)),
                "source_hash": _file_hash(path),
                "domain": "host-orchestration",
                "features": [feature],
                "candidate_family": family,
                "closure": "binding_target",
                "realization_class": realization,
                "adapter_requirements": adapters,
            })
    after = _git_status(project_root)
    family_counts: dict[str, int] = {}
    for surface in surfaces:
        family = str(surface["candidate_family"])
        family_counts[family] = family_counts.get(family, 0) + 1
    report = {
        "schema_version": HETEROGENEOUS_AUDIT_SCHEMA,
        "status": "pass" if before == after else "target_modified",
        "project": str(project_root),
        "project_git_status_before": before,
        "project_git_status_after": after,
        "no_write_validation": before == after,
        "surface_count": len(surfaces),
        "family_counts": family_counts,
        "surfaces": sorted(surfaces, key=lambda item: (item["candidate_family"], item["path"])),
        "claim_boundary": "recognition and binding analysis only; candidate proof and physical promotion require family workflows and representative runners",
    }
    (output_directory / "heterogeneous-project-audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


@dataclass(frozen=True)
class PlanNode:
    id: str
    kind: str
    operation: str
    inputs: tuple[str, ...]
    placement: str
    attributes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "inputs": list(self.inputs)}


@dataclass(frozen=True)
class PlanEdge:
    id: str
    source: str
    destination: str
    dependency: str
    information: str
    bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HeterogeneousPlanGraph:
    name: str
    kind: str
    nodes: tuple[PlanNode, ...]
    edges: tuple[PlanEdge, ...]
    bounds: dict[str, int]
    observables: tuple[str, ...]
    external_boundaries: tuple[str, ...]
    provenance: dict[str, Any]
    graph_hash: str = ""

    def __post_init__(self) -> None:
        if self.kind not in PLAN_KINDS:
            raise ValueError(f"unsupported heterogeneous plan kind: {self.kind}")
        node_ids = [item.id for item in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("plan node identifiers must be unique")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.destination not in known:
                raise ValueError(f"plan edge {edge.id} references an unknown node")
        if any(value <= 0 for value in self.bounds.values()):
            raise ValueError("all declared plan bounds must be positive")
        expected = canonical_hash(self._hash_payload())
        if self.graph_hash and self.graph_hash != expected:
            raise ValueError("heterogeneous plan graph hash does not match payload")
        if not self.graph_hash:
            object.__setattr__(self, "graph_hash", expected)

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "bounds": self.bounds,
            "observables": list(self.observables),
            "external_boundaries": list(self.external_boundaries),
            "provenance": self.provenance,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": HETEROGENEOUS_PLAN_SCHEMA,
            **self._hash_payload(),
            "graph_hash": self.graph_hash,
        }


@dataclass(frozen=True)
class PlanCandidate:
    id: str
    kind: str
    parameters: dict[str, Any]
    realization_class: str
    graph: HeterogeneousPlanGraph
    static_cost: dict[str, float]
    proof: dict[str, Any]
    artifacts: dict[str, str]
    adapter_requirements: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "parameters": self.parameters,
            "realization_class": self.realization_class,
            "graph": self.graph.to_dict(),
            "static_cost": self.static_cost,
            "proof": self.proof,
            "artifacts": self.artifacts,
            "adapter_requirements": list(self.adapter_requirements),
            "promotable": False,
        }


def synthesize_heterogeneous_plans(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("heterogeneous plan manifest must be a mapping")
    kind = str(raw.get("kind", ""))
    if kind not in PLAN_KINDS:
        raise ValueError(f"unsupported heterogeneous plan kind {kind!r}; expected {sorted(PLAN_KINDS)}")
    _validate_attribution(raw.get("attribution"))
    recursion = raw.get("recursion", {})
    if recursion and not int(recursion.get("maximum_depth", 0)):
        raise ValueError("recursive plan regions require a positive maximum_depth")
    emitters = {
        "gpu-stable-compaction": _synthesize_gpu_compaction,
        "queue-overlap": _synthesize_queue_overlap,
        "sparse-update-policy": _synthesize_sparse_policy,
        "presentation-policy": _synthesize_presentation_policy,
    }
    maximum = int(raw.get("search", {}).get("maximum_candidates", 256))
    if maximum <= 0 or maximum > 5000:
        raise ValueError("maximum_candidates must be in [1, 5000]")
    candidates = emitters[kind](raw, manifest_path, output_directory, maximum)
    candidates = sorted(candidates, key=lambda item: (item.static_cost.get("objective", math.inf), item.id))
    report = {
        "schema_version": HETEROGENEOUS_SEARCH_SCHEMA,
        "status": "pass",
        "kind": kind,
        "manifest": str(manifest_path),
        "manifest_hash": canonical_hash(raw),
        "attribution": raw["attribution"],
        "candidate_count": len(candidates),
        "candidates": [item.to_dict() for item in candidates],
        "best_static_candidate": candidates[0].to_dict() if candidates else None,
        "search_classification": "bounded_exhaustive" if len(candidates) < maximum else "bounded_truncated",
        "promotion": {
            "promotable": False,
            "reason": "synthesis and proof do not replace exact differential output and representative physical ranking",
        },
        "graphml_authority": "ranking features only; never legality, proof, or promotion",
    }
    (output_directory / "heterogeneous-plans.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def rank_heterogeneous_plans(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("heterogeneous ranking manifest must be a mapping")
    runner = raw.get("runner", {})
    command = runner.get("command")
    if not isinstance(command, list) or not any("{plan}" in str(item) for item in command):
        raise ValueError("runner.command must be a list containing {plan}")
    baseline = raw.get("baseline")
    candidates = raw.get("candidates", [])
    if not isinstance(baseline, dict) or not candidates:
        raise ValueError("ranking requires baseline and candidates")
    evidence_class = str(runner.get("evidence_class", "unspecified"))
    physical_classes = {
        "application-device-timestamp",
        "hardware-device-timestamp",
        "presentation-stage-timestamp",
        "end-to-end-hardware-timestamp",
    }
    processes = int(runner.get("processes", 10))
    rounds = int(runner.get("bootstrap_rounds", 2000))
    minimum = float(runner.get("minimum_effect_percent", 1.0))
    seed = int(runner.get("seed", 0))
    timeout = float(runner.get("timeout_seconds", 120.0))
    expected_hardware = str(raw.get("hardware_identity", ""))
    rng = random.Random(seed)

    def invoke(entry: dict[str, Any]) -> dict[str, Any]:
        plan = _resolve_path(str(entry["plan"]), manifest_path.parent)
        call = [str(item).replace("{plan}", str(plan)).replace("{candidate_id}", str(entry.get("id", "candidate"))) for item in command]
        completed = subprocess.run(call, cwd=manifest_path.parent, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if completed.returncode:
            raise RuntimeError(f"heterogeneous runner failed: {' '.join(call)}\n{completed.stderr[-3000:]}")
        for line in reversed(completed.stdout.splitlines()):
            if line.strip().startswith("{"):
                result = json.loads(line)
                required = {"total_time_ns", "output_hash", "state_hash", "device_identity", "evidence_class"}
                if required - set(result):
                    raise ValueError(f"runner result missing {sorted(required - set(result))}")
                return result
        raise ValueError("heterogeneous runner emitted no JSON result")

    rows: list[dict[str, Any]] = []
    for candidate_index, candidate in enumerate(candidates):
        effects: list[float] = []
        mismatches: list[dict[str, Any]] = []
        identity_failures: list[dict[str, Any]] = []
        class_failures: list[dict[str, Any]] = []
        pairs: list[dict[str, Any]] = []
        for process_index in range(processes):
            order = ["baseline", "candidate"]
            rng.shuffle(order)
            observed = {name: invoke(baseline if name == "baseline" else candidate) for name in order}
            left, right = observed["baseline"], observed["candidate"]
            effects.append((float(left["total_time_ns"]) / float(right["total_time_ns"]) - 1.0) * 100.0)
            if (left["output_hash"], left["state_hash"]) != (right["output_hash"], right["state_hash"]):
                mismatches.append({"process": process_index, "baseline": [left["output_hash"], left["state_hash"]], "candidate": [right["output_hash"], right["state_hash"]]})
            if left["device_identity"] != right["device_identity"] or (expected_hardware and left["device_identity"] != expected_hardware):
                identity_failures.append({"process": process_index, "baseline": left["device_identity"], "candidate": right["device_identity"]})
            if left["evidence_class"] != evidence_class or right["evidence_class"] != evidence_class:
                class_failures.append({"process": process_index, "baseline": left["evidence_class"], "candidate": right["evidence_class"]})
            pairs.append({"process": process_index, "order": order, "baseline": left, "candidate": right})
        interval = _bootstrap(effects, seed + candidate_index, rounds)
        effect = statistics.median(effects)
        physical = evidence_class in physical_classes and not class_failures
        promoted = not mismatches and not identity_failures and physical and interval[0] >= minimum
        classification = (
            "verification_failed" if mismatches else
            "hardware_identity_mismatch" if identity_failures else
            "simulated_or_unclassified_evidence" if not physical else
            "plan_win" if promoted else
            "measured_regression" if interval[1] < 0 else
            "statistical_tie"
        )
        rows.append({
            "candidate_id": str(candidate.get("id", candidate_index)),
            "classification": classification,
            "effect_percent": effect,
            "effect_95_percent": interval,
            "minimum_effect_percent": minimum,
            "semantic_parity": "PASS" if not mismatches else "FAIL",
            "hardware_identity": "PASS" if not identity_failures else "FAIL",
            "physical_evidence": "PASS" if physical else "FAIL",
            "promotable": promoted,
            "pairs": pairs,
            "mismatches": mismatches,
        })
    winners = sorted((item for item in rows if item["promotable"]), key=lambda item: item["effect_percent"], reverse=True)
    report = {
        "schema_version": HETEROGENEOUS_RANK_SCHEMA,
        "status": "pass",
        "manifest_hash": canonical_hash(raw),
        "evidence_class": evidence_class,
        "candidates": rows,
        "winner": winners[0] if winners else None,
        "promotion": {"promotable": bool(winners), "reason": "exact output/state parity and clean physical interval" if winners else "no candidate passed all gates"},
    }
    (output_directory / "heterogeneous-ranking.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _validate_attribution(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise ValueError("an attribution mapping is required before grammar expansion")
    if not str(raw.get("metric", "")) or float(raw.get("value", 0.0)) <= 0 or not str(raw.get("evidence", "")):
        raise ValueError("attribution requires metric, positive value, and evidence provenance")


def _synthesize_gpu_compaction(raw: dict[str, Any], manifest: Path, output: Path, maximum: int) -> list[PlanCandidate]:
    contract = raw.get("contract", {})
    max_elements = int(contract.get("max_elements", 256))
    if max_elements <= 0 or max_elements > 1024:
        raise ValueError("GPU compaction max_elements must be in [1, 1024]")
    architecture = raw.get("architecture", {})
    max_threads = int(architecture.get("max_threads_per_block", 1024))
    max_shared = int(architecture.get("shared_memory_per_block", 49152))
    workgroups = sorted({int(item) for item in raw.get("search", {}).get("workgroup_sizes", [32, 64, 128, 256])})
    element_bits = int(contract.get("element_bits", 32))
    candidates: list[PlanCandidate] = []
    for workgroup in workgroups:
        if workgroup > max_threads or workgroup & (workgroup - 1):
            continue
        for topology in ("one-workgroup", "hierarchical-three-pass"):
            legal = max_elements <= workgroup if topology == "one-workgroup" else math.ceil(max_elements / workgroup) <= workgroup
            if not legal:
                continue
            shared_bytes = workgroup * 4
            if shared_bytes > max_shared:
                continue
            parameters = {"workgroup_size": workgroup, "scan": "hillis-steele", "topology": topology, "max_elements": max_elements, "element_bits": element_bits}
            candidate_id = "gpu-compact-" + canonical_hash(parameters)[:12]
            candidate_dir = output / "candidates" / candidate_id
            candidate_dir.mkdir(parents=True, exist_ok=True)
            source = candidate_dir / "stable_compaction.cu"
            function = candidate_id.replace("-", "_")
            source.write_text(_cuda_compaction_source(function, element_bits) if topology == "one-workgroup" else _cuda_hierarchical_compaction_source(function, element_bits))
            launch_plan = candidate_dir / "launch-plan.json"
            launch_plan.write_text(json.dumps({
                "topology": topology,
                "workgroup_size": workgroup,
                "maximum_elements": max_elements,
                "maximum_groups": math.ceil(max_elements / workgroup),
                "kernels": [function] if topology == "one-workgroup" else [f"{function}_local_scan", f"{function}_group_scan", f"{function}_scatter"],
            }, indent=2, sort_keys=True) + "\n")
            compile_report = _compile_cuda_source(source, candidate_dir / "stable_compaction.ptx")
            proof = _prove_compaction(max_elements, workgroup, topology, candidate_dir / "proof")
            graph = _compaction_graph(raw, manifest, parameters)
            graph_json, graphml = _write_graph(graph, candidate_dir)
            artifacts = {"source": str(source), "launch_plan": str(launch_plan), "graph": str(graph_json), "graphml": str(graphml), **compile_report}
            passes = 1 if topology == "one-workgroup" else 3
            objective = passes * float(workgroup * math.log2(workgroup) + workgroup) / max_elements
            candidates.append(PlanCandidate(candidate_id, raw["kind"], parameters, "generated_cuda_source_and_launch_plan", graph, {"objective": objective, "shared_bytes": float(shared_bytes), "barriers": float(passes * (2 * math.log2(workgroup) + 2)), "kernel_passes": float(passes)}, proof, artifacts))
            if len(candidates) >= maximum:
                break
        if len(candidates) >= maximum:
            break
    if not candidates:
        raise ValueError("no legal GPU compaction plan fits the declared extent and architecture")
    return candidates


def _synthesize_sparse_policy(raw: dict[str, Any], manifest: Path, output: Path, maximum: int) -> list[PlanCandidate]:
    contract = raw.get("contract", {})
    max_elements = int(contract.get("max_elements", 4096))
    if max_elements <= 0 or max_elements > 1_000_000:
        raise ValueError("sparse policy max_elements must be in [1, 1000000]")
    policy_model = str(contract.get("policy_model", "density-threshold"))
    if policy_model == "minimum-exact-bytes":
        return _synthesize_exact_size_policy(raw, manifest, output, maximum)
    if policy_model != "density-threshold":
        raise ValueError("sparse policy_model must be density-threshold or minimum-exact-bytes")
    thresholds = sorted({float(item) for item in raw.get("search", {}).get("density_thresholds", [0.125, 0.25, 0.5, 0.75])})
    if any(item < 0 or item > 1 for item in thresholds):
        raise ValueError("density thresholds must be in [0, 1]")
    samples = [float(item) for item in raw.get("workload", {}).get("density_samples", [0.01, 0.1, 0.5, 1.0])]
    candidates: list[PlanCandidate] = []
    for threshold, representation in product(thresholds, ("index-value", "bitmap-value")):
        parameters = {"density_threshold": threshold, "sparse_representation": representation, "dense_representation": "index-value", "commit": "atomic-extent-last"}
        candidate_id = "sparse-policy-" + canonical_hash(parameters)[:12]
        candidate_dir = output / "candidates" / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        source = candidate_dir / "sparse_policy.cpp"
        source.write_text(_sparse_policy_source(candidate_id.replace("-", "_"), threshold, representation))
        compile_report = _compile_cpp_source(source, candidate_dir / "sparse_policy.o")
        proof = _prove_sparse_policy(threshold, candidate_dir / "proof")
        graph = _sparse_policy_graph(raw, manifest, parameters)
        graph_json, graphml = _write_graph(graph, candidate_dir)
        expected_bytes = sum(_sparse_policy_bytes(density, max_elements, threshold, representation) for density in samples) / max(1, len(samples))
        candidates.append(PlanCandidate(candidate_id, raw["kind"], parameters, "generated_cpp_policy_source", graph, {"objective": expected_bytes, "expected_bytes": expected_bytes}, proof, {"source": str(source), "graph": str(graph_json), "graphml": str(graphml), **compile_report}))
        if len(candidates) >= maximum:
            break
    return candidates


def _synthesize_queue_overlap(raw: dict[str, Any], manifest: Path, output: Path, maximum: int) -> list[PlanCandidate]:
    operations = raw.get("operations", [])
    queues = raw.get("queues", [])
    if not isinstance(operations, list) or not operations or not isinstance(queues, list) or not queues:
        raise ValueError("queue-overlap requires non-empty operations and queues")
    if len(operations) > 16:
        raise ValueError("queue-overlap v2 requires at most 16 operations")
    queue_ids = {str(item["id"]) for item in queues}
    operation_ids = [str(item["id"]) for item in operations]
    dependencies = {(str(left), str(right)) for left, right in raw.get("dependencies", [])}
    dependencies |= _hazard_dependencies(operations)
    if not _is_topological(operation_ids, dependencies):
        raise ValueError("operations must be listed in topological order and dependencies must be acyclic")
    choices: list[list[str]] = []
    for operation in operations:
        eligible = [str(item) for item in operation.get("eligible_queues", queue_ids) if str(item) in queue_ids]
        if not eligible:
            raise ValueError(f"operation {operation['id']} has no eligible queue")
        choices.append(sorted(set(eligible)))
    candidates: list[PlanCandidate] = []
    for assignment_tuple in product(*choices):
        assignment = dict(zip(operation_ids, assignment_tuple))
        parameters = {"queue_assignment": assignment, "dependency_count": len(dependencies)}
        candidate_id = "queue-plan-" + canonical_hash(parameters)[:12]
        candidate_dir = output / "candidates" / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        plan_manifest = _queue_protocol_manifest(raw, operations, dependencies, assignment)
        plan_path = candidate_dir / "queue-plan.yaml"
        plan_path.write_text(yaml.safe_dump(plan_manifest, sort_keys=False))
        protocol = verify_device_protocol(plan_path, candidate_dir / "protocol-proof")
        schedule = _queue_schedule(operations, dependencies, assignment)
        proof = _prove_queue_dependencies(operation_ids, dependencies, assignment, protocol.status, candidate_dir / "proof")
        graph = _queue_graph(raw, manifest, operations, dependencies, assignment)
        graph_json, graphml = _write_graph(graph, candidate_dir)
        candidates.append(PlanCandidate(candidate_id, raw["kind"], parameters, "executable_runtime_plan", graph, {"objective": schedule["makespan_ns"], **schedule}, proof, {"plan": str(plan_path), "protocol_proof": protocol.artifacts["graph"], "graph": str(graph_json), "graphml": str(graphml)}, ("application queue/command-buffer binding", "representative device timestamp runner")))
        if len(candidates) >= maximum:
            break
    return candidates


def _synthesize_presentation_policy(raw: dict[str, Any], manifest: Path, output: Path, maximum: int) -> list[PlanCandidate]:
    capabilities = raw.get("capabilities", {})
    supported_modes = {str(item).lower() for item in capabilities.get("present_modes", ["fifo"])}
    requested_modes = [str(item).lower() for item in raw.get("search", {}).get("present_modes", sorted(supported_modes))]
    image_counts = sorted({int(item) for item in raw.get("search", {}).get("image_counts", [2, 3])})
    flight_counts = sorted({int(item) for item in raw.get("search", {}).get("frames_in_flight", [1, 2])})
    refresh_ns = float(raw.get("workload", {}).get("refresh_period_ns", 16_666_667.0))
    render_ns = float(raw.get("workload", {}).get("render_time_ns", refresh_ns * 0.5))
    candidates: list[PlanCandidate] = []
    for mode, image_count, flight_count in product(requested_modes, image_counts, flight_counts):
        if mode not in supported_modes or image_count < 2 or flight_count <= 0 or flight_count >= image_count:
            continue
        parameters = {"present_mode": mode, "image_count": image_count, "frames_in_flight": flight_count, "deadline_policy": "next-vblank" if mode != "immediate" else "as-ready"}
        candidate_id = "present-plan-" + canonical_hash(parameters)[:12]
        candidate_dir = output / "candidates" / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        protocol_manifest = _presentation_protocol_manifest(raw, parameters)
        plan_path = candidate_dir / "presentation-plan.yaml"
        plan_path.write_text(yaml.safe_dump(protocol_manifest, sort_keys=False))
        protocol = verify_device_protocol(plan_path, candidate_dir / "protocol-proof")
        proof = _prove_presentation(parameters, supported_modes, protocol.status, candidate_dir / "proof")
        graph = _presentation_graph(raw, manifest, parameters)
        graph_json, graphml = _write_graph(graph, candidate_dir)
        modeled = _presentation_cost(mode, flight_count, refresh_ns, render_ns)
        candidates.append(PlanCandidate(candidate_id, raw["kind"], parameters, "executable_runtime_plan", graph, {"objective": modeled, "modeled_frame_latency_ns": modeled}, proof, {"plan": str(plan_path), "protocol_proof": protocol.artifacts["graph"], "graph": str(graph_json), "graphml": str(graphml)}, ("swapchain/runtime binding", "physical presentation-stage timestamp runner", "visible scanout evidence when claimed")))
        if len(candidates) >= maximum:
            break
    if not candidates:
        raise ValueError("no presentation candidate is supported by the declared capability set")
    return candidates


def _compaction_graph(raw: dict[str, Any], manifest: Path, parameters: dict[str, Any]) -> HeterogeneousPlanGraph:
    if parameters["topology"] == "one-workgroup":
        nodes = (
            PlanNode("input", "Input", "current-and-baseline", (), "device-global", {}),
            PlanNode("predicate", "Compare", "changed-predicate", ("input",), "lane-register", {}),
            PlanNode("scan", "PrefixScan", "exclusive-stable-prefix", ("predicate",), "workgroup-shared", {"topology": parameters["scan"]}),
            PlanNode("capacity", "CapacityGuard", "fail-unchanged", ("scan",), "workgroup", {}),
            PlanNode("scatter", "Scatter", "stable-index-value-output", ("predicate", "scan", "capacity"), "device-global", {}),
            PlanNode("extent", "Commit", "publish-extent-last", ("scatter", "capacity"), "device-global", {}),
        )
    else:
        nodes = (
            PlanNode("input", "Input", "current-and-baseline", (), "device-global", {}),
            PlanNode("predicate", "Compare", "changed-predicate", ("input",), "lane-register", {}),
            PlanNode("local_scan", "PrefixScan", "per-workgroup-exclusive-prefix", ("predicate",), "workgroup-shared", {}),
            PlanNode("group_counts", "Materialize", "group-counts", ("local_scan",), "device-global", {}),
            PlanNode("group_scan", "PrefixScan", "exclusive-group-prefix", ("group_counts",), "workgroup-shared", {}),
            PlanNode("capacity", "CapacityGuard", "fail-unchanged", ("group_scan",), "device-global", {}),
            PlanNode("scatter", "Scatter", "group-plus-local-stable-output", ("predicate", "local_scan", "group_scan", "capacity"), "device-global", {}),
            PlanNode("extent", "Commit", "publish-extent-before-scatter-guard", ("group_scan", "capacity"), "device-global", {}),
        )
    return _plan_graph(raw, manifest, nodes, {"max_elements": parameters["max_elements"], "workgroup_size": parameters["workgroup_size"]}, ("output extent", "stable indices", "stable values", "capacity status"), ("CUDA scheduler", "device memory system"))


def _sparse_policy_graph(raw: dict[str, Any], manifest: Path, parameters: dict[str, Any]) -> HeterogeneousPlanGraph:
    nodes = (
        PlanNode("current", "Input", "current-state", (), "caller-memory", {}),
        PlanNode("baseline", "StateRead", "acknowledged-baseline", (), "caller-memory", {}),
        PlanNode("compare", "Compare", "changed-predicate", ("current", "baseline"), "register", {}),
        PlanNode("extent", "PopulationCount", "changed-count", ("compare",), "register", {}),
        PlanNode("dispatch", "Dispatch", "density-guard", ("extent",), "control", {"threshold": parameters["density_threshold"]}),
        PlanNode("compact", "Compact", parameters["sparse_representation"], ("current", "compare", "dispatch"), "caller-output", {}),
        PlanNode("dense", "Materialize", "dense-index-value", ("current", "dispatch"), "caller-output", {}),
        PlanNode("commit", "Commit", "publish-output-extent-last", ("compact", "dense"), "caller-state", {}),
    )
    return _plan_graph(raw, manifest, nodes, {"max_elements": int(raw.get("contract", {}).get("max_elements", 4096))}, ("output extent", "indices", "values", "generation", "capacity status"), ("allocator outside generated region", "consumer publication protocol"))


def _exact_size_policy_graph(raw: dict[str, Any], manifest: Path, parameters: dict[str, Any]) -> HeterogeneousPlanGraph:
    nodes = (
        PlanNode("statistics", "Input", "exact-representation-statistics", (), "caller-memory", {}),
        PlanNode("dense_size", "Map", "dense-bitmap-byte-count", ("statistics",), "register", {}),
        PlanNode("sparse_size", "Map", "sparse-bitmap-byte-count", ("statistics",), "register", {}),
        PlanNode("run_size", "Map", "run-byte-count", ("statistics",), "register", {}),
        PlanNode("full_size", "Map", "full-byte-count", ("statistics",), "register", {}),
        PlanNode("select", "Select", parameters["selection_realization"], ("dense_size", "sparse_size", "run_size", "full_size"), "register", {"evaluation_order": parameters["evaluation_order"], "tie_order": parameters["tie_order"]}),
        PlanNode("output", "Output", "encoding-and-exact-size", ("select",), "caller-state", {}),
    )
    return _plan_graph(raw, manifest, nodes, {"encoding_count": 4}, ("selected encoding", "selected byte count"), ("statistics derivation", "payload encoder", "consumer decoder"))


def _queue_graph(raw: dict[str, Any], manifest: Path, operations: list[dict[str, Any]], dependencies: set[tuple[str, str]], assignment: dict[str, str]) -> HeterogeneousPlanGraph:
    nodes = tuple(PlanNode(str(item["id"]), "QueueSubmit", str(item.get("operation", item["id"])), tuple(left for left, right in dependencies if right == str(item["id"])), assignment[str(item["id"])], {"duration_ns": float(item.get("duration_ns", 1.0)), "accesses": item.get("accesses", [])}) for item in operations)
    return _plan_graph(raw, manifest, nodes, {"operations": len(operations), "queues": len(set(assignment.values()))}, tuple(str(item) for item in raw.get("observables", ["output hash", "state hash", "total latency"])), ("driver scheduling", "device execution overlap", "undeclared external actors"))


def _presentation_graph(raw: dict[str, Any], manifest: Path, parameters: dict[str, Any]) -> HeterogeneousPlanGraph:
    nodes = (
        PlanNode("acquire", "Acquire", "acquire-image", (), "presentation-engine", {}),
        PlanNode("render", "QueueSubmit", "render-frame", ("acquire",), "gpu-queue", {}),
        PlanNode("present", "Present", parameters["present_mode"], ("render",), "presentation-queue", {}),
        PlanNode("scanout", "Scanout", parameters["deadline_policy"], ("present",), "display-engine", {}),
        PlanNode("release", "Release", "release-image", ("scanout",), "swapchain", {}),
    )
    return _plan_graph(raw, manifest, nodes, {"images": parameters["image_count"], "frames_in_flight": parameters["frames_in_flight"]}, ("frame output hash", "present result", "deadline misses", "visible-stage timestamps"), ("window system", "driver", "display engine", "physical panel"))


def _plan_graph(raw: dict[str, Any], manifest: Path, nodes: tuple[PlanNode, ...], bounds: dict[str, int], observables: tuple[str, ...], external: tuple[str, ...]) -> HeterogeneousPlanGraph:
    edges = []
    for node in nodes:
        for ordinal, source in enumerate(node.inputs):
            edges.append(PlanEdge(f"{source}->{node.id}:{ordinal}", source, node.id, "semantic", "information-flow"))
    recursion = raw.get("recursion", {})
    if recursion:
        bounds = {**bounds, "recursion_depth": int(recursion["maximum_depth"])}
    return HeterogeneousPlanGraph(str(raw.get("name", raw["kind"])), str(raw["kind"]), nodes, tuple(edges), bounds, observables, external, {"manifest": str(manifest), "manifest_hash": canonical_hash(raw), "grammar": "heterogeneous-algorithm-orchestration-v2"})


def _semantic_graph(graph: HeterogeneousPlanGraph) -> SemanticFlowGraph:
    nodes = tuple(SemanticFlowNode(item.id, item.kind, item.operation, item.inputs, "plan-state", {"placement": item.placement, **item.attributes}, {"adapter": HETEROGENEOUS_PLAN_SCHEMA}, ()) for item in graph.nodes)
    edges = tuple(SemanticFlowEdge(item.id, item.source, item.destination, "plan-state", "plan", "heterogeneous-plan", "bounded-run", item.dependency, realization=graph.kind, memory_region="heterogeneous", validity_scope="bounded-plan") for item in graph.edges)
    return SemanticFlowGraph(graph.name, "heterogeneous-plan", "manifest", HETEROGENEOUS_PLAN_SCHEMA, graph.graph_hash, nodes, edges, {"bounds": graph.bounds, "observables": graph.observables}, graph.external_boundaries, (obligation("heterogeneous.bounds", "bounds", "all recursion, resource, and candidate domains are finite", scope="heterogeneous-plan", proof_method="manifest validation and Z3", native_construct="runtime plan"),), (), ())


def _write_graph(graph: HeterogeneousPlanGraph, directory: Path) -> tuple[Path, Path]:
    graph_path = directory / "heterogeneous-plan-graph.json"
    semantic_path = directory / "semantic-flow-graph.json"
    graphml_path = directory / "heterogeneous-plan.graphml"
    graph_path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n")
    semantic_path.write_text(json.dumps(_semantic_graph(graph).to_dict(), indent=2, sort_keys=True) + "\n")
    graphml_path.write_text(_graphml(graph))
    return graph_path, graphml_path


def _graphml(graph: HeterogeneousPlanGraph) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="plan_kind" for="graph" attr.name="plan_kind" attr.type="string"/>',
        '  <key id="bounds" for="graph" attr.name="bounds" attr.type="string"/>',
        '  <key id="external" for="graph" attr.name="external_boundaries" attr.type="string"/>',
        '  <key id="kind" for="node" attr.name="kind" attr.type="string"/>',
        '  <key id="operation" for="node" attr.name="operation" attr.type="string"/>',
        '  <key id="placement" for="node" attr.name="placement" attr.type="string"/>',
        '  <key id="dependency" for="edge" attr.name="dependency" attr.type="string"/>',
        f'  <graph id="{escape(graph.graph_hash)}" edgedefault="directed">',
        f'    <data key="plan_kind">{escape(graph.kind)}</data>',
        f'    <data key="bounds">{escape(json.dumps(graph.bounds, sort_keys=True, separators=(",", ":")))}</data>',
        f'    <data key="external">{escape(json.dumps(graph.external_boundaries))}</data>',
    ]
    for node in sorted(graph.nodes, key=lambda item: item.id):
        lines.extend((
            f'    <node id="{escape(node.id)}">',
            f'      <data key="kind">{escape(node.kind)}</data>',
            f'      <data key="operation">{escape(node.operation)}</data>',
            f'      <data key="placement">{escape(node.placement)}</data>',
            '    </node>',
        ))
    for edge in sorted(graph.edges, key=lambda item: item.id):
        lines.extend((
            f'    <edge id="{escape(edge.id)}" source="{escape(edge.source)}" target="{escape(edge.destination)}">',
            f'      <data key="dependency">{escape(edge.dependency)}</data>',
            '    </edge>',
        ))
    lines.extend(('  </graph>', '</graphml>', ''))
    return "\n".join(lines)


def _prove_compaction(max_elements: int, workgroup: int, topology: str, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    solver = Solver()
    symbolic_lanes = min(max_elements, 64)
    selected = [Bool(f"selected_{index}") for index in range(symbolic_lanes)]
    positions = [Int(f"position_{index}") for index in range(symbolic_lanes)]
    for index in range(symbolic_lanes):
        solver.add(positions[index] == sum(If(selected[prior], 1, 0) for prior in range(index)))
    violation = Or(*[
        And(selected[left], selected[right], positions[left] >= positions[right])
        for left in range(symbolic_lanes) for right in range(left + 1, symbolic_lanes)
    ]) if symbolic_lanes > 1 else BoolVal(False)
    solver.add(violation)
    result = solver.check()
    capacity_solver = Solver()
    total = Int("selected_total")
    capacity = Int("capacity")
    any_write = Bool("any_write")
    capacity_solver.add(total >= 0, capacity >= 0, any_write == And(total > 0, total <= capacity))
    capacity_solver.add(total > capacity, any_write)
    capacity_atomic = capacity_solver.check() != sat
    group_count = math.ceil(max_elements / workgroup)
    coverage = (
        workgroup >= max_elements if topology == "one-workgroup"
        else group_count <= workgroup
    ) and workgroup & (workgroup - 1) == 0
    status = "PROVED" if result != sat and coverage and capacity_atomic else "FAIL"
    (directory / "compaction.smt2").write_text(solver.to_smt2() + "\n; capacity atomicity\n" + capacity_solver.to_smt2())
    report = {"status": status, "obligations": {"stable_order": result != sat, "lane_coverage": coverage, "group_scan_coverage": topology == "one-workgroup" or group_count <= workgroup, "capacity_atomicity": capacity_atomic, "uniform_barriers": True}, "counterexample": {} if result != sat else {str(item): str(solver.model()[item]) for item in solver.model()}, "proof_scope": f"symbolic stable-order proof through {symbolic_lanes} lanes plus structural coverage for {max_elements} elements, topology {topology}, workgroup {workgroup}"}
    (directory / "proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _prove_sparse_policy(threshold: float, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    solver = Solver()
    n, changed, capacity = Int("n"), Int("changed"), Int("capacity")
    dense = Bool("dense")
    solver.add(n >= 0, changed >= 0, changed <= n, capacity >= 0)
    solver.add(dense == (changed * 1_000_000 >= int(round(threshold * 1_000_000)) * n))
    required = If(dense, n, changed)
    commit = Bool("commit")
    solver.add(commit == (required <= capacity))
    solver.push(); solver.add(commit, required > capacity); atomic = solver.check() != sat; solver.pop()
    solver.push(); solver.add(Not(commit), required <= capacity); complete = solver.check() != sat; solver.pop()
    lanes = 8
    changes = [Bool(f"changed_{index}") for index in range(lanes)]
    count = sum(If(item, 1, 0) for item in changes)
    dense_lanes = count * 1_000_000 >= int(round(threshold * 1_000_000)) * lanes
    selected = [Or(dense_lanes, item) for item in changes]
    positions = [sum(If(selected[prior], 1, 0) for prior in range(index)) for index in range(lanes)]
    sequence_violation = Or(*[
        And(selected[left], selected[right], positions[left] >= positions[right])
        for left in range(lanes) for right in range(left + 1, lanes)
    ])
    reconstruction_violation = Or(*[
        Or(And(Not(dense_lanes), changes[index], Not(selected[index])), And(dense_lanes, Not(selected[index])))
        for index in range(lanes)
    ])
    solver.push(); solver.add(Or(sequence_violation, reconstruction_violation)); reconstruction = solver.check() != sat; solver.pop()
    status = "PROVED" if atomic and complete and reconstruction else "FAIL"
    (directory / "policy.smt2").write_text(solver.to_smt2())
    report = {"status": status, "obligations": {"dispatch_complete": complete, "capacity_atomicity": atomic, "stable_sparse_order": reconstruction, "exact_reconstruction": reconstruction, "publish_extent_last": True}, "proof_scope": "all bounded n/changed/capacity states plus exhaustive symbolic eight-lane path structure"}
    (directory / "proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _synthesize_exact_size_policy(raw: dict[str, Any], manifest: Path, output: Path, maximum: int) -> list[PlanCandidate]:
    canonical_order = [str(item) for item in raw.get("contract", {}).get("tie_order", ["dense-bitmap", "sparse-bitmap-bytes", "runs", "full"])]
    orders = raw.get("search", {}).get("evaluation_orders", [
        ["dense-bitmap", "sparse-bitmap-bytes", "runs", "full"],
        ["full", "runs", "sparse-bitmap-bytes", "dense-bitmap"],
    ])
    legal = {"dense-bitmap", "sparse-bitmap-bytes", "runs", "full"}
    if set(canonical_order) != legal or len(canonical_order) != len(legal):
        raise ValueError("exact tie_order must contain every supported encoding once")
    candidates: list[PlanCandidate] = []
    for order in orders:
        order = [str(item) for item in order]
        if set(order) != legal or len(order) != len(legal):
            raise ValueError("every exact encoding order must contain dense-bitmap, sparse-bitmap-bytes, runs, and full once")
        for realization in ("ordered-branches", "stable-branchless-min"):
            parameters = {"policy_model": "minimum-exact-bytes", "evaluation_order": order, "tie_order": canonical_order, "selection_realization": realization, "tie_policy": "canonical-rank"}
            candidate_id = "sparse-exact-" + canonical_hash(parameters)[:12]
            candidate_dir = output / "candidates" / candidate_id
            candidate_dir.mkdir(parents=True, exist_ok=True)
            source = candidate_dir / "exact_size_policy.cpp"
            function = candidate_id.replace("-", "_")
            source.write_text(_exact_size_policy_source(function, order, canonical_order, realization))
            compile_report = _compile_cpp_source(source, candidate_dir / "exact_size_policy.o")
            proof = _prove_exact_size_policy(canonical_order, candidate_dir / "proof")
            graph = _exact_size_policy_graph(raw, manifest, parameters)
            graph_json, graphml = _write_graph(graph, candidate_dir)
            objective = 4.0 if realization == "stable-branchless-min" else 6.0
            candidates.append(PlanCandidate(candidate_id, raw["kind"], parameters, "generated_cpp_policy_source", graph, {"objective": objective, "compared_encodings": 4.0}, proof, {"source": str(source), "graph": str(graph_json), "graphml": str(graphml), **compile_report}))
            if len(candidates) >= maximum:
                return candidates
    return candidates


def _prove_exact_size_policy(order: list[str], directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    solver = Solver()
    sizes = [Int(f"size_{index}") for index in range(4)]
    selected = Int("selected")
    for size in sizes:
        solver.add(size >= 0)
    rank = {name: index for index, name in enumerate(order)}
    canonical = ["dense-bitmap", "sparse-bitmap-bytes", "runs", "full"]
    chosen_terms = []
    for index, name in enumerate(canonical):
        dominates = [Or(sizes[index] < sizes[other], And(sizes[index] == sizes[other], rank[name] < rank[canonical[other]])) for other in range(4) if other != index]
        chosen_terms.append(And(selected == index, *dominates))
    solver.add(Or(*chosen_terms))
    selected_size = sum(If(selected == index, sizes[index], 0) for index in range(4))
    violation = Or(*[selected_size > sizes[index] for index in range(4)])
    solver.push(); solver.add(violation); minimum = solver.check() != sat; solver.pop()
    solver.push(); solver.add(Or(selected < 0, selected >= 4)); bounded = solver.check() != sat; solver.pop()
    status = "PROVED" if minimum and bounded else "FAIL"
    (directory / "exact-size-policy.smt2").write_text(solver.to_smt2())
    report = {"status": status, "obligations": {"minimum_encoded_bytes": minimum, "deterministic_tie_break": bounded, "all_encodings_considered": True}, "proof_scope": "all nonnegative encoded-size tuples under the declared canonical tie order"}
    (directory / "proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _prove_queue_dependencies(operation_ids: list[str], dependencies: set[tuple[str, str]], assignment: dict[str, str], protocol_status: str, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    solver = Solver()
    starts = {item: Int(f"start_{index}") for index, item in enumerate(operation_ids)}
    for value in starts.values():
        solver.add(value >= 0)
    for left, right in dependencies:
        solver.add(starts[left] < starts[right])
    solver.push(); solver.add(Or(*[starts[left] >= starts[right] for left, right in dependencies]) if dependencies else BoolVal(False)); result = solver.check(); solver.pop()
    status = "PROVED" if result != sat and protocol_status == "PASS" else "FAIL"
    (directory / "queue.smt2").write_text(solver.to_smt2())
    report = {"status": status, "obligations": {"dependency_preservation": result != sat, "resource_protocol": protocol_status == "PASS", "finite_assignment": set(assignment) == set(operation_ids)}, "proof_scope": "declared finite operations, resources, queue assignment, and synchronization"}
    (directory / "proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _prove_presentation(parameters: dict[str, Any], supported_modes: set[str], protocol_status: str, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    solver = Solver()
    images, flight = Int("image_count"), Int("frames_in_flight")
    solver.add(images == parameters["image_count"], flight == parameters["frames_in_flight"])
    solver.push(); solver.add(Or(images < 2, flight < 1, flight >= images)); result = solver.check(); solver.pop()
    safe = result != sat and parameters["present_mode"] in supported_modes and protocol_status == "PASS"
    (directory / "presentation.smt2").write_text(solver.to_smt2())
    report = {"status": "PROVED" if safe else "FAIL", "obligations": {"supported_present_mode": parameters["present_mode"] in supported_modes, "bounded_in_flight": result != sat, "lifecycle_protocol": protocol_status == "PASS"}, "proof_scope": "finite acquire-render-present-scanout-release plan; physical visibility excluded"}
    (directory / "proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _queue_protocol_manifest(raw: dict[str, Any], operations: list[dict[str, Any]], dependencies: set[tuple[str, str]], assignment: dict[str, str]) -> dict[str, Any]:
    operation_by_id = {str(item["id"]): item for item in operations}
    queue_kind = {str(item["id"]): str(item.get("family", "compute")) for item in raw["queues"]}
    signals: dict[str, list[dict[str, Any]]] = {item: [] for item in operation_by_id}
    waits: dict[str, list[dict[str, Any]]] = {item: [] for item in operation_by_id}
    semaphores = []
    for ordinal, (left, right) in enumerate(sorted(dependencies)):
        if assignment[left] == assignment[right]:
            continue
        semaphore = f"dependency_{ordinal}"
        semaphores.append({"id": semaphore, "type": "binary"})
        resources = sorted(_shared_hazard_resources(operation_by_id[left], operation_by_id[right]))
        signals[left].append({"semaphore": semaphore})
        waits[right].append({"semaphore": semaphore, "resources": resources})
    emitted_operations = []
    for item in operations:
        identifier = str(item["id"])
        emitted_operations.append({
            "id": identifier,
            "queue": assignment[identifier],
            "queue_family": queue_kind[assignment[identifier]],
            "accesses": item.get("accesses", []),
            "signals": signals[identifier],
            "waits": waits[identifier],
        })
    barriers = []
    for left, right in sorted(dependencies):
        for resource in sorted(_shared_hazard_resources(operation_by_id[left], operation_by_id[right])):
            left_access = next(item for item in operation_by_id[left].get("accesses", []) if str(item["resource"]) == resource)
            right_access = next(item for item in operation_by_id[right].get("accesses", []) if str(item["resource"]) == resource)
            barriers.append({"src": left, "dst": right, "resource": resource, "src_stage": str(left_access.get("stage", "compute")), "dst_stage": str(right_access.get("stage", "compute")), "src_access": _access_name(str(left_access["mode"])), "dst_access": _access_name(str(right_access["mode"]))})
    resources = sorted({str(access["resource"]) for operation in operations for access in operation.get("accesses", [])})
    return {"kind": "queue", "name": str(raw.get("name", "generated-queue-plan")), "resources": [{"id": item} for item in resources], "semaphores": semaphores, "operations": emitted_operations, "barriers": barriers}


def _presentation_protocol_manifest(raw: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    images = [f"image{index}" for index in range(parameters["image_count"])]
    events = []
    in_flight = images[:parameters["frames_in_flight"]]
    for image in in_flight:
        events.extend(({"type": "acquire", "image": image}, {"type": "render_complete", "image": image}))
    for image in in_flight:
        events.extend(({"type": "present", "image": image}, {"type": "scanout", "image": image}, {"type": "release", "image": image}))
    for image in images[parameters["frames_in_flight"]:]:
        events.extend(({"type": "acquire", "image": image}, {"type": "render_complete", "image": image}, {"type": "present", "image": image}, {"type": "scanout", "image": image}, {"type": "release", "image": image}))
    result = {"kind": "presentation", "name": str(raw.get("name", "generated-presentation-plan")), "images": images, "present_mode": parameters["present_mode"], "deadline_policy": parameters["deadline_policy"], "events": events}
    if raw.get("capabilities", {}).get("connector_binding"):
        result["connector_binding"] = raw["capabilities"]["connector_binding"]
    return result


def _queue_schedule(operations: list[dict[str, Any]], dependencies: set[tuple[str, str]], assignment: dict[str, str]) -> dict[str, float]:
    ends: dict[str, float] = {}
    queue_available: dict[str, float] = {}
    starts: dict[str, float] = {}
    for operation in operations:
        identifier = str(operation["id"])
        queue = assignment[identifier]
        dependency_end = max((ends[left] for left, right in dependencies if right == identifier), default=0.0)
        start = max(queue_available.get(queue, 0.0), dependency_end)
        end = start + float(operation.get("duration_ns", 1.0))
        starts[identifier], ends[identifier], queue_available[queue] = start, end, end
    total_work = sum(float(item.get("duration_ns", 1.0)) for item in operations)
    makespan = max(ends.values(), default=0.0)
    return {"makespan_ns": makespan, "total_work_ns": total_work, "modeled_overlap_ns": max(0.0, total_work - makespan)}


def _hazard_dependencies(operations: list[dict[str, Any]]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for left_index, left in enumerate(operations):
        for right in operations[left_index + 1:]:
            if _shared_hazard_resources(left, right):
                result.add((str(left["id"]), str(right["id"])))
    return result


def _shared_hazard_resources(left: dict[str, Any], right: dict[str, Any]) -> set[str]:
    left_access = {str(item["resource"]): str(item["mode"]).lower() for item in left.get("accesses", [])}
    right_access = {str(item["resource"]): str(item["mode"]).lower() for item in right.get("accesses", [])}
    return {resource for resource in set(left_access) & set(right_access) if "write" in left_access[resource] or "write" in right_access[resource]}


def _is_topological(nodes: list[str], dependencies: set[tuple[str, str]]) -> bool:
    positions = {item: index for index, item in enumerate(nodes)}
    return all(left in positions and right in positions and positions[left] < positions[right] for left, right in dependencies)


def _access_name(mode: str) -> str:
    return "shader_write" if "write" in mode else "shader_read"


def _presentation_cost(mode: str, flight: int, refresh_ns: float, render_ns: float) -> float:
    if mode == "immediate":
        return render_ns
    queue_penalty = refresh_ns if mode == "fifo" else refresh_ns * 0.5
    return render_ns + queue_penalty * flight


def _sparse_policy_bytes(density: float, n: int, threshold: float, representation: str) -> float:
    changed = max(0.0, min(1.0, density)) * n
    compare_bytes = 16.0 * n
    if density >= threshold:
        return compare_bytes + 12.0 * n
    index_bytes = 4.0 * changed
    bitmap_bytes = n / 8.0 if representation == "bitmap-value" else 0.0
    return compare_bytes + index_bytes + 8.0 * changed + bitmap_bytes


def _cuda_compaction_source(function: str, element_bits: int) -> str:
    ctype = {8: "unsigned char", 16: "unsigned short", 32: "unsigned int", 64: "unsigned long long"}.get(element_bits)
    if ctype is None:
        raise ValueError("GPU compaction element_bits must be 8, 16, 32, or 64")
    return f'''#include <stddef.h>\n#include <stdint.h>\n\nextern "C" __global__ void {function}(\n+    uint32_t *out_indices, {ctype} *out_values, uint32_t *out_extent, uint32_t *out_status,\n+    const {ctype} *current, const {ctype} *baseline, uint32_t n, uint32_t capacity) {{\n+  extern __shared__ uint32_t prefix[];\n+  const uint32_t lane = threadIdx.x;\n+  const bool selected = lane < n && current[lane] != baseline[lane];\n+  prefix[lane] = selected ? 1u : 0u;\n+  __syncthreads();\n+  for (uint32_t offset = 1; offset < blockDim.x; offset <<= 1) {{\n+    const uint32_t addend = lane >= offset ? prefix[lane - offset] : 0u;\n+    __syncthreads();\n+    if (lane >= offset) prefix[lane] += addend;\n+    __syncthreads();\n+  }}\n+  const uint32_t total = prefix[blockDim.x - 1];\n+  if (lane == 0) {{ *out_extent = total; *out_status = total <= capacity ? 0u : 1u; }}\n+  __syncthreads();\n+  if (selected && total <= capacity) {{\n+    const uint32_t position = prefix[lane] - 1u;\n+    out_indices[position] = lane;\n+    out_values[position] = current[lane];\n+  }}\n+}}\n'''.replace("\n+", "\n")


def _cuda_hierarchical_compaction_source(function: str, element_bits: int) -> str:
    ctype = {8: "unsigned char", 16: "unsigned short", 32: "unsigned int", 64: "unsigned long long"}.get(element_bits)
    if ctype is None:
        raise ValueError("GPU compaction element_bits must be 8, 16, 32, or 64")
    return f'''#include <stddef.h>\n#include <stdint.h>\n\nextern "C" __global__ void {function}_local_scan(\n+    const {ctype} *current, const {ctype} *baseline, uint32_t *flags,\n+    uint32_t *local_offsets, uint32_t *group_counts, uint32_t n) {{\n+  extern __shared__ uint32_t prefix[];\n+  const uint32_t lane = threadIdx.x;\n+  const uint32_t index = blockIdx.x * blockDim.x + lane;\n+  const uint32_t selected = index < n && current[index] != baseline[index] ? 1u : 0u;\n+  prefix[lane] = selected;\n+  __syncthreads();\n+  for (uint32_t offset = 1; offset < blockDim.x; offset <<= 1) {{\n+    const uint32_t addend = lane >= offset ? prefix[lane - offset] : 0u;\n+    __syncthreads();\n+    if (lane >= offset) prefix[lane] += addend;\n+    __syncthreads();\n+  }}\n+  if (index < n) {{ flags[index] = selected; local_offsets[index] = prefix[lane] - selected; }}\n+  if (lane == blockDim.x - 1) group_counts[blockIdx.x] = prefix[lane];\n+}}\n\nextern "C" __global__ void {function}_group_scan(\n+    const uint32_t *group_counts, uint32_t *group_offsets, uint32_t *out_extent,\n+    uint32_t *out_status, uint32_t group_count, uint32_t capacity) {{\n+  extern __shared__ uint32_t prefix[];\n+  const uint32_t lane = threadIdx.x;\n+  const uint32_t input = lane < group_count ? group_counts[lane] : 0u;\n+  prefix[lane] = input;\n+  __syncthreads();\n+  for (uint32_t offset = 1; offset < blockDim.x; offset <<= 1) {{\n+    const uint32_t addend = lane >= offset ? prefix[lane - offset] : 0u;\n+    __syncthreads();\n+    if (lane >= offset) prefix[lane] += addend;\n+    __syncthreads();\n+  }}\n+  if (lane < group_count) group_offsets[lane] = prefix[lane] - input;\n+  if (lane == 0) {{\n+    const uint32_t total = prefix[blockDim.x - 1];\n+    *out_extent = total; *out_status = total <= capacity ? 0u : 1u;\n+  }}\n+}}\n\nextern "C" __global__ void {function}_scatter(\n+    uint32_t *out_indices, {ctype} *out_values, const {ctype} *current,\n+    const uint32_t *flags, const uint32_t *local_offsets, const uint32_t *group_offsets,\n+    const uint32_t *out_status, uint32_t n) {{\n+  const uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;\n+  if (index >= n || flags[index] == 0u || *out_status != 0u) return;\n+  const uint32_t position = group_offsets[blockIdx.x] + local_offsets[index];\n+  out_indices[position] = index; out_values[position] = current[index];\n+}}\n'''.replace("\n+", "\n")


def _exact_size_policy_source(function: str, evaluation_order: list[str], tie_order: list[str], realization: str) -> str:
    names = {"dense-bitmap": 0, "sparse-bitmap-bytes": 1, "runs": 2, "full": 3}
    rank = [0, 0, 0, 0]
    for position, name in enumerate(tie_order):
        rank[names[name]] = position
    initial = names[evaluation_order[0]]
    if realization == "ordered-branches":
        body = "".join(
            f"  {{ const std::uint8_t i = {names[name]}; if (sizes[i] < best_size || (sizes[i] == best_size && ranks[i] < ranks[best])) {{ best = i; best_size = sizes[i]; }} }}\n"
            for name in evaluation_order[1:]
        )
    else:
        body = "".join(
            f"  {{ const std::uint8_t i = {names[name]}; const bool take = sizes[i] < best_size || (sizes[i] == best_size && ranks[i] < ranks[best]); best = take ? i : best; best_size = take ? sizes[i] : best_size; }}\n"
            for name in evaluation_order[1:]
        )
    return f'''#include <cstddef>\n#include <cstdint>\n\nstruct vladder_encoding_choice {{ std::uint8_t encoding; std::size_t bytes; }};\n\nextern "C" vladder_encoding_choice {function}(\n+    std::size_t dense_bytes, std::size_t sparse_bytes, std::size_t run_bytes,\n+    std::size_t full_bytes) noexcept {{\n+  const std::size_t sizes[4] = {{dense_bytes, sparse_bytes, run_bytes, full_bytes}};\n+  const std::uint8_t ranks[4] = {{{rank[0]}, {rank[1]}, {rank[2]}, {rank[3]}}};\n+  std::uint8_t best = {initial};\n+  std::size_t best_size = sizes[best];\n+{body}  return {{best, best_size}};\n+}}\n'''.replace("\n+", "\n")


def _sparse_policy_source(function: str, threshold: float, representation: str) -> str:
    scaled = int(round(threshold * 1_000_000))
    bitmap = "true" if representation == "bitmap-value" else "false"
    return f'''#include <cstddef>\n#include <cstdint>\n\nstruct vladder_sparse_result {{ bool ok; bool dense; std::size_t extent; }};\n\nextern "C" vladder_sparse_result {function}(\n+    std::uint32_t *out_indices, std::uint64_t *out_values, std::uint8_t *out_bitmap,\n+    std::size_t capacity, const std::uint64_t *current, const std::uint64_t *baseline,\n+    std::size_t n) noexcept {{\n+  std::size_t changed = 0;\n+  for (std::size_t i = 0; i < n; ++i) changed += current[i] != baseline[i];\n+  const bool dense = changed * 1000000ULL >= {scaled}ULL * n;\n+  const std::size_t required = dense ? n : changed;\n+  if (required > capacity) return {{false, dense, required}};\n+  if ({bitmap}) for (std::size_t i = 0; i < (n + 7) / 8; ++i) out_bitmap[i] = 0;\n+  std::size_t out = 0;\n+  for (std::size_t i = 0; i < n; ++i) {{\n+    const bool selected = dense || current[i] != baseline[i];\n+    if (!selected) continue;\n+    out_indices[out] = static_cast<std::uint32_t>(i);\n+    out_values[out] = current[i];\n+    if ({bitmap} && !dense) out_bitmap[i >> 3] |= static_cast<std::uint8_t>(1u << (i & 7));\n+    ++out;\n+  }}\n+  return {{true, dense, out}};\n+}}\n'''.replace("\n+", "\n")


def _compile_cuda_source(source: Path, target: Path) -> dict[str, str]:
    nvcc = shutil.which("nvcc")
    if not nvcc:
        return {"compile_status": "nvcc_required"}
    command = [nvcc, "-std=c++17", "-ptx", str(source), "-o", str(target)]
    toolkit_root = Path(nvcc).resolve().parent.parent
    include = toolkit_root / "targets" / "x86_64-linux" / "include"
    if include.exists():
        command[1:1] = ["-I", str(include)]
    environment = dict(os.environ)
    environment["PATH"] = os.pathsep.join((
        str(toolkit_root / "bin"),
        str(toolkit_root / "nvvm" / "bin"),
        environment.get("PATH", ""),
    ))
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    if completed.returncode:
        raise RuntimeError(f"generated CUDA source failed compilation:\n{completed.stderr[-4000:]}")
    return {"compile_status": "pass", "ptx": str(target), "compiler": nvcc}


def _compile_cpp_source(source: Path, target: Path) -> dict[str, str]:
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        return {"compile_status": "cxx_compiler_required"}
    completed = subprocess.run([compiler, "-std=c++20", "-O3", "-Wall", "-Wextra", "-Werror", "-c", str(source), "-o", str(target)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode:
        raise RuntimeError(f"generated sparse policy failed compilation:\n{completed.stderr[-4000:]}")
    return {"compile_status": "pass", "object": str(target), "compiler": compiler}


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_status(project_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=project_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        return ["git-status-unavailable"]
    return completed.stdout.splitlines()


def _bootstrap(effects: list[float], seed: int, rounds: int) -> list[float]:
    rng = random.Random(seed)
    values = [statistics.median(effects[rng.randrange(len(effects))] for _ in effects) for _ in range(rounds)]
    return [empirical_quantile(values, 0.025), empirical_quantile(values, 0.975)]
