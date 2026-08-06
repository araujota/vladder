from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .closure_bindings import language_boundary_catalog
from .protocol_envelopes import protocol_registry, validate_protocol_application
from .semantic_closure import FunctionSummary, compose_system_graph, prove_system_graph


SYSTEM_CLOSURE_WORKFLOW_SCHEMA = "system-closure-workflow-v1"


def _load_manifest(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("system closure manifest must be an object")
    functions = value.get("functions", [])
    reports = value.get("reports", [])
    if not isinstance(functions, list) or not isinstance(reports, list) or not functions and not reports:
        raise ValueError("system closure manifest requires a non-empty functions or reports list")
    return value


def _summary_from_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text())
    candidates = (
        report.get("compositional_summary"),
        report.get("build_identity", {}).get("compositional_summary"),
        report.get("support", {}).get("build_identity", {}).get("compositional_summary"),
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    raise ValueError(f"inspection artifact has no compositional_summary: {path}")


def run_system_closure(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = _load_manifest(manifest_path)
    summary_values = list(raw.get("functions", []))
    for report in raw.get("reports", []):
        path = Path(str(report))
        if not path.is_absolute():
            path = manifest_path.parent / path
        summary_values.append(_summary_from_report(path.resolve()))
    functions = tuple(FunctionSummary.from_dict(item) for item in summary_values)
    graph = compose_system_graph(str(raw.get("system", manifest_path.stem)), functions)
    proof = prove_system_graph(graph, output_directory / "proofs")
    protocols = protocol_registry()
    protocol_validation = [
        {"function": function.id, **validate_protocol_application(application)}
        for function in functions
        for application in function.contracts.get("protocol_applications", [])
    ]
    protocol_closed = all(item["status"] == "closed" for item in protocol_validation)
    boundary_matrix = [
        {
            "function": item["id"],
            "language": item["source_language"],
            "closure": item["closure"],
            "transitive_effects": item["transitive_effects"],
            "protocol_envelopes": item.get("contracts", {}).get("protocol_envelopes", []),
            "candidate_count": item["candidate_count"],
            "boundary_count": sum(1 for boundary in graph["boundaries"] if boundary["caller"] == item["id"]),
        }
        for item in graph["functions"]
    ]
    boundary_groups: dict[tuple[str, str], dict[str, Any]] = {}
    for boundary in graph["boundaries"]:
        key = (boundary["missing_contract"], boundary["next_action"])
        group = boundary_groups.setdefault(key, {
            "missing_contract": key[0],
            "next_action": key[1],
            "count": 0,
            "functions": set(),
            "representative_constructs": [],
        })
        group["count"] += 1
        group["functions"].add(boundary["caller"])
        if len(group["representative_constructs"]) < 8:
            group["representative_constructs"].append(boundary["native_construct"])
    boundary_summary = [
        {**group, "functions": sorted(group["functions"])}
        for group in sorted(boundary_groups.values(), key=lambda item: (-item["count"], item["missing_contract"]))
    ]
    report = {
        "schema_version": SYSTEM_CLOSURE_WORKFLOW_SCHEMA,
        "status": "pass" if proof["status"] == "PASS" and protocol_closed else "protocol_guard_required" if not protocol_closed else "proof_failed",
        "manifest": str(manifest_path),
        "system_graph": graph,
        "proof": proof,
        "protocol_registry": protocols,
        "protocol_validation": protocol_validation,
        "boundary_matrix": boundary_matrix,
        "boundary_summary": boundary_summary,
        "language_boundary_catalog": language_boundary_catalog(),
        "meaningful_semantic_coverage": bool(graph["functions"]),
        "candidate_generation_performed": False,
        "source_changes_performed": False,
        "next_action": (
            "run attributed computational grammars inside closed components; retain listed boundaries"
            if graph["boundaries"]
            else "run attributed computational grammars and compose local proofs with this closure proof"
        ),
        "claim_boundary": (
            "compositional effects, finite protocol envelopes, and closed-subgraph isolation; "
            "not arbitrary callback, third-party protocol, or whole-program equivalence"
        ),
    }
    (output_directory / "system-flow-graph.json").write_text(
        json.dumps(graph, indent=2, sort_keys=True) + "\n"
    )
    (output_directory / "protocol-envelopes.json").write_text(
        json.dumps(protocols, indent=2, sort_keys=True) + "\n"
    )
    (output_directory / "system-closure-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report
