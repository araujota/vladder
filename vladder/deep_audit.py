from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml

from .deep_benchmark import benchmark_deep_candidate, compile_deep_harness
from .deep_grammar import load_deep_grammar, search_deep_grammar
from .deep_ir import DeepKernelContract, build_deep_realization_graph, inspect_source_realization
from .deep_lowering import emit_deep_candidate
from .deep_proof import prove_deep_candidate


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def extract_named_source_region(source: str, function: str, language: str) -> str:
    leaf = function.rsplit("::", 1)[-1]
    if language == "rust":
        pattern = re.compile(rf"(?:pub(?:\([^)]*\))?\s+)?(?:unsafe\s+)?fn\s+{re.escape(leaf)}\s*(?:<[^{{;]*>)?\s*\(")
    else:
        pattern = re.compile(rf"\b{re.escape(leaf)}\s*\(")
    matches = list(pattern.finditer(source))
    for match in matches:
        brace = source.find("{", match.end())
        semicolon = source.find(";", match.end())
        if brace < 0 or (0 <= semicolon < brace):
            continue
        depth = 0
        in_string: str | None = None
        escaped = False
        for index in range(brace, len(source)):
            char = source[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == in_string:
                    in_string = None
                continue
            if char in {'"', "'"}:
                in_string = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[match.start():index + 1]
    raise ValueError(f"could not extract function {function!r} from {language} source")


def _load_region(case: dict[str, Any], side: str, base: Path, language: str) -> tuple[str, Path | None, str]:
    item = case.get(side)
    if not isinstance(item, dict):
        raise ValueError(f"expert audit case requires {side} mapping")
    function = str(item.get("function") or case.get("function") or "")
    if not function:
        raise ValueError(f"expert audit {side} requires a function")
    if item.get("inline") is not None:
        text = str(item["inline"])
        return extract_named_source_region(text, function, language), None, function
    path = _resolve_path(base, str(item.get("source", "")))
    if not path.is_file():
        raise ValueError(f"expert audit source does not exist: {path}")
    return extract_named_source_region(path.read_text(), function, language), path, function


def audit_expert_manifest(
    manifest_path: Path,
    output_directory: Path,
    *,
    run_benchmarks: bool | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), list):
        raise ValueError("deep grammar audit manifest requires a cases list")
    grammar = load_deep_grammar()
    reports: list[dict[str, Any]] = []
    for case_index, case_value in enumerate(raw["cases"]):
        if not isinstance(case_value, dict):
            raise ValueError("deep grammar audit case must be a mapping")
        case = case_value
        case_id = str(case.get("id") or f"case-{case_index:03d}")
        language = str(case.get("language", "c"))
        contract_data = dict(case.get("contract") or {})
        contract = DeepKernelContract(
            str(contract_data.get("archetype", "exact-byte-predicate-reduction")),
            str(contract_data.get("predicate", "equal-u8")),
            input_min=int(contract_data.get("input_min", 0)),
            input_max=int(contract_data.get("input_max", 1 << 30)),
        )
        case_dir = output_directory / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        baseline_text, baseline_path, baseline_function = _load_region(case, "baseline", manifest_path.parent, language)
        expert_text, expert_path, expert_function = _load_region(case, "expert", manifest_path.parent, language)
        baseline = inspect_source_realization(baseline_text, language, baseline_function)
        expert = inspect_source_realization(expert_text, language, expert_function)
        expected_baseline = str((case.get("baseline") or {}).get("realization", baseline.realization or ""))
        expected_expert = str((case.get("expert") or {}).get("realization", expert.realization or ""))
        representation_pass = (
            baseline.representable and expert.representable
            and baseline.predicate == contract.predicate and expert.predicate == contract.predicate
            and baseline.realization == expected_baseline and expert.realization == expected_expert
        )
        stages: dict[str, Any] = {
            "representation": {
                "status": "PASS" if representation_pass else "FAIL",
                "baseline": baseline.to_dict(),
                "expert": expert.to_dict(),
                "expected_baseline": expected_baseline,
                "expected_expert": expected_expert,
            }
        }
        classification = "representation_failure"
        candidate = None
        proof = None
        benchmark = None
        derivation = None
        if representation_pass:
            baseline_graph = build_deep_realization_graph(contract, baseline.realization or "scalar", source_language=language, function_identity=baseline_function)
            expert_graph = build_deep_realization_graph(contract, expert.realization or "scalar", source_language=language, function_identity=expert_function)
            (case_dir / "baseline-graph.json").write_text(json.dumps(baseline_graph.to_dict(), indent=2, sort_keys=True) + "\n")
            (case_dir / "expert-graph.json").write_text(json.dumps(expert_graph.to_dict(), indent=2, sort_keys=True) + "\n")
            search = search_deep_grammar(contract, grammar, source=baseline.realization or "scalar", targets=(expert.realization or "",))
            (case_dir / "search.json").write_text(json.dumps(search.to_dict(), indent=2, sort_keys=True) + "\n")
            derivation = search.derivations[0] if search.derivations else None
            stages["derivation"] = {
                "status": "PASS" if derivation else "FAIL",
                "target": expert.realization,
                "search_classification": search.to_dict()["classification"],
                "derivation": derivation.to_dict() if derivation else None,
            }
            classification = "grammar_failure"
            if derivation:
                try:
                    candidate = emit_deep_candidate(contract, derivation, language, "deep_candidate", grammar)
                    (case_dir / ("candidate.rs" if language == "rust" else "candidate.c")).write_text(candidate.source)
                    generated_graph = build_deep_realization_graph(contract, candidate.realization, source_language=language, function_identity="deep_candidate")
                    lowering_pass = generated_graph.semantic_shape_hash == expert_graph.semantic_shape_hash
                    stages["lowering"] = {
                        "status": "PASS" if lowering_pass else "FAIL",
                        "candidate": candidate.to_dict(),
                        "expert_semantic_shape_hash": expert_graph.semantic_shape_hash,
                        "generated_semantic_shape_hash": generated_graph.semantic_shape_hash,
                    }
                except (ValueError, RuntimeError) as error:
                    lowering_pass = False
                    stages["lowering"] = {"status": "FAIL", "error": str(error)}
                classification = "lowering_failure"
                if lowering_pass and candidate:
                    proof = prove_deep_candidate(contract, derivation, candidate, case_dir / "proofs")
                    native_build = compile_deep_harness(contract, candidate, case_dir / "native-evidence") if proof["status"] == "PASS" else {"status": "NOT_RUN"}
                    native_result: dict[str, Any] = {"status": "NOT_RUN"}
                    if native_build.get("status") == "pass" and native_build.get("binary"):
                        completed = subprocess.run(
                            [str(native_build["binary"]), "candidate", "521", "1"],
                            text=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        native_result = {
                            "status": "PASS" if completed.returncode == 0 else "FAIL",
                            "return_code": completed.returncode,
                            "exhaustive_single_byte_pairs": 65536,
                            "boundary_lengths": 521,
                            "stdout": completed.stdout,
                            "stderr": completed.stderr,
                        }
                    proof_pass = proof["status"] == "PASS" and native_result["status"] == "PASS"
                    stages["proof"] = {
                        "status": "PASS" if proof_pass else "FAIL",
                        "formal_status": proof["status"],
                        "artifact": str(case_dir / "proofs" / f"{candidate.id}.proof.json"),
                        "native_build": native_build,
                        "native_differential": native_result,
                    }
                    classification = "proof_failure"
                    if proof_pass:
                        should_benchmark = bool(case.get("benchmark", False)) if run_benchmarks is None else run_benchmarks
                        if should_benchmark:
                            policy = dict(case.get("benchmark_policy") or raw.get("benchmark_policy") or {})
                            benchmark = benchmark_deep_candidate(
                                contract,
                                derivation,
                                candidate,
                                case_dir / "benchmark",
                                processes=int(policy.get("processes", 10)),
                                repetitions_per_process=int(policy.get("repetitions_per_process", 3)),
                                n=int(policy.get("n", 1 << 20)),
                                inner=int(policy.get("inner", 128)),
                                cpu=int(policy["cpu"]) if policy.get("cpu") is not None else None,
                                minimum_effect_percent=float(policy.get("minimum_effect_percent", 1.0)),
                            )
                            paired = benchmark.get("paired", {})
                            stages["performance"] = {
                                "status": "PASS" if paired.get("promotable_physical_evidence") else "NOT_PROMOTED",
                                "effect_percent": paired.get("paired_effect_percent"),
                                "confidence_95": paired.get("paired_effect_95_percent"),
                                "classification": paired.get("classification"),
                                "hot_assembly_identity": (benchmark.get("build") or {}).get("hot_assembly_identity"),
                            }
                            classification = "complete" if paired.get("promotable_physical_evidence") else "performance_not_promoted"
                        else:
                            stages["performance"] = {"status": "NOT_RUN", "reason": "manifest did not request physical ranking"}
                            classification = "proof_complete_measurement_not_run"
        report = {
            "id": case_id,
            "language": language,
            "contract": contract.to_dict(),
            "classification": classification,
            "stages": stages,
            "lineage": {
                "baseline_source": str(baseline_path) if baseline_path else "inline",
                "baseline_sha256": hashlib.sha256(baseline_text.encode()).hexdigest(),
                "expert_source": str(expert_path) if expert_path else "inline",
                "expert_sha256": hashlib.sha256(expert_text.encode()).hexdigest(),
                "derivation_hash": derivation.derivation_hash if derivation else None,
                "candidate_id": candidate.id if candidate else None,
            },
        }
        (case_dir / "audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        reports.append(report)
    summary = {
        "schema_version": "vladder-expert-grammar-audit-v1",
        "status": "pass" if reports and all(item["classification"] in {"complete", "proof_complete_measurement_not_run", "performance_not_promoted"} for item in reports) else "incomplete",
        "grammar_version": grammar.version,
        "grammar_hash": grammar.hash,
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256_path(manifest_path),
        "case_count": len(reports),
        "classifications": {name: sum(item["classification"] == name for item in reports) for name in sorted({item["classification"] for item in reports})},
        "cases": reports,
    }
    assembly_groups: dict[str, list[str]] = {}
    for item in reports:
        identity = (((item.get("stages") or {}).get("performance") or {}).get("hot_assembly_identity") or {}).get("normalized_sha256")
        if identity:
            assembly_groups.setdefault(str(identity), []).append(str(item["id"]))
    summary["assembly_identity_groups"] = [
        {"normalized_sha256": identity, "cases": sorted(cases), "deduplicated": len(cases) > 1}
        for identity, cases in sorted(assembly_groups.items())
    ]
    (output_directory / "expert-grammar-audit.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def repository_fingerprint(root: Path) -> dict[str, Any]:
    root = root.resolve()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain=v1", "-z"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
    return {"root": str(root), "revision": revision, "status_sha256": _sha256_bytes(status), "status_entry_count": status.count(b"\0")}


def audit_neuralfusion_evidence_readonly(
    repository_root: Path,
    evidence_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    before = repository_fingerprint(repository_root)
    files = sorted(evidence_root.resolve().glob("**/cpp-information-flow.json"))
    regions: list[dict[str, Any]] = []
    mappings = {
        "InputBoundary": "Input",
        "ResultBoundary": "Output",
        "CompiledRegion": "Call",
        "SourceCall": "Call",
        "LocalRegion": "Loop",
    }
    for path in files:
        payload = json.loads(path.read_text())
        nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
        mapped = [mappings.get(str(node.get("kind")), "Control") for node in nodes if isinstance(node, dict)]
        instruction_counts: dict[str, int] = {}
        for node in nodes:
            if isinstance(node, dict):
                for key, value in (node.get("attributes", {}).get("instruction_counts", {}) or {}).items():
                    instruction_counts[str(key)] = instruction_counts.get(str(key), 0) + int(value)
        invariants = dict(payload.get("invariants") or {})
        regions.append({
            "id": path.parent.name,
            "artifact": str(path),
            "artifact_sha256": _sha256_path(path),
            "node_count": len(nodes),
            "mapped_common_kinds": sorted(set(mapped)),
            "instruction_counts": instruction_counts,
            "semantic_boundary_representable": bool(nodes),
            "deep_byte_predicate_archetype_detected": False,
            "deep_local_optimization_status": "requires_local_archetype_extraction" if nodes else "representation_failure",
            "external_or_unwind_boundary": bool(invariants.get("remaining_external_calls") or invariants.get("unwind")),
            "claim": "read-only representability audit; no candidate generation, proof, benchmark, or source change",
        })
    after = repository_fingerprint(repository_root)
    unchanged = before == after
    report = {
        "schema_version": "vladder-neuralfusion-deep-readonly-v1",
        "status": "pass" if files and unchanged else "fail",
        "before": before,
        "after": after,
        "repository_unchanged": unchanged,
        "evidence_root": str(evidence_root.resolve()),
        "artifact_count": len(files),
        "semantic_boundaries_representable": sum(item["semantic_boundary_representable"] for item in regions),
        "deep_archetypes_detected": sum(item["deep_byte_predicate_archetype_detected"] for item in regions),
        "regions": regions,
        "limitations": [
            "existing C++ evidence is boundary-level and does not contain byte-predicate reduction semantics",
            "this audit intentionally does not rerun extraction, synthesis, project builds, or physical workflows",
            "absence of a deep-v2 archetype does not block lifetime, protocol, or other shared grammar analyses",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
