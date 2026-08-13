from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable, Mapping

from .cpp_regions import inspect_cpp_region
from .deep_benchmark import _hot_assembly_identity
from .language_adapter import canonical_hash
from .selected_build_search import (
    SelectedBuildCppGrammar,
    _compose_candidate_source,
    _compose_proof,
    _materialize_selected_build_choice,
)


CROSS_TU_SELECTED_BUILD_VERSION = "cross-tu-selected-build-v1"


def capture_cross_tu_selected_build_regions(
    report: Mapping[str, Any],
    compile_commands: Path,
    output_directory: Path,
    *,
    maximum_functions: int = 32,
) -> dict[str, Any]:
    """Bind definition-visible C++ functions to local executable grammar regions."""
    output_directory.mkdir(parents=True, exist_ok=True)
    units = {
        str(item["id"]): item
        for item in report.get("index", {}).get("translation_units", ())
        if isinstance(item, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for function in tuple(report.get("slice", {}).get("functions", ()))[:maximum_functions]:
        if not isinstance(function, Mapping):
            continue
        function_id = str(function.get("id") or "")
        symbol = function_id.split("::", 1)[1] if function_id.startswith("cpp::") else function_id
        contracts = function.get("contracts") if isinstance(function.get("contracts"), Mapping) else {}
        unit = units.get(str(contracts.get("translation_unit")))
        if unit is None:
            rows.append(_blocked(function_id, symbol, "translation unit is absent from the selected-build index"))
            continue
        source = Path(str(unit.get("source") or ""))
        if not source.is_file():
            rows.append(_blocked(function_id, symbol, "selected-build source is unavailable"))
            continue
        function_name = _demangled_function_name(symbol)
        if not function_name:
            rows.append(_blocked(function_id, symbol, "native symbol cannot be mapped to a source function name"))
            continue
        region_output = output_directory / canonical_hash({"function": function_id})[:20]
        try:
            captured = inspect_cpp_region(
                source,
                function_name,
                compile_commands,
                region_output,
                symbol=symbol,
                command_index=int(unit["index"]),
            )
        except (OSError, RuntimeError, ValueError) as error:
            rows.append(_blocked(function_id, symbol, f"selected-build extraction failed: {error}"))
            continue
        report_path = region_output / "cpp-support.json"
        eligible = tuple(
            item for item in captured.get("closure", {}).get("regions", ())
            if isinstance(item, Mapping)
            and (item.get("eligible") or item.get("schedule_eligible"))
        )
        rows.append({
            "function_id": function_id,
            "symbol": symbol,
            "function": function_name,
            "translation_unit": str(unit["id"]),
            "source": str(source.resolve()),
            "command_index": int(unit["index"]),
            "status": "applicable" if captured.get("selection") and eligible else "inapplicable",
            "authority": "selected-build-region-closure-v1",
            "reason": (
                ""
                if captured.get("selection") and eligible
                else _capture_reason(captured)
            ),
            "report": str(report_path),
            "region_count": len(eligible),
            "regions": [str(item["id"]) for item in eligible],
        })
    payload = {
        "schema_version": "vladder-cross-tu-selected-build-capture-v1",
        "version": CROSS_TU_SELECTED_BUILD_VERSION,
        "function_count": len(rows),
        "applicable_function_count": sum(item["status"] == "applicable" for item in rows),
        "region_count": sum(int(item.get("region_count", 0)) for item in rows),
        "functions": rows,
    }
    payload["capture_hash"] = canonical_hash(payload)
    path = output_directory / "cross-tu-selected-build.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return {**payload, "artifact": str(path)}


def evaluate_cross_tu_selected_build_candidate(
    capture: Mapping[str, Any],
    selection: Mapping[str, str],
    output_directory: Path,
    *,
    selected_functions: Iterable[str] | None = None,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    selected_function_ids = (
        frozenset(str(item) for item in selected_functions)
        if selected_functions is not None else None
    )
    descriptors = {
        str(item["function_id"]): item
        for item in capture.get("functions", ())
        if isinstance(item, Mapping) and item.get("status") == "applicable"
        and (
            selected_function_ids is None
            or str(item["function_id"]) in selected_function_ids
        )
    }
    if not descriptors:
        raise ValueError("the selected cross-TU slice contains no executable regional definition")
    reports = {
        function_id: json.loads(Path(str(item["report"])).read_text())
        for function_id, item in descriptors.items()
    }
    selected_candidates: dict[str, list[dict[str, Any]]] = {}
    local_selections: dict[str, dict[str, str]] = {}
    for function_id, report in reports.items():
        grammar = SelectedBuildCppGrammar(report)
        local: dict[str, str] = {}
        for region in grammar.regions:
            key = region_key(function_id, region)
            choice = str(selection.get(key, "baseline"))
            if choice != "baseline" and choice not in grammar.by_region[region]:
                raise ValueError(f"cross-TU selected-build choice is absent: {key}={choice}")
            local[region] = choice
            if choice != "baseline":
                selected_candidates.setdefault(function_id, []).append(
                    _materialize_selected_build_choice(
                        report,
                        region,
                        choice,
                        grammar.by_region[region][choice],
                        output_directory
                        / "regional"
                        / canonical_hash({"function": function_id})[:16]
                        / "materialize"
                        / choice,
                    )
                )
        local_selections[function_id] = local

    by_source: dict[str, list[str]] = {}
    for function_id, descriptor in descriptors.items():
        by_source.setdefault(str(descriptor["source"]), []).append(function_id)
    source_results: list[dict[str, Any]] = []
    all_proofs: list[dict[str, Any]] = []
    for source_name, function_ids in sorted(by_source.items()):
        original = Path(source_name)
        source_text = original.read_text()
        selected = [
            candidate
            for function_id in function_ids
            for candidate in selected_candidates.get(function_id, ())
        ]
        generated = _compose_candidate_source(source_text, selected)
        source_root = output_directory / "translation-units" / hashlib.sha256(source_name.encode()).hexdigest()[:16]
        source_root.mkdir(parents=True, exist_ok=True)
        generated_path = source_root / original.name
        generated_path.write_text(generated)
        representative = reports[function_ids[0]]
        symbols = [str(reports[item].get("selection", {}).get("symbol")) for item in function_ids]
        compiled = _compile_symbols(representative, original, generated_path, symbols, source_root)
        proofs = [
            _compose_proof(
                reports[function_id],
                local_selections[function_id],
                selected_candidates.get(function_id, []),
            )
            for function_id in function_ids
        ]
        all_proofs.extend(proofs)
        source_results.append({
            "source_sha256": hashlib.sha256(generated.encode()).hexdigest(),
            "source": str(generated_path),
            "functions": function_ids,
            "compile": compiled,
        })
    proof_status = "PASS" if all(item.get("status") == "PASS" for item in all_proofs) else "FAIL"
    compile_status = "PASS" if all(item["compile"].get("status") == "PASS" for item in source_results) else "FAIL"
    identities = sorted(
        identity
        for item in source_results
        for identity in item["compile"].get("symbol_identities", {}).values()
        if identity
    )
    baseline = all(choice == "baseline" for choice in selection.values())
    candidate_id = canonical_hash({
        "capture": capture.get("capture_hash"),
        "selected_functions": sorted(descriptors),
        "selection": dict(sorted(selection.items())),
        "sources": [item["source_sha256"] for item in source_results],
    })
    proof_path = output_directory / "proof.json"
    proof_path.write_text(json.dumps({
        "schema_version": "vladder-cross-tu-selected-build-proof-v1",
        "status": proof_status,
        "functions": all_proofs,
        "claim": "non-overlapping, independently proved local region schedules compose across selected translation units",
        "excluded_claims": ["cross-call functional rewrites", "external protocol behavior", "performance improvement"],
    }, indent=2, sort_keys=True) + "\n")
    return {
        "candidate_id": candidate_id,
        "realization": "baseline" if baseline else "cross-tu-composed-schedules",
        "parameters": {
            "selected_functions": sorted(descriptors),
            "selection": dict(sorted(selection.items())),
        },
        "source_sha256": canonical_hash([item["source_sha256"] for item in source_results]),
        "proof_status": proof_status,
        "proof_class": "cross-tu-selected-build-source-schedule-v1",
        "compile_status": compile_status,
        "assembly_identity": canonical_hash(identities) if identities and compile_status == "PASS" else None,
        "artifacts": {
            "proof": str(proof_path),
            "translation_units": [item["source"] for item in source_results],
        },
        "compile": {"status": compile_status, "translation_units": source_results},
    }


def region_key(function_id: str, region: str) -> str:
    return f"{canonical_hash({'function': function_id})[:16]}:{region}"


def applicable_region_domains(capture: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    domains: dict[str, tuple[str, ...]] = {}
    for descriptor in capture.get("functions", ()):
        if not isinstance(descriptor, Mapping) or descriptor.get("status") != "applicable":
            continue
        report = json.loads(Path(str(descriptor["report"])).read_text())
        grammar = SelectedBuildCppGrammar(report)
        for region in grammar.regions:
            domains[region_key(str(descriptor["function_id"]), region)] = (
                "baseline", *tuple(sorted(grammar.by_region[region]))
            )
    return domains


def _compile_symbols(
    report: Mapping[str, Any],
    original: Path,
    source: Path,
    symbols: Iterable[str],
    output_directory: Path,
) -> dict[str, Any]:
    command = report.get("compile_command", {})
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return {"status": "FAIL", "reason": "clang++ unavailable"}
    assembly = output_directory / "candidate.identity.s"
    argv = [
        compiler,
        *[str(item) for item in command.get("semantic_arguments", ())],
        "-iquote", str(original.parent),
        "-O3", "-fno-inline-functions", "-S", str(source), "-o", str(assembly),
    ]
    completed = subprocess.run(
        argv,
        cwd=str(command.get("directory") or original.parent),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    if completed.returncode:
        return {
            "status": "FAIL", "command": argv,
            "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-8000:],
        }
    identities = {
        symbol: _hot_assembly_identity(assembly, symbol).get("normalized_sha256")
        for symbol in symbols
    }
    return {
        "status": "PASS" if all(identities.values()) else "FAIL",
        "command": argv,
        "assembly": str(assembly),
        "symbol_identities": identities,
        "stderr": completed.stderr[-4000:],
    }


def _demangled_function_name(symbol: str) -> str | None:
    cxxfilt = shutil.which("c++filt")
    if not cxxfilt:
        return None
    completed = subprocess.run(
        [cxxfilt, symbol], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
    )
    if completed.returncode:
        return None
    demangled = completed.stdout.strip().split("(", 1)[0].strip()
    if not demangled:
        return None
    name = demangled.rsplit("::", 1)[-1]
    name = re.sub(r"<.*>$", "", name)
    return name if re.fullmatch(r"[A-Za-z_~][A-Za-z0-9_~]*", name) else None


def _capture_reason(captured: Mapping[str, Any]) -> str:
    adapters = captured.get("adapters", ())
    if adapters:
        return "; ".join(str(item.get("reason") or item.get("kind")) for item in adapters if isinstance(item, Mapping))
    return "no executable bounded local region was found in the selected definition"


def _blocked(function_id: str, symbol: str, reason: str) -> dict[str, Any]:
    return {
        "function_id": function_id,
        "symbol": symbol,
        "status": "inapplicable",
        "authority": "selected-build-region-closure-v1",
        "reason": reason,
        "region_count": 0,
        "regions": [],
    }
