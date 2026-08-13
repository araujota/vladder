from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .report import write_json
from .toolchain import alive2_check, discover_toolchain, run


CPP_CLOSURE_SCHEMA = "vladder-cpp-closure-v1"


def _sha256(value: str | bytes) -> str:
    payload = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _scope(adapter: dict[str, Any]) -> dict[str, Any]:
    kind = str(adapter.get("kind", "unknown-adapter"))
    categories = {
        "exception-adapter": "exception_and_destructor_protocol",
        "ownership-lifetime-adapter": "ownership_allocation_and_retirement",
        "object-state-adapter": "class_state_and_invariant",
        "memory-order-adapter": "concurrency_and_memory_order",
        "external-call-adapter": "external_api_or_callback",
        "abi-adapter": "unmodeled_source_abi",
        "function-extraction-adapter": "source_or_symbol_selection",
        "overload-selection-adapter": "source_or_symbol_selection",
        "compile-command-selection-adapter": "source_or_symbol_selection",
        "source-lowering-adapter": "source_realization",
    }
    category = categories.get(kind, "bounded_semantic_adapter")
    categorical = category in {
        "exception_and_destructor_protocol",
        "ownership_allocation_and_retirement",
        "concurrency_and_memory_order",
        "external_api_or_callback",
    }
    procedural = category == "source_or_symbol_selection"
    return {
        "kind": kind,
        "category": category,
        "evidence": adapter.get("reason"),
        "blocked_claim": (
            "generic whole-function C++ refinement and automatic repository promotion"
            if categorical else "automatic transformation for the selected boundary"
        ),
        "required_adapter": adapter.get("required_boundary"),
        "next_workflow": adapter.get("next_workflow"),
        "categorical_for_generic_ingestion": categorical,
        "automatic_status": (
            "not_generically_modelable" if categorical else
            "resolvable_by_selection" if procedural else
            "requires_explicit_bounded_contract"
        ),
        "empirical_boundary": (
            "the selected function crosses a semantic protocol whose state space and observables are not present in local LLVM IR"
            if categorical else
            "the selected boundary needs a finite ABI, state, or source-realization adapter before transformation"
        ),
        "whole_function_consequence": (
            "generic whole-function equivalence is unavailable" if categorical else
            "automatic transformation is unavailable until the named adapter is supplied"
        ),
        "local_region_consequence": "independent local regions remain eligible when their live-ins, live-outs, and effects close locally",
        "does_not_block": [
            "compiled-code attribution",
            "lifetime and placement analysis",
            "independently isolated local regions",
            "project benchmark adapters",
            "manually contracted domain verification",
        ],
    }


def _capsulable(region: dict[str, Any], tier: str) -> tuple[bool, list[str]]:
    hazards = set(region.get("hard_hazards", []))
    permitted = {"object_state"} if tier == "bounded_state_transition" else set()
    remaining = sorted(hazards - permitted)
    if region.get("escaping_control") and region.get("closure_mode") != "whole_function_cfg":
        remaining.append("escaping_control")
    return not remaining, remaining


def _region_blocker(kind: str) -> dict[str, Any]:
    descriptions = {
        "escaping_control": (
            "control transfer leaves the candidate loop",
            "a CFG region extractor with explicit multi-exit live-outs",
        ),
        "exception": ("the region can throw or unwind", "a bounded exception and destructor contract"),
        "allocation": ("the region changes ownership or allocation state", "an ownership/capacity/retirement model"),
        "memory_order": ("the region performs synchronization or volatile access", "a C++ memory-order protocol model"),
        "runtime_control": ("the region uses assembly or coroutine runtime control", "a specialized runtime adapter"),
        "object_state": ("the region accesses object state outside an admitted state tier", "an explicit finite state projection"),
        "external_call": ("the region retains an unmodeled helper or external call", "an inlined helper or explicit call summary"),
        "capacity_mutation": ("the region may change container capacity or ownership", "a bounded capacity, allocation, and exception contract"),
        "source_range": ("the region has macro-origin or out-of-definition source coordinates", "a macro-aware Clang refactoring adapter"),
    }
    evidence, required = descriptions.get(kind, ("the region is not locally closed", "a specialized bounded region adapter"))
    return {
        "kind": kind,
        "evidence": evidence,
        "blocked_claim": "automatic lambda-capsule isolation for this source region",
        "required_adapter": required,
        "whole_function_blocked": False,
        "permitted_continuation": [
            "owning-function attribution",
            "other independently closed subregions",
            "explicit CFG or protocol adapter",
        ],
    }


def classify_cpp_closure(report: dict[str, Any]) -> dict[str, Any]:
    tier = str(report.get("support_tier", "unselected"))
    scopes = [_scope(item) for item in report.get("adapters", [])]
    regions = []
    for region in report.get("subregions", []):
        eligible, blockers = _capsulable(region, tier)
        regions.append({
            "id": region.get("id"),
            "eligible": eligible,
            "schedule_eligible": bool(region.get("schedule_hint_eligible")),
            "blockers": blockers,
            "blocker_details": [_region_blocker(item) for item in blockers],
            "disposition": (
                "whole_function_cfg" if eligible and region.get("closure_mode") == "whole_function_cfg" else
                "no_growth_container_capsule" if eligible and region.get("closure_mode") == "no_growth_container" else
                "effect_preserving_schedule" if region.get("schedule_hint_eligible") and region.get("closure_mode") == "effect_preserving_schedule" else
                "automatic_capsule" if eligible else "region_adapter_required"
            ),
            "isolation_mode": region.get("closure_mode", "lambda_capsule"),
            "classification": region.get("classification"),
            "source_range": region.get("source_range"),
        })
    eligible_regions = [item for item in regions if item["eligible"]]
    schedule_regions = [item for item in regions if item["schedule_eligible"]]
    semantic_capture = bool(
        report.get("selection") and report.get("production_ir") and report.get("information_flow")
    )
    whole_local = tier in {"whole_function_local_ir", "bounded_state_transition"}
    canonical = tier == "canonical_source_transform"
    nested = bool(eligible_regions)
    isolation_predicted = canonical or whole_local or nested
    candidate_predicted = canonical or bool(schedule_regions)
    if canonical:
        disposition = "automatic"
    elif whole_local and nested:
        disposition = "contract_bounded" if tier == "bounded_state_transition" else "automatic_with_benchmark_adapter"
    elif whole_local:
        disposition = "contract_bounded" if tier == "bounded_state_transition" else "proof_unit_only"
    elif nested:
        disposition = "local_regions_only"
    elif schedule_regions:
        disposition = "effect_preserving_schedule_only"
    elif report.get("selection") is None:
        disposition = "unresolved_selection"
    else:
        disposition = "external_protocol_only"
    return {
        "schema_version": CPP_CLOSURE_SCHEMA,
        "disposition": disposition,
        "capabilities": {
            "semantic_capture": {
                "ready": semantic_capture, "actual": semantic_capture,
                "scope": "selected build and declared contract",
            },
            "isolation": {"ready": isolation_predicted, "actual": False, "kind": "canonical" if canonical else "predicted"},
            "candidate_generation": {
                "ready": candidate_predicted,
                "actual": False,
                "grammar": "bounded-cfg-and-loop-schedule-v3" if schedule_regions else None,
                "claim_boundary": (
                    "schedule directives preserve the owning source and compiler legality; "
                    "they do not close callback, ownership, exception, or protocol semantics"
                    if schedule_regions and not nested else "closed local region"
                ),
            },
            "local_proof": {"ready": isolation_predicted, "actual": False, "method": "canonical IR identity plus typed obligations"},
            "benchmark": {"ready": canonical, "actual": canonical, "adapter_required": not canonical},
            "source_rewrite": {"ready": canonical or bool(schedule_regions), "actual": canonical, "application_performed": False},
            "protocol_equivalence": {
                "ready": not scopes,
                "actual": False,
                "scope": "whole selected C++ boundary",
            },
        },
        "regions": regions,
        "protocol_scopes": scopes,
        "claim_boundary": (
            "local proof units may be optimized independently; protocol scopes remain outside generic equivalence"
            if isolation_predicted else
            "no automatically isolatable proof unit was found; attribution and explicitly modeled workflows remain available"
        ),
        "global_workflow_blocked": False,
    }


def _defined_symbols(text: str) -> set[str]:
    symbols: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("define "):
            continue
        match = re.search(r'@(?:"([^"]+)"|([^\s(]+))\(', line)
        if match:
            symbols.add(match.group(1) or match.group(2))
    return symbols


def _extract_function(text: str, symbol: str, replacement: str) -> str:
    escaped = re.escape(symbol)
    match = re.search(rf'^define\s+.*@(?:"{escaped}"|{escaped})\([^\n]*\).*\{{\s*$', text, re.MULTILINE)
    if not match:
        raise ValueError(f"proof symbol {symbol!r} is absent from emitted IR")
    opening = text.find("{", match.start(), match.end())
    depth = 0
    end = None
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError(f"proof symbol {symbol!r} has an unterminated body")
    body = text[match.start():end]
    body = re.sub(rf'@(?:"{escaped}"|{escaped})\(', f"@{replacement}(", body, count=1)
    body = re.sub(r",\s*![A-Za-z0-9_.]+\s+![0-9]+", "", body)
    body = re.sub(r"\s+![A-Za-z0-9_.]+\s+![0-9]+", "", body)
    body = re.sub(r"\s+#[0-9]+(?=\s*(?:align\s+\d+\s*)?\{)", " ", body)
    return body + "\n"


def _pair_ir(reference: str, candidate: str, path: Path) -> None:
    path.write_text(reference.rstrip() + "\n\n" + candidate.rstrip() + "\n")


def _compile_ir(
    semantic_arguments: list[str], directory: Path, original: Path, generated: Path, output: Path
) -> dict[str, Any]:
    tc = discover_toolchain()
    flags = [
        *semantic_arguments,
        "-iquote", str(original.parent),
        "-O1", "-fno-vectorize", "-fno-slp-vectorize", "-fno-unroll-loops",
        "-S", "-emit-llvm", str(generated), "-o", str(output),
    ]
    result = run([tc.compiler, *flags], cwd=directory, timeout=240)
    return {
        "status": "pass" if result.returncode == 0 else "fail",
        "returncode": result.returncode,
        "stderr": result.stderr[-4000:],
        "ir": str(output),
        "ir_sha256": _sha256(output.read_bytes()) if output.exists() else None,
        "flags_sha256": _sha256(json.dumps(flags, sort_keys=True)),
    }


_SCHEDULE_VARIANTS = (
    ("unroll-2", "loop-unroll-schedule", "unroll_count(2)", 2),
    ("unroll-4", "loop-unroll-schedule", "unroll_count(4)", 4),
    ("vector-width-2", "loop-vector-width", "vectorize(enable) vectorize_width(2)", 2),
    ("vector-width-4", "loop-vector-width", "vectorize(enable) vectorize_width(4)", 4),
    ("vector-width-8", "loop-vector-width", "vectorize(enable) vectorize_width(8)", 8),
    ("interleave-2", "loop-interleave-schedule", "interleave_count(2)", 2),
    ("interleave-4", "loop-interleave-schedule", "interleave_count(4)", 4),
)


def cpp_schedule_variants() -> tuple[dict[str, Any], ...]:
    return tuple({
        "choice": choice,
        "schedule_family": family,
        "directive": directive,
        "factor": factor,
    } for choice, family, directive, factor in _SCHEDULE_VARIANTS)


def _wrap_loop(source: str, source_range: list[int], directive: str | None = None) -> str:
    begin, end = (int(source_range[0]), int(source_range[1]))
    loop = source[begin:end]
    if directive is not None:
        directive_text = (
            "#if defined(__clang__) && !defined(VLADDER_CPP_PROOF)\n"
            f"#pragma clang loop {directive}\n"
            "#endif\n"
        )
    else:
        directive_text = ""
    replacement = "[&]() __attribute__((noinline)) {\n" + directive_text + loop + "\n}();"
    return source[:begin] + replacement + source[end:]


def _direct_hint(source: str, source_range: list[int], directive: str) -> str:
    begin = int(source_range[0])
    line_prefix = "" if begin == 0 or source[begin - 1] == "\n" else "\n"
    directive = line_prefix + (
        "#if defined(__clang__) && !defined(VLADDER_CPP_PROOF)\n"
        f"#pragma clang loop {directive}\n"
        "#endif\n"
    )
    return source[:begin] + directive + source[begin:]


def _schedule_proof(out_dir: Path, choice: str, factor: int) -> dict[str, Any]:
    path = out_dir / f"{choice}.smt2"
    try:
        import z3
    except ImportError:
        path.write_text("; z3 unavailable\n")
        return {"status": "UNAVAILABLE", "method": "z3", "artifact": str(path)}
    n, k = z3.Ints("n k")
    q, r = z3.Ints("q r")
    solver = z3.Solver()
    solver.add(n >= 0, k >= 0, k < n, q == k / factor, r == k % factor)
    solver.add(z3.Not(z3.And(r >= 0, r < factor, q * factor + r == k)))
    result = solver.check()
    path.write_text(
        "; Counterexample query: every logical iteration has one block/lane decomposition\n"
        + solver.to_smt2()
    )
    return {
        "status": "PROVED" if result == z3.unsat else "FAILED",
        "method": "z3-int",
        "factor": factor,
        "choice": choice,
        "result": str(result),
        "artifact": str(path),
        "scope": "iteration coverage only; the proof-source IR identity establishes unchanged loop-body semantics",
    }


def materialize_cpp_schedule_candidate(
    report: dict[str, Any],
    source: Path,
    semantic_arguments: list[str],
    directory: Path,
    region_id: str,
    choice: str,
    out_dir: Path,
) -> dict[str, Any]:
    """Materialize exactly one selected-build schedule action after policy expansion."""
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / "candidate.json"
    if artifact.is_file():
        cached = json.loads(artifact.read_text())
        if cached.get("source_sha256") and Path(str(cached.get("repository_candidate_source"))).is_file():
            return cached
    source = source.resolve()
    source_text = source.read_text()
    if report.get("source_sha256") != _sha256(source_text):
        raise ValueError("selected-build source changed after semantic capture")
    closure = classify_cpp_closure(report)
    region = next(
        (
            item for item in closure["regions"]
            if item.get("id") == region_id
            and (item.get("eligible") or item.get("schedule_eligible"))
        ),
        None,
    )
    if region is None:
        raise ValueError(f"selected-build region is absent or ineligible: {region_id}")
    variant = next((item for item in _SCHEDULE_VARIANTS if item[0] == choice), None)
    if variant is None:
        raise ValueError(f"unknown selected-build schedule choice: {choice}")
    _, schedule_family, directive, factor = variant
    insertion = int(region["source_range"][0])
    line_prefix = "" if insertion == 0 or source_text[insertion - 1] == "\n" else "\n"
    guarded_directive = line_prefix + (
        "#if defined(__clang__) && !defined(VLADDER_CPP_PROOF)\n"
        f"#pragma clang loop {directive}\n"
        "#endif\n"
    )
    baseline_evidence_path = out_dir.parent / "baseline-evidence.json"
    if baseline_evidence_path.is_file():
        baseline_evidence = json.loads(baseline_evidence_path.read_text())
    elif region.get("isolation_mode") in {"whole_function_cfg", "effect_preserving_schedule"}:
        unit = _whole_function_unit(report, out_dir.parent)
        baseline_evidence = {
            "kind": str(region.get("isolation_mode")),
            "identity": unit.get("proof", {}),
        }
        write_json(baseline_evidence_path, baseline_evidence)
    else:
        baseline_module = Path(report["production_ir"]["analysis_ir"])
        baseline_symbols = _defined_symbols(baseline_module.read_text(errors="replace"))
        baseline_source = out_dir.parent / "capsule-baseline.cpp"
        baseline_source.write_text(_wrap_loop(source_text, region["source_range"]))
        baseline_ir = out_dir.parent / "capsule-baseline.ll"
        compiled = _compile_ir(semantic_arguments, directory, source, baseline_source, baseline_ir)
        if compiled["status"] != "pass":
            raise ValueError(f"selected-build baseline capsule failed to compile: {region_id}")
        added = sorted(_defined_symbols(baseline_ir.read_text(errors="replace")) - baseline_symbols)
        lambda_symbols = [item for item in added if "clEv" in item or "$_" in item]
        if len(lambda_symbols) != 1:
            raise ValueError(f"selected-build baseline capsule symbol is ambiguous: {region_id}")
        reference = _extract_function(
            baseline_ir.read_text(errors="replace"), lambda_symbols[0], "transform_ref",
        )
        pair = out_dir.parent / "capsule.identity.ll"
        _pair_ir(reference, reference.replace("@transform_ref(", "@transform_candidate(", 1), pair)
        identity = alive2_check(
            discover_toolchain(), pair, out_dir.parent / "alive2", "capsule-identity",
        )
        baseline_evidence = {
            "kind": "lambda_capsule",
            "identity": identity,
            "proof_source": str(baseline_source),
        }
        write_json(baseline_evidence_path, baseline_evidence)

    identity = baseline_evidence.get("identity", {})
    whole_cfg = region.get("isolation_mode") in {"whole_function_cfg", "effect_preserving_schedule"}
    effect_preserving = region.get("isolation_mode") == "effect_preserving_schedule"
    candidate_source = out_dir / f"source-{choice}.cpp"
    candidate_source.write_text(_direct_hint(source_text, region["source_range"], directive))
    physical_source = candidate_source
    if not whole_cfg:
        physical_source = out_dir / f"capsule-{choice}.cpp"
        physical_source.write_text(_wrap_loop(source_text, region["source_range"], directive))
    physical_ir = out_dir / f"candidate-{choice}.ll"
    candidate_compile = _compile_ir(
        semantic_arguments, directory, source, physical_source, physical_ir,
    )
    syntax = run(
        [discover_toolchain().compiler, *semantic_arguments, "-iquote", str(source.parent),
         "-fsyntax-only", str(candidate_source)],
        cwd=directory,
        timeout=240,
    )
    schedule = _schedule_proof(out_dir, choice, factor)
    proof_passed = (
        schedule["status"] == "PROVED"
        and identity.get("status") == "correct"
        and syntax.returncode == 0
        and candidate_compile["status"] == "pass"
    )
    candidate = {
        "id": f"{region_id}-{'cfg-' if whole_cfg else ''}{choice}",
        "region_id": region_id,
        "schedule_choice": choice,
        "schedule_family": schedule_family,
        "grammar": "bounded-cfg-and-loop-schedule-v3" if whole_cfg else "typed-loop-schedule-v2",
        "rule": (
            "effect-preserving-owning-loop-schedule-hint" if effect_preserving else
            "whole-function-clang-loop-schedule-hint" if whole_cfg else
            "clang-loop-schedule-hint"
        ),
        "factor": factor,
        "repository_candidate_source": str(candidate_source),
        "physical_capsule_source": None if whole_cfg else str(physical_source),
        "source_sha256": _sha256(candidate_source.read_bytes()),
        "placement": {"source": str(source), "insert_before": region["source_range"][0]},
        "source_edit": {
            "start": region["source_range"][0],
            "end": region["source_range"][0],
            "replacement": guarded_directive,
        },
        "compile": candidate_compile,
        "repository_syntax": {
            "status": "pass" if syntax.returncode == 0 else "fail",
            "stderr": syntax.stderr[-4000:],
        },
        "proof": {
            "status": "SOURCE_CONTRACT_PROVED" if proof_passed else "FAILED",
            "class": (
                "compiler_legality_effect_preserving_schedule_contract" if effect_preserving else
                "whole_function_schedule_contract" if whole_cfg else
                "source_schedule_contract"
            ),
            "schedule": schedule,
            "body_refinement": identity,
            "proof_source": baseline_evidence.get("proof_source"),
            "physical_candidate_alive2": {
                "status": "NOT_RUN",
                "reason": "the guarded source schedule directive is absent from the semantic proof build",
            },
            "claim": (
                "the owning body and effects are unchanged; Clang retains legality authority and Z3 proves schedule partition coverage"
                if effect_preserving else
                "the captured body is unchanged and Z3 proves iteration partition coverage"
            ),
            "excluded_claims": [
                "performance improvement",
                "generic equivalence for callbacks, ownership, exceptions, concurrency, or external protocols",
            ],
        },
        "benchmark": {"status": "ADAPTER_REQUIRED", "reason": "production workload remains project-defined"},
        "application_performed": False,
    }
    write_json(artifact, candidate)
    return candidate


def _whole_function_unit(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    normalized = Path(report["production_ir"]["normalized_ir"])
    text = normalized.read_text(errors="replace")
    reference = text.replace("@transform(", "@transform_ref(", 1)
    candidate = text.replace("@transform(", "@transform_candidate(", 1)
    pair = out_dir / "whole-function.identity.ll"
    _pair_ir(reference, candidate, pair)
    proof = alive2_check(discover_toolchain(), pair, out_dir / "alive2", "whole-function-identity")
    return {
        "id": "whole-function",
        "kind": "whole_function_local_ir",
        "symbol": report["selection"]["symbol"],
        "source_range": report["selection"]["source_range"],
        "proof_ir": str(pair),
        "proof": proof,
        "identity_only": True,
        "promotion_scope": (
            "compiled local function only; class invariant required for nonidentity state rewrites"
            if report.get("support_tier") == "bounded_state_transition" else
            "compiled local function under typed ABI preconditions"
        ),
    }


def materialize_cpp_closure(
    report: dict[str, Any], source: Path, semantic_arguments: list[str], directory: Path, out_dir: Path
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    closure = classify_cpp_closure(report)
    source_text = source.read_text()
    if report.get("source_sha256") != _sha256(source_text):
        closure["materialization_status"] = "source_changed"
        closure["source_changes_performed"] = False
        closure["source_integrity"] = {
            "path": str(source),
            "before_sha256": report.get("source_sha256"),
            "after_sha256": _sha256(source_text),
            "unchanged": False,
        }
        path = out_dir / "cpp-closure.json"
        write_json(path, closure)
        closure["artifact"] = str(path)
        return closure
    proof_units: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    if report.get("support_tier") in {"whole_function_local_ir", "bounded_state_transition"}:
        unit = _whole_function_unit(report, out_dir)
        proof_units.append(unit)

    baseline_module = Path(report["production_ir"]["analysis_ir"])
    baseline_symbols = _defined_symbols(baseline_module.read_text(errors="replace"))
    for region in closure["regions"]:
        if not (region["eligible"] or region.get("schedule_eligible")):
            continue
        region_id = str(region["id"])
        region_dir = out_dir / region_id
        region_dir.mkdir(parents=True, exist_ok=True)
        if region.get("isolation_mode") == "whole_function_cfg":
            whole = next((item for item in proof_units if item.get("id") == "whole-function"), None)
            identity = (whole or {}).get("proof", {})
            for choice, schedule_family, directive, factor in _SCHEDULE_VARIANTS:
                direct_candidate = region_dir / f"source-{choice}.cpp"
                direct_candidate.write_text(_direct_hint(source_text, region["source_range"], directive))
                physical_ir = region_dir / f"whole-function-{choice}.ll"
                candidate_compile = _compile_ir(
                    semantic_arguments, directory, source, direct_candidate, physical_ir
                )
                syntax = run(
                    [discover_toolchain().compiler, *semantic_arguments, "-iquote", str(source.parent),
                     "-fsyntax-only", str(direct_candidate)],
                    cwd=directory, timeout=240,
                )
                schedule = _schedule_proof(region_dir, choice, factor)
                candidates.append({
                    "id": f"{region_id}-cfg-{choice}",
                    "region_id": region_id,
                    "schedule_choice": choice,
                    "schedule_family": schedule_family,
                    "grammar": "bounded-cfg-and-loop-schedule-v3",
                    "rule": "whole-function-clang-loop-schedule-hint",
                    "factor": factor,
                    "repository_candidate_source": str(direct_candidate),
                    "source_sha256": _sha256(direct_candidate.read_bytes()),
                    "placement": {"source": str(source), "insert_before": region["source_range"][0]},
                    "compile": candidate_compile,
                    "repository_syntax": {"status": "pass" if syntax.returncode == 0 else "fail", "stderr": syntax.stderr[-4000:]},
                    "proof": {
                        "status": (
                            "SOURCE_CONTRACT_PROVED"
                            if schedule["status"] == "PROVED"
                            and identity.get("status") == "correct"
                            and syntax.returncode == 0 else "FAILED"
                        ),
                        "class": "whole_function_schedule_contract",
                        "schedule": schedule,
                        "body_refinement": identity,
                        "physical_candidate_alive2": {"status": "NOT_RUN", "reason": "the source directive is a compiler scheduling request and is absent from the semantic proof build"},
                        "claim": "ordinary return exits remain in the original function; only a guarded compiler loop schedule hint is added",
                        "excluded_claims": ["performance improvement", "exception or cleanup equivalence outside the captured local function"],
                    },
                    "benchmark": {"status": "ADAPTER_REQUIRED", "reason": "production inputs and workload remain project-defined"},
                    "application_performed": False,
                })
            proof_units.append({
                "id": region_id, "kind": "whole_function_cfg", "status": "isolated" if identity.get("status") == "correct" else "proof_failed",
                "source_range": region["source_range"], "proof": identity,
                "capture": "tagged ordinary returns at whole-function boundary",
            })
            continue
        baseline_source = region_dir / "capsule-baseline.cpp"
        baseline_source.write_text(_wrap_loop(source_text, region["source_range"]))
        baseline_ir = region_dir / "capsule-baseline.ll"
        compiled = _compile_ir(semantic_arguments, directory, source, baseline_source, baseline_ir)
        if compiled["status"] != "pass":
            proof_units.append({
                "id": region_id, "kind": "lambda_capsule", "status": "compile_failed",
                "compile": compiled, "source": str(baseline_source),
            })
            continue
        added = sorted(_defined_symbols(baseline_ir.read_text(errors="replace")) - baseline_symbols)
        lambda_symbols = [item for item in added if "clEv" in item or "$_" in item]
        if len(lambda_symbols) != 1:
            proof_units.append({
                "id": region_id, "kind": "lambda_capsule", "status": "symbol_ambiguous",
                "compile": compiled, "candidate_symbols": added, "source": str(baseline_source),
            })
            continue
        symbol = lambda_symbols[0]
        reference = _extract_function(baseline_ir.read_text(errors="replace"), symbol, "transform_ref")
        pair = region_dir / "capsule.identity.ll"
        _pair_ir(reference, reference.replace("@transform_ref(", "@transform_candidate(", 1), pair)
        identity = alive2_check(discover_toolchain(), pair, region_dir / "alive2", "capsule-identity")
        unit = {
            "id": region_id,
            "kind": "lambda_capsule",
            "status": "isolated" if identity.get("status") == "correct" else "proof_failed",
            "symbol": symbol,
            "source_range": region["source_range"],
            "source": str(baseline_source),
            "source_sha256": _sha256(baseline_source.read_bytes()),
            "compile": compiled,
            "proof_ir": str(pair),
            "proof": identity,
            "capture": "reference",
            "invocation_count": 1,
        }
        proof_units.append(unit)
        if identity.get("status") != "correct":
            continue
        for choice, schedule_family, directive, factor in _SCHEDULE_VARIANTS:
            capsule_candidate = region_dir / f"capsule-{choice}.cpp"
            capsule_candidate.write_text(_wrap_loop(source_text, region["source_range"], directive))
            physical_ir = region_dir / f"capsule-{choice}.ll"
            candidate_compile = _compile_ir(
                semantic_arguments, directory, source, capsule_candidate, physical_ir
            )
            direct_candidate = region_dir / f"source-{choice}.cpp"
            direct_candidate.write_text(_direct_hint(source_text, region["source_range"], directive))
            syntax = run(
                [discover_toolchain().compiler, *semantic_arguments, "-iquote", str(source.parent),
                 "-fsyntax-only", str(direct_candidate)],
                cwd=directory, timeout=240,
            )
            schedule = _schedule_proof(region_dir, choice, factor)
            candidate = {
                "id": f"{region_id}-{choice}",
                "region_id": region_id,
                "schedule_choice": choice,
                "schedule_family": schedule_family,
                "grammar": "typed-loop-schedule-v2",
                "rule": "clang-loop-schedule-hint",
                "factor": factor,
                "physical_capsule_source": str(capsule_candidate),
                "repository_candidate_source": str(direct_candidate),
                "source_sha256": _sha256(direct_candidate.read_bytes()),
                "placement": {"source": str(source), "insert_before": region["source_range"][0]},
                "compile": candidate_compile,
                "repository_syntax": {
                    "status": "pass" if syntax.returncode == 0 else "fail",
                    "stderr": syntax.stderr[-4000:],
                },
                "proof": {
                    "status": (
                        "SOURCE_CONTRACT_PROVED"
                        if schedule["status"] == "PROVED" and identity.get("status") == "correct" else "FAILED"
                    ),
                    "class": "source_schedule_contract",
                    "schedule": schedule,
                    "body_refinement": identity,
                    "proof_source": str(baseline_source),
                    "physical_candidate_alive2": {
                        "status": "NOT_RUN",
                        "reason": "LLVM loop-unroll refinement is not claimed; the source candidate changes only a guarded Clang scheduling directive",
                    },
                    "claim": "the proof build removes the scheduling directive and is capsule-IR identical; Z3 proves the declared loop partition",
                    "excluded_claims": [
                        "whole owning-function equivalence",
                        "external protocol equivalence",
                        "performance improvement before workload benchmarking",
                    ],
                },
                "benchmark": {
                    "status": "ADAPTER_REQUIRED",
                    "reason": "generic C++ input construction and owning workload semantics are not inferred",
                },
                "application_performed": False,
            }
            candidates.append(candidate)

    isolated = [item for item in proof_units if item.get("proof", {}).get("status") == "correct"]
    proved_candidates = [
        item for item in candidates
        if item.get("proof", {}).get("status") == "SOURCE_CONTRACT_PROVED"
    ]
    closure["proof_units"] = proof_units
    closure["candidates"] = candidates
    closure["capabilities"]["isolation"].update({"actual": bool(isolated), "count": len(isolated)})
    closure["capabilities"]["local_proof"].update({"actual": bool(isolated), "identity_unit_count": len(isolated)})
    closure["capabilities"]["candidate_generation"].update({"actual": bool(candidates), "count": len(candidates)})
    closure["capabilities"]["source_rewrite"].update({
        "actual": bool(proved_candidates), "candidate_count": len(proved_candidates), "application_performed": False,
    })
    closure["capabilities"]["benchmark"].update({
        "ready": bool(report.get("transformation_ready")),
        "actual": bool(report.get("transformation_ready")),
        "adapter_required": not bool(report.get("transformation_ready")),
    })
    closure["materialization_status"] = "pass" if isolated else "no_proved_unit"
    closure["source_changes_performed"] = False
    closure["source_integrity"] = {
        "path": str(source),
        "before_sha256": report.get("source_sha256"),
        "after_sha256": _sha256(source.read_bytes()),
        "unchanged": report.get("source_sha256") == _sha256(source.read_bytes()),
    }
    path = out_dir / "cpp-closure.json"
    write_json(path, closure)
    closure["artifact"] = str(path)
    return closure


def aggregate_closure_capabilities(reports: list[dict[str, Any]]) -> dict[str, Any]:
    dispositions = Counter(str(item.get("disposition", "unknown")) for item in reports)
    keys = (
        "semantic_capture", "isolation", "candidate_generation", "local_proof",
        "benchmark", "source_rewrite", "protocol_equivalence",
    )
    counts = {
        key: sum(bool(item.get("capabilities", {}).get(key, {}).get("actual")) for item in reports)
        for key in keys
    }
    predicted = {
        key: sum(bool(item.get("capabilities", {}).get(key, {}).get("ready")) for item in reports)
        for key in keys
    }
    categorical = Counter(
        str(scope.get("category"))
        for item in reports for scope in item.get("protocol_scopes", [])
        if scope.get("categorical_for_generic_ingestion")
    )
    return {
        "dispositions": dict(sorted(dispositions.items())),
        "actual_capabilities": counts,
        "predicted_capabilities": predicted,
        "categorical_protocol_scopes": dict(sorted(categorical.items())),
    }
