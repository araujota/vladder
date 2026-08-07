from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

from . import __version__
from .consent import AGENT_EXPERIENCE_REVIEW, CANONICAL_TRAINING_DATA, contribution_stage
from .cpp_adapters import generate_cpp_adapter_bundle
from .automatic import inspect_automatic_region
from .cpp_regions import inspect_cpp_region, isolate_cpp_region, optimize_cpp_region
from .lifetime_workflow import analyze_lifetime_flow, synthesize_lifetime_flow
from .shader_workflow import inspect_shader, synthesize_shader
from .gpu_workflow import capture_gpu_workflow, rank_gpu_workflow, synthesize_gpu_workflow, verify_gpu_workflow
from .state_protocol import verify_state_protocol
from .system_closure import run_system_closure
from .rust_adapter import RustRegionRequest, inspect_rust_region, isolate_rust_region, optimize_rust_region, synthesize_rust_region
from .zig_adapter import ZigRegionRequest, inspect_zig_region, isolate_zig_region, optimize_zig_region, synthesize_zig_region
from .julia_adapter import JuliaRegionRequest, inspect_julia_region, isolate_julia_region, optimize_julia_region, synthesize_julia_region
from .training_workflow import sync_promotion_summary


WORKFLOW_SCHEMA = "vladder-agent-workflow-v1"
SUMMARY_SCHEMA = "vladder-promotion-summary-v1"


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_json(value: Any) -> str:
    return _hash_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def initialize_workflow_manifest(kind: str, output_path: Path) -> dict[str, Any]:
    if kind not in {"c", "cpp", "rust", "zig", "julia", "system", "lifetime", "shader", "gpu", "protocol"}:
        raise ValueError("workflow kind must be c, cpp, rust, zig, julia, system, lifetime, shader, gpu, or protocol")
    region: dict[str, Any]
    if kind == "c":
        region = {"kind": "c", "action": "inspect", "source": "TODO.c", "function": "transform"}
    elif kind == "cpp":
        region = {
            "kind": "cpp", "action": "inspect", "source": "TODO.cpp", "function": "TODO",
            "compile_commands": "build/compile_commands.json", "symbol": None, "command_index": None,
        }
    elif kind == "rust":
        region = {
            "kind": "rust", "action": "inspect", "manifest": "Cargo.toml",
            "source": "src/lib.rs", "function": "TODO", "package": None,
            "target_kind": "lib", "target_name": None, "profile": "release",
            "features": [], "proof_bound": 32,
        }
    elif kind == "zig":
        region = {"kind": "zig", "action": "inspect", "source": "src/root.zig", "function": "TODO", "build_root": ".", "optimize_mode": "ReleaseFast", "target": "native", "proof_bound": 32}
    elif kind == "julia":
        region = {"kind": "julia", "action": "inspect", "project": ".", "source": "src/Package.jl", "module": "TODO", "function": "TODO", "signature": "Vector{UInt8},UInt8", "cpu_target": "native", "proof_bound": 32}
    elif kind == "system":
        region = {"kind": "system", "action": "closure", "manifest": "system-closure.yaml"}
    elif kind == "lifetime":
        region = {"kind": "lifetime", "action": "analyze", "manifest": "lifetime.yaml", "trace": "lifetime.jsonl"}
    elif kind == "shader":
        region = {"kind": "shader", "action": "inspect", "source": "kernel.comp", "target_env": "vulkan1.2", "runner_manifest": None}
    elif kind == "gpu":
        region = {"kind": "gpu", "action": "capture", "manifest": "gpu-workflow.yaml"}
    else:
        region = {"kind": "protocol", "action": "verify", "manifest": "state-protocol.yaml"}
    manifest = {
        "schema_version": WORKFLOW_SCHEMA,
        "name": "TODO-workflow",
        "region": region,
        "contract": {"identity": "TODO", "exact": True},
        "attribution": {"profile_report": "TODO", "regional_share_percent": None},
        "workload": {"identity": "TODO", "held_out": False},
        "promotion": {"minimum_effect_percent": 1.0, "requires_composed_confirmation": True},
        "retained_candidate_identity": None,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def _workflow_key(raw: dict[str, Any], base: Path) -> tuple[str, dict[str, Any]]:
    region = raw.get("region", {})
    file_hashes: dict[str, str] = {}
    for key in ("source", "compile_commands", "manifest", "trace", "runner_manifest", "project", "build_root"):
        value = region.get(key) if isinstance(region, dict) else None
        if not value:
            continue
        path = _resolve(base, str(value))
        if path.is_dir():
            if key == "compile_commands":
                path = path / "compile_commands.json"
            else:
                identities = []
                for name in ("Project.toml", "JuliaProject.toml", "Manifest.toml", "LocalPreferences.toml", "build.zig", "build.zig.zon"):
                    candidate = path / name
                    if candidate.exists(): identities.append({"name": name, "sha256": _hash_bytes(candidate.read_bytes())})
                file_hashes[key] = _hash_json(identities)
                continue
        if path.exists() and path.is_file():
            file_hashes[key] = _hash_bytes(path.read_bytes())
    identity = {
        "vladder_version": __version__,
        "manifest": raw,
        "file_hashes": file_hashes,
    }
    return _hash_json(identity), identity


def run_agent_workflow(manifest_path: Path, output_directory: Path, *, force: bool = False) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("region"), dict):
        raise ValueError("workflow manifest requires a region mapping")
    key, identity = _workflow_key(raw, manifest_path.parent)
    state_path = output_directory / "workflow-state.json"
    summary_path = output_directory / "promotion-summary.json"
    if not force and state_path.exists() and summary_path.exists():
        state = json.loads(state_path.read_text())
        if state.get("workflow_key") == key:
            summary = json.loads(summary_path.read_text())
            summary["optional_contributions"] = _optional_contributions()
            summary["evidence_origin"] = "revalidated"
            summary["newly_computed"] = False
            summary["next_action"] = (
                "evidence inputs are unchanged; use --force only to collect new physical evidence"
                if summary.get("states", {}).get("benchmarked") else summary.get("next_action")
            )
            summary = _finalize_training_contribution(summary, output_directory)
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
            return summary

    region = raw["region"]
    kind = str(region.get("kind", ""))
    action = str(region.get("action", "inspect"))
    stage_dir = output_directory / "stage"
    if kind == "c":
        source = _resolve(manifest_path.parent, str(region["source"]))
        if action == "inspect":
            support = inspect_automatic_region(source, str(region["function"]), stage_dir)
            report = {
                "schema_version": "vladder-c-workflow-inspection-v1",
                "status": "supported" if support.supported else "adapter_required",
                "source": str(source),
                "source_sha256": _hash_bytes(source.read_bytes()),
                "function": str(region["function"]),
                "automatic_region": support.to_dict(),
            }
            report_path = stage_dir / "c-support.json"
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        elif action == "optimize":
            command = [
                sys.executable, "-m", "vladder", "region", "optimize",
                "--source", str(source), "--function", str(region["function"]),
                "--out-dir", str(stage_dir), "--min-speedup-pct",
                str(raw.get("promotion", {}).get("minimum_effect_percent", 1.0)),
            ]
            completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            report_path = stage_dir / "perf.json"
            if not report_path.exists():
                raise RuntimeError(f"bounded C workflow failed ({completed.returncode}): {completed.stderr[-3000:]}")
            report = json.loads(report_path.read_text())
        else:
            raise ValueError(f"unsupported C workflow action: {action}")
        adapter = None
    elif kind == "cpp":
        source = _resolve(manifest_path.parent, str(region["source"]))
        database = _resolve(manifest_path.parent, str(region["compile_commands"]))
        arguments = {
            "symbol": str(region["symbol"]) if region.get("symbol") else None,
            "command_index": int(region["command_index"]) if region.get("command_index") is not None else None,
        }
        if action == "inspect":
            report = inspect_cpp_region(source, str(region["function"]), database, stage_dir, **arguments)
        elif action in {"isolate", "synthesize"}:
            _, report = isolate_cpp_region(source, str(region["function"]), database, stage_dir, **arguments)
        elif action == "optimize":
            _, report = optimize_cpp_region(source, str(region["function"]), database, stage_dir, **arguments)
        else:
            raise ValueError(f"unsupported C++ workflow action: {action}")
        report_path = stage_dir / ("cpp-optimization.json" if action == "optimize" else "cpp-support.json")
        adapter = None
        closure_report = report.get("isolation", report) if isinstance(report.get("isolation", report), dict) else report
        closure = closure_report.get("closure", {})
        if closure.get("disposition") != "automatic" or not closure.get("capabilities", {}).get("benchmark", {}).get("actual"):
            closure_path = stage_dir / ("isolation/cpp-support.json" if action == "optimize" else "cpp-support.json")
            adapter = generate_cpp_adapter_bundle(closure_path, output_directory / "application-adapter")
    elif kind == "rust":
        source = _resolve(manifest_path.parent, str(region["source"]))
        cargo_manifest = _resolve(manifest_path.parent, str(region["manifest"]))
        request = RustRegionRequest(
            manifest_path=cargo_manifest,
            source=source,
            function=str(region["function"]),
            output_directory=stage_dir,
            package=str(region["package"]) if region.get("package") else None,
            target_kind=str(region.get("target_kind", "lib")),
            target_name=str(region["target_name"]) if region.get("target_name") else None,
            profile=str(region.get("profile", "release")),
            features=tuple(str(value) for value in region.get("features", [])),
            proof_bound=int(region.get("proof_bound", 32)),
            minimum_speedup_pct=float(raw.get("promotion", {}).get("minimum_effect_percent", 1.0)),
        )
        actions = {
            "inspect": inspect_rust_region,
            "isolate": isolate_rust_region,
            "synthesize": synthesize_rust_region,
            "optimize": optimize_rust_region,
        }
        if action not in actions:
            raise ValueError(f"unsupported Rust workflow action: {action}")
        report = actions[action](request)
        report_path = stage_dir / {
            "inspect": "rust-support.json", "isolate": "rust-isolation.json",
            "synthesize": "rust-synthesis.json", "optimize": "rust-optimization.json",
        }[action]
        adapter = None
    elif kind == "zig":
        request = ZigRegionRequest(
            source=_resolve(manifest_path.parent, str(region["source"])), function=str(region["function"]),
            output_directory=stage_dir, build_root=_resolve(manifest_path.parent, str(region["build_root"])) if region.get("build_root") else None,
            optimize_mode=str(region.get("optimize_mode", "ReleaseFast")), target=str(region.get("target", "native")),
            proof_bound=int(region.get("proof_bound", 32)), minimum_speedup_pct=float(raw.get("promotion", {}).get("minimum_effect_percent", 1.0)),
        )
        actions = {"inspect": inspect_zig_region, "isolate": isolate_zig_region, "synthesize": synthesize_zig_region, "optimize": optimize_zig_region}
        if action not in actions: raise ValueError(f"unsupported Zig workflow action: {action}")
        report = actions[action](request)
        report_path = stage_dir / {"inspect": "zig-support.json", "isolate": "zig-isolation.json", "synthesize": "zig-synthesis.json", "optimize": "zig-optimization.json"}[action]
        adapter = None
    elif kind == "julia":
        request = JuliaRegionRequest(
            project=_resolve(manifest_path.parent, str(region["project"])), source=_resolve(manifest_path.parent, str(region["source"])),
            module=str(region["module"]), function=str(region["function"]), signature=str(region["signature"]),
            output_directory=stage_dir, proof_bound=int(region.get("proof_bound", 32)),
            minimum_speedup_pct=float(raw.get("promotion", {}).get("minimum_effect_percent", 1.0)), cpu_target=str(region.get("cpu_target", "native")),
        )
        actions = {"inspect": inspect_julia_region, "isolate": isolate_julia_region, "synthesize": synthesize_julia_region, "optimize": optimize_julia_region}
        if action not in actions: raise ValueError(f"unsupported Julia workflow action: {action}")
        report = actions[action](request)
        report_path = stage_dir / {"inspect": "julia-support.json", "isolate": "julia-isolation.json", "synthesize": "julia-synthesis.json", "optimize": "julia-optimization.json"}[action]
        adapter = None
    elif kind == "system":
        if action != "closure":
            raise ValueError(f"unsupported system workflow action: {action}")
        report = run_system_closure(_resolve(manifest_path.parent, str(region["manifest"])), stage_dir)
        report_path = stage_dir / "system-closure-report.json"
        adapter = None
    elif kind == "lifetime":
        lifetime_manifest = _resolve(manifest_path.parent, str(region["manifest"]))
        trace = _resolve(manifest_path.parent, str(region["trace"]))
        report = (
            synthesize_lifetime_flow(lifetime_manifest, trace, stage_dir)
            if action == "synthesize" else analyze_lifetime_flow(lifetime_manifest, trace, stage_dir)
        )
        report_path = stage_dir / ("lifetime-report.json" if action == "synthesize" else "lifetime-analysis.json")
        adapter = None
    elif kind == "shader":
        source = _resolve(manifest_path.parent, str(region["source"]))
        target = str(region.get("target_env", "vulkan1.2"))
        runner = _resolve(manifest_path.parent, str(region["runner_manifest"])) if region.get("runner_manifest") else None
        report = (
            synthesize_shader(source, stage_dir, target_env=target, runner_manifest=runner)
            if action == "synthesize" else inspect_shader(source, stage_dir, target_env=target)
        )
        report_path = stage_dir / ("shader-report.json" if action == "synthesize" else "shader-inspection.json")
        adapter = None
    elif kind == "gpu":
        gpu_manifest = _resolve(manifest_path.parent, str(region["manifest"]))
        actions = {
            "capture": capture_gpu_workflow,
            "synthesize": synthesize_gpu_workflow,
            "verify": verify_gpu_workflow,
            "rank": rank_gpu_workflow,
        }
        if action not in actions:
            raise ValueError(f"unsupported GPU workflow action: {action}")
        report = actions[action](gpu_manifest, stage_dir)
        report_path = stage_dir / "gpu-workflow.json"
        adapter = None
    elif kind == "protocol":
        protocol_manifest = _resolve(manifest_path.parent, str(region["manifest"]))
        report = verify_state_protocol(protocol_manifest, stage_dir)
        report_path = stage_dir / "protocol-proof.json"
        adapter = None
    else:
        raise ValueError("region.kind must be c, cpp, rust, zig, julia, system, lifetime, shader, gpu, or protocol")

    summary = build_promotion_summary(
        report,
        report_path=report_path,
        workflow_kind=kind,
        workflow_key=key,
        retained_candidate_identity=raw.get("retained_candidate_identity"),
        adapter=adapter,
        manifest=raw,
    )
    summary["evidence_origin"] = "newly_computed"
    summary["newly_computed"] = True
    summary = _finalize_training_contribution(summary, output_directory)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    state = {
        "schema_version": "vladder-workflow-state-v1",
        "workflow_key": key,
        "identity": identity,
        "summary": str(summary_path),
        "stage_report": str(report_path),
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return summary


def build_promotion_summary(
    report: dict[str, Any],
    *,
    report_path: Path,
    workflow_kind: str | None = None,
    workflow_key: str | None = None,
    retained_candidate_identity: Any = None,
    adapter: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kind = workflow_kind or _infer_kind(report)
    states = {
        "workflow_completed": True,
        "meaningful_semantic_coverage": False,
        "candidate_generated": False,
        "candidate_proved": False,
        "physically_benchmarked": False,
        "application_integrated": False,
        "production_promoted": False,
        "production_retained": False,
    }
    proof_class = "none"
    disposition = "inspected_only"
    blockers: list[str] = []
    next_action = "inspect the stage report"
    candidate_identity = None
    architectural_findings: list[dict[str, Any]] = []

    if kind == "c":
        support = report.get("automatic_region", {})
        states["meaningful_semantic_coverage"] = bool(support.get("supported") or report.get("analysis"))
        candidates = report.get("candidates", [])
        states["candidate_generated"] = bool(candidates)
        winner = report.get("winner") if isinstance(report.get("winner"), dict) else None
        states["candidate_proved"] = bool(
            winner and winner.get("proof", {}).get("status") == "PROVED"
            and winner.get("memory_proof", {}).get("status") == "proved"
            and winner.get("alive2", {}).get("status") == "correct"
        )
        states["physically_benchmarked"] = bool(winner and winner.get("status") == "PASS")
        states["production_promoted"] = bool(report.get("promotion", {}).get("promotable"))
        proof_class = str(report.get("verification_tier", "bounded_c_region"))
        disposition = "promotable" if states["production_promoted"] else str(report.get("status", "inspected"))
        candidate_identity = winner.get("candidate") if winner else None
        next_action = (
            "verify the applied source and run composed-system confirmation"
            if states["production_promoted"] else
            "run bounded C optimization" if states["meaningful_semantic_coverage"] and not states["candidate_generated"] else
            "resolve the named C adapter boundary" if not states["meaningful_semantic_coverage"] else
            "retain the negative result or broaden only attribution-justified grammar"
        )
    elif kind == "cpp":
        local_report = report.get("isolation", report) if isinstance(report.get("isolation", report), dict) else report
        closure = local_report.get("closure", {})
        capabilities = closure.get("capabilities", {})
        states["meaningful_semantic_coverage"] = bool(capabilities.get("semantic_capture", {}).get("actual"))
        states["candidate_generated"] = bool(capabilities.get("candidate_generation", {}).get("actual"))
        states["candidate_proved"] = bool(capabilities.get("local_proof", {}).get("actual"))
        states["physically_benchmarked"] = bool(capabilities.get("benchmark", {}).get("actual"))
        states["application_integrated"] = bool(report.get("application_verification", {}).get("status") == "pass")
        promotion = report.get("promotion", local_report.get("promotion", {}))
        states["production_promoted"] = bool(promotion.get("promotable"))
        proof_class = str(report.get("proof_classification", local_report.get("proof_classification", "unclassified")))
        disposition = str(closure.get("disposition", local_report.get("status", "unclassified")))
        blockers.extend(str(item.get("reason", item.get("kind"))) for item in local_report.get("adapters", []))
        if adapter:
            blockers.extend(str(item.get("reason")) for item in adapter.get("unresolved_boundaries", []))
        candidate_identity = report.get("winner", {}).get("candidate_sha256") if isinstance(report.get("winner"), dict) else None
        next_action = (
            "run project integration and composed benchmark" if states["physically_benchmarked"] else
            "complete the generated application adapter and paired benchmark" if adapter else
            "generate the C++ application adapter and model the unresolved boundary" if disposition not in {"automatic", "automatic_with_benchmark_adapter"} else
            "materialize and prove an admitted local candidate" if states["meaningful_semantic_coverage"] else
            "resolve source, overload, template, or compile-command selection"
        )
    elif kind in {"rust", "zig", "julia"}:
        support = report.get("support", report)
        graph = support.get("semantic_graph")
        states["meaningful_semantic_coverage"] = bool(graph and graph.get("nodes"))
        candidates = report.get("candidates", [])
        states["candidate_generated"] = bool(candidates)
        states["candidate_proved"] = bool(candidates) and any(
            item.get("proof_status") == "PASS" for item in candidates
        )
        states["physically_benchmarked"] = bool(report.get("measurements"))
        states["production_promoted"] = bool(report.get("promotion", {}).get("promotable"))
        winner = report.get("winner") if isinstance(report.get("winner"), dict) else None
        candidate_identity = winner.get("candidate", {}).get("id") if winner else None
        proof_class = f"{kind}_source_schedule_z3_plus_bounded_llvm_refinement" if states["candidate_proved"] else f"{kind}_native_semantic_capture"
        disposition = f"promotable_local_{kind}_candidate" if states["production_promoted"] else str(report.get("status", "inspected"))
        blockers.extend(str(item.get("reason", item.get("kind"))) for item in support.get("blockers", []))
        next_action = (
            f"apply the emitted {kind} patch, run project tests, and confirm the project workload"
            if states["production_promoted"] else
            f"physically rank the proved {kind} candidates" if states["candidate_proved"] and not states["physically_benchmarked"] else
            "retain the measured negative result or add only an attribution-justified common grammar rule"
            if states["physically_benchmarked"] else
            f"run {kind} synthesis" if states["meaningful_semantic_coverage"] else
            f"resolve the named {kind} semantic adapter boundary"
        )
    elif kind == "system":
        graph = report.get("system_graph", {})
        states["meaningful_semantic_coverage"] = bool(graph.get("functions"))
        states["candidate_proved"] = report.get("proof", {}).get("status") == "PASS"
        proof_class = "compositional_effect_and_protocol_closure"
        disposition = str(graph.get("closure", report.get("status", "unclassified")))
        blockers.extend(item.get("missing_contract", "unresolved boundary") for item in report.get("boundary_summary", []))
        for item in report.get("boundary_summary", []):
            architectural_findings.append({
                "kind": "scoped_external_or_protocol_boundary",
                "count": item.get("count", 0),
                "functions": item.get("functions", []),
            })
        next_action = str(report.get("next_action", "run attributed grammars in closed components"))
    elif kind == "lifetime":
        quality = report.get("trace_quality", {})
        states["meaningful_semantic_coverage"] = quality.get("status") == "sufficient"
        states["candidate_generated"] = int(report.get("candidate_count", 0)) > 0
        states["candidate_proved"] = int(report.get("accepted_count", 0)) > 0
        proof_class = "bounded_lifetime_state_transition" if states["candidate_proved"] else "none"
        disposition = str(report.get("status", "unclassified"))
        if not states["meaningful_semantic_coverage"]:
            blockers.append("lifetime trace has insufficient construction/consumption/reuse or residency evidence")
        summary = report.get("attribution", {}).get("summary", {})
        for key, finding in (
            ("repeated_realization_items", "repeated realization volume"),
            ("over_retained_items", "post-final-use residency"),
            ("redundant_transfer_items", "repeated boundary transfer volume"),
        ):
            if int(summary.get(key, 0)):
                architectural_findings.append({"kind": finding, "item_count": int(summary[key])})
        next_action = report.get("next_action") or (
            "realize the winning lifetime plan with fallback and debug oracle"
            if states["candidate_proved"] else "capture a stronger lifetime trace"
        )
    elif kind == "shader":
        states["meaningful_semantic_coverage"] = report.get("status") == "pass"
        states["candidate_generated"] = int(report.get("candidate_count", 0)) > 0
        winner = report.get("winner")
        states["candidate_proved"] = bool(winner and winner.get("semantic_equivalence") == "PASS")
        states["physically_benchmarked"] = bool(winner and winner.get("runner_evidence"))
        states["production_promoted"] = bool(winner and winner.get("promotable"))
        proof_class = "gpu_output_differential" if states["candidate_proved"] else "structurally_valid_spirv"
        disposition = "gpu_candidate_win" if states["production_promoted"] else "output_oracle_required"
        if not states["candidate_proved"]:
            blockers.append("no application GPU output oracle established candidate equivalence")
        next_action = str(report.get("next_action", "provide an output and timestamp runner"))
        candidate_identity = winner.get("module_sha256") if isinstance(winner, dict) else None
    elif kind == "gpu":
        kernel = report.get("kernel", {})
        graph = kernel.get("graph", {}) if isinstance(kernel, dict) else {}
        states["meaningful_semantic_coverage"] = bool(graph.get("nodes")) and not kernel.get("unsupported_operations")
        states["candidate_generated"] = int(report.get("candidate_count", 0)) > 0 or bool(report.get("static_finalists"))
        protocols = report.get("protocols", [])
        protocols_pass = bool(protocols) and all(item.get("status") == "PASS" for item in protocols)
        physical = report.get("physical", {})
        winner = physical.get("winner") if isinstance(physical, dict) else None
        states["candidate_proved"] = bool(
            (report.get("status") == "PASS" or protocols_pass)
            and (states["meaningful_semantic_coverage"] or report.get("kernel_capture_complete"))
        )
        states["physically_benchmarked"] = bool(physical.get("candidates")) if isinstance(physical, dict) else False
        states["production_promoted"] = bool(report.get("promotion", {}).get("promotable"))
        proof_class = str(report.get("proof_classification", "heterogeneous_kernel_and_bounded_device_protocol" if states["candidate_proved"] else "partial_heterogeneous_evidence"))
        disposition = str(report.get("bounded_classification", report.get("status", "inspected")))
        blockers.extend(str(item) for item in kernel.get("unsupported_operations", []))
        for item in protocols:
            blockers.extend(issue.get("message", issue.get("id", "protocol issue")) for issue in item.get("issues", []))
        candidate_identity = winner.get("candidate_id") if isinstance(winner, dict) else None
        next_action = str(report.get("next_action") or (
            "integrate the promoted kernel and protocol plan, then run composed-system confirmation"
            if states["production_promoted"] else
            "run clean exact-output physical ranking" if states["candidate_proved"] else
            "resolve unsupported kernel operations or device-protocol counterexamples"
        ))
    elif kind == "protocol":
        states["meaningful_semantic_coverage"] = True
        states["candidate_proved"] = report.get("status") == "PASS"
        proof_class = "bounded_z3_state_protocol"
        disposition = "protocol_proved" if states["candidate_proved"] else "protocol_counterexample"
        blockers.extend(item["name"] for item in report.get("obligations", []) if item.get("status") != "PROVED")
        next_action = "bind the proved projection to production state and run sequence differential tests"

    states["production_retained"] = bool(
        states["production_promoted"] and candidate_identity and retained_candidate_identity == candidate_identity
    )
    result_class = (
        "retained_revalidated" if states["production_retained"] else
        "new_production_optimization" if states["production_promoted"] else
        "candidate_proved_not_benchmarked" if states["candidate_proved"] and not states["physically_benchmarked"] else
        "candidate_generated_not_proved" if states["candidate_generated"] else
        "architectural_finding" if architectural_findings else
        "inspection_only"
    )
    artifacts = _decisive_artifacts(report, report_path, adapter)
    lineage = _lineage(report, report_path, artifacts)
    return {
        "schema_version": SUMMARY_SCHEMA,
        "workflow_kind": kind,
        "workflow_key": workflow_key,
        "states": states,
        "proof_class": proof_class,
        "disposition": disposition,
        "result_classification": result_class,
        "candidate_identity": candidate_identity,
        "retained_candidate_identity": retained_candidate_identity,
        "promotion_permitted": states["production_promoted"],
        "blockers": sorted(set(blockers)),
        "next_action": next_action,
        "meaningful_coverage": "meaningful" if states["meaningful_semantic_coverage"] else "insufficient_or_selection_only",
        "architectural_findings": architectural_findings,
        "decisive_artifacts": artifacts[:5],
        "artifact_lineage": lineage,
        "manifest_identity": _hash_json(manifest) if manifest else None,
        "claim_boundary": "promotion requires every state through application integration; local proof never implies external protocol equivalence",
        "optional_contributions": _optional_contributions(),
    }


def _optional_contributions() -> dict[str, Any]:
    return {
        "canonical_training_data": contribution_stage(CANONICAL_TRAINING_DATA),
        "agent_experience_review": contribution_stage(AGENT_EXPERIENCE_REVIEW),
        "authority": (
            "canonical training submission is an automatic terminal stage after a complete "
            "promotion summary only when durable training consent is opt_in; review submission "
            "always remains separately approved"
        ),
    }


def _finalize_training_contribution(summary: dict[str, Any], output_directory: Path) -> dict[str, Any]:
    """Submit one complete terminal disposition when durable training consent permits it."""
    training = summary.get("optional_contributions", {}).get("canonical_training_data", {})
    if training.get("status") != "continuous_contribution_enabled":
        return summary
    try:
        if summary.get("schema_version") != SUMMARY_SCHEMA:
            raise ValueError("training contribution requires a promotion summary")
        if not summary.get("states", {}).get("workflow_completed"):
            raise ValueError("training contribution requires a terminal workflow disposition")
        if not summary.get("workflow_key"):
            raise ValueError("training contribution requires a deterministic workflow identity")
        sync = sync_promotion_summary(summary, output_directory / "training-contribution")
        submitted = sync.get("status") == "pass"
        updated = {
            **training,
            "status": "continuous_contribution_completed" if submitted else "continuous_contribution_queued",
            "network_action_performed": True,
            "trigger": "terminal_promotion_summary",
            "record_complete": True,
            "database_acknowledged": submitted,
            "retry_pending": not submitted,
            "sync_report": str(output_directory / "training-contribution/promotion-training-sync.json"),
            "record_forms": sync["record_forms"],
        }
    except Exception as error:
        updated = {
            **training,
            "status": "continuous_contribution_failed",
            "network_action_performed": False,
            "trigger": "terminal_promotion_summary",
            "record_complete": False,
            "error": str(error),
            "next_action": "retry the registered training exporter; optimization evidence remains valid",
        }
    summary["optional_contributions"]["canonical_training_data"] = updated
    return summary


def summarize_report(report_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    report_path = report_path.resolve()
    report = json.loads(report_path.read_text())
    summary = build_promotion_summary(
        report,
        report_path=report_path,
        workflow_key=_hash_json({
            "report_schema": report.get("schema_version"),
            "report_sha256": _hash_bytes(report_path.read_bytes()),
        }),
    )
    summary["evidence_origin"] = "imported_stage_report"
    summary["newly_computed"] = False
    contribution_root = output_path.resolve().parent if output_path else report_path.parent
    summary = _finalize_training_contribution(summary, contribution_root)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def query_lineage(summary_path: Path, artifact: str) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text())
    lineage = summary.get("artifact_lineage", {})
    edges = lineage.get("edges", [])
    ancestors: set[str] = set()
    descendants: set[str] = set()
    changed = True
    while changed:
        changed = False
        for edge in edges:
            src, dst = str(edge["from"]), str(edge["to"])
            if dst == artifact or dst in ancestors:
                if src not in ancestors:
                    ancestors.add(src); changed = True
            if src == artifact or src in descendants:
                if dst not in descendants:
                    descendants.add(dst); changed = True
    return {"artifact": artifact, "ancestors": sorted(ancestors), "descendants": sorted(descendants)}


def _infer_kind(report: dict[str, Any]) -> str:
    schema = str(report.get("schema_version", ""))
    if "cpp" in schema or report.get("language") == "c++":
        return "cpp"
    if "rust" in schema or report.get("source_language") == "rust":
        return "rust"
    if "zig" in schema or report.get("source_language") == "zig":
        return "zig"
    if "julia" in schema or report.get("source_language") == "julia":
        return "julia"
    if "system-closure" in schema or "system_graph" in report:
        return "system"
    if schema.startswith("vladder-c-") or "automatic_region" in report:
        return "c"
    if "lifetime" in schema:
        return "lifetime"
    if "shader" in schema or report.get("language") == "spirv-compute":
        return "shader"
    if "gpu-workflow" in schema or "heterogeneous" in schema:
        return "gpu"
    if "protocol" in schema:
        return "protocol"
    return "unknown"


def _decisive_artifacts(report: dict[str, Any], report_path: Path, adapter: dict[str, Any] | None) -> list[dict[str, str]]:
    artifacts = [{"role": "stage_report", "path": str(report_path)}]
    source_artifacts = report.get("artifacts", {})
    if isinstance(source_artifacts, dict):
        priorities = ("provenance", "proof_envelope", "regenerated_cpp", "optimized_cpp", "adapter_contract")
        for name in priorities:
            if source_artifacts.get(name):
                artifacts.append({"role": name, "path": str(source_artifacts[name])})
    support = report.get("support", report)
    if isinstance(support, dict):
        rust_artifacts = support.get("artifacts", {})
        if isinstance(rust_artifacts, dict):
            for name in ("mir", "llvm_ir", "assembly", "source"):
                if rust_artifacts.get(name) and len(artifacts) < 5:
                    artifacts.append({"role": f"rust_{name}", "path": str(rust_artifacts[name])})
    if adapter:
        for name in ("manifest", "benchmark_adapter", "observable_oracle", "agent_task"):
            if adapter.get(name):
                artifacts.append({"role": f"application_{name}", "path": str(adapter[name])})
    if report.get("winner") and len(artifacts) < 5:
        artifacts.append({"role": "winner_embedded_in_report", "path": str(report_path)})
    return artifacts


def _lineage(report: dict[str, Any], report_path: Path, artifacts: list[dict[str, str]]) -> dict[str, Any]:
    nodes = [{"id": "source", "kind": "source", "identity": report.get("source_sha256") or report.get("manifest_hash")}]
    nodes.extend({"id": item["role"], "kind": "artifact", "path": item["path"]} for item in artifacts)
    nodes.append({"id": "disposition", "kind": "decision"})
    edges = []
    previous = "source"
    for item in artifacts:
        edges.append({"from": previous, "to": item["role"]})
        previous = item["role"]
    edges.append({"from": previous, "to": "disposition"})
    return {"nodes": nodes, "edges": edges, "queryable_by": "artifact id"}
