from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any

import yaml

from .language_adapter import (
    LANGUAGE_ADAPTER_PROTOCOL_VERSION,
    LanguageAdapterRegistry,
    LanguageCapability,
    LanguageRegionEvidence,
    canonical_hash,
    file_sha256,
)
from .canonical_regions import (
    CanonicalBoundedRegion,
    CanonicalRegionError,
    build_canonical_graph,
    classify_canonical_region,
    corroborate_compiler_shape,
)
from .canonical_executable import synthesize_canonical_region
from .paired_benchmark import run_paired_benchmark
from .closure_bindings import rust_function_summary
from .rust_semantics import (
    RUST_SUPPORT_VERSION,
    MirFunction,
    RustEffectSummary,
    RustFunction,
    RustKernelModel,
    build_semantic_flow_graph,
    classify_rust_effects,
    extract_rust_function,
    infer_rust_kernel_model,
    parse_mir_functions,
    select_mir_function,
)
from .rust_verification import (
    RustCandidate,
    build_llvm_refinement_unit,
    build_rust_benchmark_harness,
    compile_rust_executable,
    compile_rust_library,
    generate_rust_candidates,
    prove_bounded_mir_equivalence,
    run_alive2_refinement,
    rustfmt_source,
    validate_candidate_mir,
)


@dataclass(frozen=True)
class RustRegionRequest:
    manifest_path: Path
    source: Path
    function: str
    output_directory: Path
    package: str | None = None
    target_kind: str = "lib"
    target_name: str | None = None
    profile: str = "release"
    features: tuple[str, ...] = ()
    proof_bound: int = 32
    minimum_speedup_pct: float = 1.0
    benchmark_elements: int = 1 << 20
    benchmark_inner: int = 128
    benchmark_processes: int = 8
    benchmark_repetitions: int = 2
    cpu: int | None = None


@dataclass(frozen=True)
class RustCaptureContext:
    request: RustRegionRequest
    function: RustFunction
    effects: RustEffectSummary
    mir: MirFunction
    all_mir: tuple[MirFunction, ...]
    model: RustKernelModel | None
    canonical_region: CanonicalBoundedRegion | None
    build_identity: dict[str, Any]
    artifacts: dict[str, str]
    evidence: LanguageRegionEvidence


class RustLanguageAdapter:
    name = "rustc-mir-llvm"
    source_language = "rust"
    support_version = RUST_SUPPORT_VERSION

    def inspect(self, request: RustRegionRequest) -> LanguageRegionEvidence:
        return _capture_rust_region(request).evidence

    def synthesize(self, request: RustRegionRequest) -> dict[str, Any]:
        return synthesize_rust_region(request)

    def optimize(self, request: RustRegionRequest) -> dict[str, Any]:
        return optimize_rust_region(request)


def rust_language_registry() -> LanguageAdapterRegistry:
    registry = LanguageAdapterRegistry()
    registry.register(RustLanguageAdapter())
    return registry


def rust_support_report() -> dict[str, Any]:
    tools: dict[str, dict[str, Any]] = {}
    for name in ("rustc", "cargo", "rustfmt", "alive-tv"):
        path = _optional_tool(name)
        tools[name] = {
            "available": path is not None,
            "path": str(path) if path else None,
            "version": _command([str(path), "--version"]).splitlines()[0] if path else None,
        }
    strict_ready = all(tools[name]["available"] for name in ("rustc", "cargo", "alive-tv"))
    return {
        **rust_language_registry().support_matrix(),
        "status": "pass" if tools["rustc"]["available"] and tools["cargo"]["available"] else "unavailable",
        "strict_proof_ready": strict_ready,
        "tools": tools,
        "semantic_vocabulary": "shared SemanticFlowGraph; language-specific facts are provenance and proof obligations",
    }


def inspect_rust_region(request: RustRegionRequest) -> dict[str, Any]:
    return _capture_rust_region(request).evidence.to_dict()


def isolate_rust_region(request: RustRegionRequest) -> dict[str, Any]:
    context = _capture_rust_region(request)
    output = request.output_directory.resolve()
    report = {
        "schema_version": "vladder-rust-isolation-v1",
        "status": "pass" if context.evidence.status == "supported" else "adapter_required",
        "support": context.evidence.to_dict(),
        "selected_mir": context.mir.to_dict(),
        "kernel_model": context.model.to_dict() if context.model else None,
        "canonical_region": context.canonical_region.to_dict() if context.canonical_region else None,
        "proof_readiness": {
            "mir_semantic_model": context.canonical_region is not None,
            "llvm_artifact": "llvm_ir" in context.artifacts,
            "source_regeneration": context.model is not None and not context.effects.blockers,
        },
        "source_changes_performed": False,
    }
    _write_json(output / "rust-isolation.json", report)
    return report


def synthesize_rust_region(request: RustRegionRequest) -> dict[str, Any]:
    context = _capture_rust_region(request)
    output = request.output_directory.resolve()
    if (
        context.canonical_region is not None
        and context.canonical_region.operation != "count_equal_u8"
        and not context.effects.blockers
    ):
        native = synthesize_canonical_region(context.canonical_region, "rust", output / "canonical-native")
        report = {
            "schema_version": "vladder-rust-synthesis-v2",
            "status": native["status"],
            "support": context.evidence.to_dict(),
            **{key: value for key, value in native.items() if key not in {"schema_version", "status"}},
        }
        _write_json(output / "rust-synthesis.json", report)
        return report
    if context.model is None or context.effects.blockers:
        report = {
            "schema_version": "vladder-rust-synthesis-v1",
            "status": "lowerer_required" if context.evidence.status == "supported" else "adapter_required",
            "support": context.evidence.to_dict(),
            "candidate_count": 0,
            "required_lowerer": (
                context.canonical_region.executable_grammar
                if context.canonical_region is not None else None
            ),
            "claim_boundary": "semantic capture is closed; executable native candidate lowering is an independent capability",
            "source_changes_performed": False,
        }
        _write_json(output / "rust-synthesis.json", report)
        return report

    rustc = _required_tool("rustc")
    rustfmt = _optional_tool("rustfmt")
    alive_tv = _optional_tool("alive-tv")
    edition = str(context.build_identity["edition"])
    overflow_checks = bool(context.build_identity["overflow_checks"])
    workspace_root = Path(str(context.build_identity["workspace_root"]))
    candidates = generate_rust_candidates(context.function, context.model)
    candidate_reports: list[dict[str, Any]] = []
    candidates_root = output / "candidates"
    for candidate in candidates:
        candidate_root = candidates_root / candidate.rule
        candidate_root.mkdir(parents=True, exist_ok=True)
        source_path = candidate_root / "candidate.rs"
        source_path.write_text(candidate.source)
        formatting = rustfmt_source(rustfmt, source_path, edition, cwd=workspace_root)
        formatted_source = source_path.read_text()
        candidate = RustCandidate(
            hashlib.sha256(formatted_source.encode()).hexdigest()[:16],
            candidate.rule,
            candidate.factor,
            candidate.accumulator_banks,
            formatted_source,
            hashlib.sha256(formatted_source.encode()).hexdigest(),
        )
        compiled = compile_rust_library(
            rustc,
            source_path,
            candidate_root / "build",
            crate_name=f"vladder_{candidate.id}",
            edition=edition,
            opt_level=3,
            overflow_checks=overflow_checks,
            cwd=workspace_root,
        )
        mir_validation: dict[str, Any]
        mir_proof: dict[str, Any]
        alive: dict[str, Any]
        if compiled["status"] == "pass":
            mir_validation = validate_candidate_mir(
                candidate, context.function, context.model, Path(str(compiled["mir"])),
                overflow_checks=overflow_checks,
            )
            mir_proof = prove_bounded_mir_equivalence(
                candidate, context.model, candidate_root / "proofs" / "mir-equivalence.smt2",
            )
            proof_unit = build_llvm_refinement_unit(
                context.function,
                candidate,
                context.model.proof_bound,
                candidate_root / "proofs" / "llvm-proof.rs",
            )
            rustfmt_source(rustfmt, Path(proof_unit["source"]), edition, cwd=workspace_root)
            proof_unit["source_sha256"] = file_sha256(Path(proof_unit["source"]))
            proof_compile = compile_rust_library(
                rustc,
                Path(proof_unit["source"]),
                candidate_root / "proofs" / "build",
                crate_name=f"vladder_proof_{candidate.id}",
                edition=edition,
                opt_level=3,
                overflow_checks=overflow_checks,
                cwd=workspace_root,
            )
            alive = (
                run_alive2_refinement(
                    alive_tv,
                    Path(str(proof_compile["llvm_ir"])),
                    candidate_root / "proofs" / "alive2.json",
                )
                if proof_compile["status"] == "pass" else
                {"status": "UNAVAILABLE", "reason": "LLVM proof unit did not compile", "compile": proof_compile}
            )
        else:
            mir_validation = {"status": "FAIL", "reason": "candidate compilation failed"}
            mir_proof = {"status": "NOT_RUN", "reason": "candidate compilation failed"}
            alive = {"status": "NOT_RUN", "reason": "candidate compilation failed"}
        proved = (
            compiled["status"] == "pass"
            and mir_validation.get("status") == "PASS"
            and mir_proof.get("status") == "PASS"
            and alive.get("status") == "PASS"
        )
        item = {
            "candidate": candidate.to_dict(),
            "source": str(source_path),
            "formatting": formatting,
            "compile": compiled,
            "mir_validation": mir_validation,
            "mir_proof": mir_proof,
            "llvm_refinement": alive,
            "llvm_proof_unit": proof_unit if compiled["status"] == "pass" else None,
            "proof_status": "PASS" if proved else "FAIL",
            "application_performed": False,
        }
        _write_json(candidate_root / "candidate.json", item)
        candidate_reports.append(item)

    report = {
        "schema_version": "vladder-rust-synthesis-v1",
        "status": "pass" if candidate_reports else "no_candidates",
        "support": context.evidence.to_dict(),
        "kernel_model": context.model.to_dict(),
        "candidate_count": len(candidate_reports),
        "proved_candidate_count": sum(item["proof_status"] == "PASS" for item in candidate_reports),
        "candidates": candidate_reports,
        "source_changes_performed": False,
        "claim_boundary": "bounded MIR and fixed-length LLVM proof; physical and project promotion are separate",
    }
    _write_json(output / "rust-synthesis.json", report)
    return report


def optimize_rust_region(request: RustRegionRequest) -> dict[str, Any]:
    synthesis = synthesize_rust_region(request)
    output = request.output_directory.resolve()
    if synthesis.get("status") != "pass":
        report = {
            "schema_version": "vladder-rust-optimization-v1",
            "status": "adapter_required",
            "synthesis": synthesis,
            "promotion": {"promotable": False},
        }
        _write_json(output / "rust-optimization.json", report)
        return report
    context = _capture_rust_region(request)
    assert context.model is not None
    rustc = _required_tool("rustc")
    rustfmt = _optional_tool("rustfmt")
    candidates = tuple(
        RustCandidate(**item["candidate"])
        for item in synthesis["candidates"]
    )
    harness_source = output / "benchmark" / "rust_benchmark.rs"
    harness_meta = build_rust_benchmark_harness(context.function, candidates, harness_source)
    rustfmt_source(
        rustfmt,
        harness_source,
        str(context.build_identity["edition"]),
        cwd=Path(str(context.build_identity["workspace_root"])),
    )
    executable = output / "benchmark" / "rust_benchmark"
    compile_report = compile_rust_executable(
        rustc,
        harness_source,
        executable,
        edition=str(context.build_identity["edition"]),
        target_cpu="native",
        overflow_checks=bool(context.build_identity["overflow_checks"]),
        cwd=Path(str(context.build_identity["workspace_root"])),
    )
    if compile_report["status"] != "pass":
        report = {
            "schema_version": "vladder-rust-optimization-v1",
            "status": "benchmark_compile_failed",
            "synthesis": synthesis,
            "benchmark_compile": compile_report,
            "promotion": {"promotable": False},
        }
        _write_json(output / "rust-optimization.json", report)
        return report
    verify = subprocess.run([str(executable), "verify"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if verify.returncode != 0:
        report = {
            "schema_version": "vladder-rust-optimization-v1",
            "status": "differential_failed",
            "synthesis": synthesis,
            "benchmark_compile": compile_report,
            "differential": {"return_code": verify.returncode, "stdout": verify.stdout, "stderr": verify.stderr},
            "promotion": {"promotable": False},
        }
        _write_json(output / "rust-optimization.json", report)
        return report

    proof_by_id = {
        item["candidate"]["id"]: item for item in synthesis["candidates"]
    }
    measurements: list[dict[str, Any]] = []
    benchmark_cpu = _available_cpu(request.cpu)
    for candidate in candidates:
        manifest = {
            "executable": str(executable),
            "baseline_args": ["baseline"],
            "candidate_args": [candidate.rule],
            "cwd": str(output / "benchmark"),
            "environment": {
                "VLADDER_N": str(request.benchmark_elements),
                "VLADDER_INNER": str(request.benchmark_inner),
            },
            "processes": request.benchmark_processes,
            "repetitions_per_process": request.benchmark_repetitions,
            "metric_key": "metric_ns",
            "observable_key": "observable",
            "exact_observables": True,
            "direction": "lower",
            "minimum_effect_percent": request.minimum_speedup_pct,
            "bootstrap_rounds": 2000,
            "seed": int(candidate.id[:8], 16),
            "cpu": benchmark_cpu,
            "candidate_identity": candidate.id,
        }
        manifest_path = output / "benchmark" / f"paired-{candidate.id}.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True))
        physical = run_paired_benchmark(manifest_path, output / "benchmark" / candidate.id)
        proof = proof_by_id[candidate.id]
        strict_proof = proof["proof_status"] == "PASS"
        promoted = strict_proof and physical["promotable_physical_evidence"]
        measurements.append({
            "candidate": candidate.to_dict(),
            "strict_proof": strict_proof,
            "physical": physical,
            "classification": "verified_regional_win" if promoted else "unproved" if not strict_proof else physical["classification"],
            "promotable": promoted,
        })
    promotable = [item for item in measurements if item["promotable"]]
    promotable.sort(key=lambda item: item["physical"]["paired_effect_percent"], reverse=True)
    winner = promotable[0] if promotable else None
    patch_path: str | None = None
    optimized_path: str | None = None
    if winner:
        candidate = next(value for value in candidates if value.id == winner["candidate"]["id"])
        optimized = output / "optimized.rs"
        optimized.write_text(candidate.source)
        optimized_path = str(optimized)
        patch = output / "optimized.patch"
        patch.write_text(_source_patch(context.function, candidate.source, request.source))
        patch_path = str(patch)
    report = {
        "schema_version": "vladder-rust-optimization-v1",
        "status": "pass",
        "support": context.evidence.to_dict(),
        "synthesis_report": str(output / "rust-synthesis.json"),
        "benchmark_harness": harness_meta,
        "benchmark_compile": compile_report,
        "differential": {"status": "PASS", "stdout": verify.stdout.strip()},
        "measurements": measurements,
        "winner": winner,
        "optimized_source": optimized_path,
        "optimized_patch": patch_path,
        "promotion": {
            "promotable": winner is not None,
            "minimum_speedup_percent": request.minimum_speedup_pct,
            "requires_project_integration": True,
            "source_applied": False,
        },
        "claim_boundary": "best verified local Rust R1 realization on this hardware; project tests and end-to-end confirmation remain required",
    }
    _write_json(output / "rust-optimization.json", report)
    return report


def audit_rust_regions(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("regions"), list):
        raise ValueError("Rust audit manifest requires a regions list")
    reports: list[dict[str, Any]] = []
    for index, item in enumerate(raw["regions"]):
        if not isinstance(item, dict):
            raise ValueError(f"Rust audit region {index} must be a mapping")
        cargo_manifest = Path(str(item["manifest_path"]))
        source = Path(str(item["source"]))
        request = RustRegionRequest(
            manifest_path=cargo_manifest if cargo_manifest.is_absolute() else manifest_path.parent / cargo_manifest,
            source=source if source.is_absolute() else manifest_path.parent / source,
            function=str(item["function"]),
            package=str(item["package"]) if item.get("package") else None,
            target_kind=str(item.get("target_kind", "lib")),
            target_name=str(item["target_name"]) if item.get("target_name") else None,
            profile=str(item.get("profile", "release")),
            features=tuple(str(value) for value in item.get("features", [])),
            proof_bound=int(item.get("proof_bound", 32)),
            output_directory=output_directory / f"region-{index:03d}",
        )
        region_report = inspect_rust_region(request)
        region_report["id"] = str(item.get("id", f"region-{index:03d}"))
        reports.append(region_report)
    report = {
        "schema_version": "vladder-rust-audit-v1",
        "status": "pass",
        "region_count": len(reports),
        "supported_count": sum(item["status"] == "supported" for item in reports),
        "regions": reports,
        "optimization_performed": False,
        "source_changes_performed": False,
    }
    _write_json(output_directory / "rust-audit.json", report)
    return report


def _capture_rust_region(request: RustRegionRequest) -> RustCaptureContext:
    output = request.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = request.source.resolve()
    manifest = request.manifest_path.resolve()
    if not source.exists() or not manifest.exists():
        raise ValueError("Rust source and Cargo manifest must exist")
    metadata = _cargo_metadata(manifest)
    package = _select_package(metadata, manifest, request.package)
    target = _select_target(package, request.target_kind, request.target_name)
    rustc = _required_tool("rustc")
    cargo = _required_tool("cargo")
    workspace_root = Path(str(metadata["workspace_root"]))
    rustc_verbose = _command([str(rustc), "--version", "--verbose"], cwd=workspace_root)
    cargo_version = _command([str(cargo), "--version"], cwd=workspace_root)
    edition = str(target.get("edition") or package.get("edition") or "2021")
    profile_settings = _profile_settings(manifest, workspace_root, request.profile)
    overflow_checks = bool(profile_settings["overflow_checks"])
    capture_root = output / "capture"
    cargo_target = capture_root / "cargo-target"
    command = [
        str(cargo), "rustc", "--manifest-path", str(manifest), "--package", str(package["name"]),
        "--target-dir", str(cargo_target),
    ]
    if request.profile == "release":
        command.append("--release")
    else:
        command.extend(("--profile", request.profile))
    command.extend(_target_arguments(request.target_kind, str(target["name"])))
    if request.features:
        command.extend(("--features", ",".join(request.features)))
    lockfile = Path(str(metadata["workspace_root"])) / "Cargo.lock"
    if lockfile.exists():
        command.append("--locked")
    command.extend((
        "--", "--emit=mir,llvm-ir,asm", "-C", "codegen-units=1", "-C", "target-cpu=native", "-C", "debuginfo=1",
        "-C", f"overflow-checks={'yes' if overflow_checks else 'no'}",
    ))
    completed = subprocess.run(
        command,
        cwd=Path(str(metadata["workspace_root"])),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"cargo rustc capture failed:\n{completed.stderr[-4000:]}")
    profile_directory = "release" if request.profile == "release" else request.profile
    deps = cargo_target / profile_directory / "deps"
    crate_stem = str(target["name"]).replace("-", "_")
    emitted = {
        "mir": _select_emitted(deps, crate_stem, ".mir"),
        "llvm_ir": _select_emitted(deps, crate_stem, ".ll"),
        "assembly": _select_emitted(deps, crate_stem, ".s"),
    }
    artifacts: dict[str, str] = {}
    for name, path in emitted.items():
        destination = capture_root / f"target.{path.suffix.lstrip('.')}"
        shutil.copy2(path, destination)
        artifacts[name] = str(destination)
    artifacts["source"] = str(source)
    _write_json(capture_root / "cargo-metadata.json", metadata)
    (capture_root / "cargo-rustc.stdout.txt").write_text(completed.stdout)
    (capture_root / "cargo-rustc.stderr.txt").write_text(completed.stderr)
    text = source.read_text()
    function = extract_rust_function(text, request.function)
    effects = classify_rust_effects(function)
    mir_text = Path(artifacts["mir"]).read_text()
    all_mir = parse_mir_functions(mir_text)
    selected_mir = select_mir_function(all_mir, request.function)
    model = infer_rust_kernel_model(
        function,
        selected_mir,
        all_mir,
        overflow_checks=overflow_checks,
        proof_bound=request.proof_bound,
    )
    blockers = list(effects.blockers)
    canonical_region: CanonicalBoundedRegion | None = None
    try:
        canonical_region = classify_canonical_region("rust", function.source, function.signature)
    except CanonicalRegionError as error:
        blockers.append(error.to_blocker())
    rustc_identity = canonical_hash({"version": rustc_verbose, "path": str(rustc)})
    graph = None
    corroboration = None
    if canonical_region is not None:
        llvm_text = Path(artifacts["llvm_ir"]).read_text(errors="replace")
        corroboration = corroborate_compiler_shape(canonical_region, (selected_mir.body, llvm_text))
        if corroboration["status"] != "pass":
            blockers.append({
                "kind": "compiler-shape-mismatch",
                "reason": f"selected MIR/LLVM lacks canonical signals: {corroboration['missing_signals']}",
                "required_adapter": "capture the correct monomorphized instance or add a typed compiler-IR recognizer",
            })
        elif model is not None:
            graph = build_semantic_flow_graph(function, model, selected_mir, rustc_identity)
            graph = replace(
                graph,
                contracts={
                    **graph.contracts,
                    "canonical_region": canonical_region.to_dict(),
                    "compiler_corroboration": corroboration,
                },
                graph_hash="",
            )
        else:
            graph = build_canonical_graph(
                canonical_region,
                name=request.function,
                language="rust",
                compiler_identity=rustc_identity,
                semantic_ir="rustc MIR + LLVM IR",
                function_identity=f"{source}:{request.function}",
                source_provenance={
                    "source": str(source), "source_sha256": file_sha256(source),
                    "function": request.function, "mir_sha256": selected_mir.sha256,
                },
                language_contracts={
                    "ownership": [parameter.ownership for parameter in function.parameters],
                    "panic_strategy": profile_settings["panic"],
                    "overflow_checks": overflow_checks,
                    "monomorphic": effects.monomorphic,
                },
                compiler_corroboration=corroboration,
                excluded_claims=(
                    "unsafe and custom Drop behavior",
                    "async, atomics, FFI, allocation, and external effects",
                    "candidate equivalence until a family lowerer and proof unit execute",
                ),
            )
    build_identity = {
        "manifest_path": str(manifest),
        "manifest_sha256": file_sha256(manifest),
        "lockfile": str(lockfile) if lockfile.exists() else None,
        "lockfile_sha256": file_sha256(lockfile) if lockfile.exists() else None,
        "workspace_root": str(metadata["workspace_root"]),
        "cargo_configuration": _configuration_identity(workspace_root),
        "package": package["name"],
        "package_version": package["version"],
        "target_kind": request.target_kind,
        "target_name": target["name"],
        "edition": edition,
        "profile": request.profile,
        "features": list(request.features),
        "overflow_checks": overflow_checks,
        "target_triple": _rustc_field(rustc_verbose, "host") or platform.machine(),
        "panic_strategy": profile_settings["panic"],
        "profile_settings": profile_settings,
        "rust_environment": {
            name: os.environ.get(name)
            for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER")
            if os.environ.get(name) is not None
        },
        "mir_parser_compatibility": "structural-v1 with selected-operation fail-closed validation",
        "rustc": str(rustc),
        "rustc_verbose": rustc_verbose,
        "rustc_identity": rustc_identity,
        "cargo": str(cargo),
        "cargo_version": cargo_version.splitlines()[0] if cargo_version else "unknown",
        "capture_command": command,
        "source_sha256": file_sha256(source),
        "function_sha256": function.function_sha256,
        "artifact_hashes": {name: file_sha256(Path(path)) for name, path in artifacts.items() if name != "source"},
        "canonical_region": canonical_region.to_dict() if canonical_region else None,
        "compiler_corroboration": corroboration,
    }
    compositional_summary = rust_function_summary(
        function,
        effects,
        rustc_identity,
        semantic_graph_hash=graph.graph_hash if graph else "",
        blockers=tuple(blockers),
    ).to_dict()
    build_identity["compositional_summary"] = compositional_summary
    executable = model is not None and not blockers
    capabilities = _rust_capabilities(bool(graph), not blockers, executable, artifacts)
    status = "supported" if graph is not None and not blockers else "local_graph_only" if graph is not None else "adapter_required"
    evidence = LanguageRegionEvidence(
        LANGUAGE_ADAPTER_PROTOCOL_VERSION,
        RustLanguageAdapter.name,
        "rust",
        RUST_SUPPORT_VERSION,
        request.function,
        status,
        capabilities,
        graph,
        build_identity,
        tuple(blockers),
        artifacts,
        "proof covers only the recognized safe monomorphic R1 region under the recorded rustc/Cargo contract",
    )
    _write_json(output / "rust-support.json", evidence.to_dict())
    _write_json(output / "rust-effects.json", effects.to_dict())
    _write_json(output / "rust-build.json", build_identity)
    _write_json(output / "compositional-summary.json", compositional_summary)
    _write_json(output / "selected-mir.json", selected_mir.to_dict())
    if canonical_region:
        _write_json(output / "canonical-region.json", canonical_region.to_dict())
    if graph:
        _write_json(output / "rust-flow.json", graph.to_dict())
    return RustCaptureContext(request, function, effects, selected_mir, all_mir, model, canonical_region, build_identity, artifacts, evidence)


def _rust_capabilities(graph: bool, closed: bool, executable: bool, artifacts: dict[str, str]) -> dict[str, LanguageCapability]:
    return {
        "semantic_capture": LanguageCapability(True, True, "source, Cargo, MIR, LLVM IR, and assembly captured", artifacts.get("mir")),
        "closure": LanguageCapability(True, closed, "canonical bounded effect and operation closure" if closed else "one or more semantic adapters remain"),
        "candidate_generation": LanguageCapability(executable, False, "exact reduction lowerer available" if executable else "semantic graph closed; native family lowerer required"),
        "semantic_proof": LanguageCapability(executable, False, "bounded MIR-derived Z3 proof per lowered candidate"),
        "backend_refinement": LanguageCapability(executable, False, "fixed-bound LLVM refinement through Alive2"),
        "differential_execution": LanguageCapability(executable, False, "generated adversarial Rust harness after lowering"),
        "physical_benchmark": LanguageCapability(executable, False, "same-executable paired process benchmark after lowering"),
        "source_rewrite": LanguageCapability(executable, False, "native Rust candidate source and patch after proof; never auto-applied"),
        "protocol_equivalence": LanguageCapability(False, False, "unsafe, Drop, async, concurrency, FFI, and external protocols are excluded"),
    }


def _cargo_metadata(manifest: Path) -> dict[str, Any]:
    cargo = _required_tool("cargo")
    command = [
        str(cargo), "metadata", "--format-version", "1", "--no-deps",
        "--manifest-path", str(manifest),
    ]
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    if completed.returncode != 0:
        raise RuntimeError(f"cargo metadata failed:\n{completed.stderr[-4000:]}")
    return json.loads(completed.stdout)


def _select_package(metadata: dict[str, Any], manifest: Path, requested: str | None) -> dict[str, Any]:
    packages = metadata.get("packages") or []
    if requested:
        matches = [item for item in packages if item.get("name") == requested or item.get("id") == requested]
    else:
        matches = [item for item in packages if Path(str(item.get("manifest_path", ""))).resolve() == manifest]
    if len(matches) != 1:
        raise ValueError(f"Cargo package selection is ambiguous or absent: {[item.get('name') for item in matches]}")
    return matches[0]


def _select_target(package: dict[str, Any], kind: str, requested: str | None) -> dict[str, Any]:
    targets = package.get("targets") or []
    matches = [item for item in targets if kind in item.get("kind", [])]
    if requested:
        matches = [item for item in matches if item.get("name") == requested]
    if len(matches) != 1:
        raise ValueError(f"Cargo target selection is ambiguous or absent: {[item.get('name') for item in matches]}")
    return matches[0]


def _target_arguments(kind: str, name: str) -> list[str]:
    if kind == "lib":
        return ["--lib"]
    if kind in {"bin", "example", "test", "bench"}:
        return [f"--{kind}", name]
    raise ValueError(f"unsupported Cargo target kind: {kind}")


def _select_emitted(directory: Path, crate_stem: str, suffix: str) -> Path:
    values = sorted(directory.glob(f"{crate_stem}-*{suffix}"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    if not values:
        values = sorted(directory.glob(f"*{suffix}"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    if not values:
        raise RuntimeError(f"cargo rustc emitted no {suffix} artifact under {directory}")
    return values[0]


def _profile_settings(manifest: Path, workspace_root: Path, profile: str) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python 3.10
        import tomli as tomllib

    values: dict[str, Any] = {}
    roots = [workspace_root / "Cargo.toml", manifest]
    for path in dict.fromkeys(path.resolve() for path in roots):
        if not path.exists():
            continue
        raw = tomllib.loads(path.read_text())
        values.update((raw.get("profile") or {}).get(profile) or {})
    return {
        "overflow_checks": bool(values.get("overflow-checks", profile not in {"release", "bench"})),
        "panic": str(values.get("panic", "unwind")),
        "opt_level": values.get("opt-level", 3 if profile in {"release", "bench"} else 0),
        "lto": values.get("lto", False),
        "debug": values.get("debug", False),
        "codegen_units": values.get("codegen-units", 16 if profile == "release" else 256),
        "incremental": values.get("incremental", profile not in {"release", "bench"}),
    }


def _required_tool(name: str) -> Path:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required Rust adapter tool is unavailable: {name}")
    return Path(path)


def _optional_tool(name: str) -> Path | None:
    path = shutil.which(name)
    return Path(path) if path else None


def _command(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{completed.stderr}")
    return completed.stdout + completed.stderr


def _configuration_identity(workspace_root: Path) -> list[dict[str, str]]:
    candidates: list[Path] = []
    for root in (workspace_root, *workspace_root.parents):
        candidates.extend((root / ".cargo" / "config.toml", root / ".cargo" / "config"))
        candidates.extend((root / "rust-toolchain.toml", root / "rust-toolchain"))
    cargo_home = Path(os.environ.get("CARGO_HOME", str(Path.home() / ".cargo")))
    candidates.extend((cargo_home / "config.toml", cargo_home / "config"))
    return [
        {"path": str(path), "sha256": file_sha256(path)}
        for path in dict.fromkeys(path.resolve() for path in candidates)
        if path.exists() and path.is_file()
    ]


def _rustc_field(verbose: str, field: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(field)}:\s*(.+)$", verbose)
    return match.group(1).strip() if match else None


def _available_cpu(requested: int | None) -> int | None:
    if not hasattr(os, "sched_getaffinity"):
        return requested
    allowed = sorted(os.sched_getaffinity(0))
    if not allowed:
        return None
    return requested if requested in allowed else allowed[0]


def _source_patch(function: RustFunction, candidate_source: str, source_path: Path) -> str:
    import difflib

    original = source_path.read_text()
    generated_name = re.search(r"\bfn\s+(candidate_[A-Za-z0-9_]+)\b", candidate_source)
    if not generated_name:
        raise ValueError("generated Rust candidate has no candidate function name")
    realized = candidate_source.replace(generated_name.group(1), function.source_name, 1)
    replacement = original[: function.start_offset] + realized + original[function.end_offset :]
    return "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        replacement.splitlines(keepends=True),
        fromfile=f"a/{source_path.name}",
        tofile=f"b/{source_path.name}",
    ))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
