from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from .cpp_regions import inspect_cpp_region
from .dataflow_grammar import BoundedDataflowGrammar, load_bounded_dataflow_grammar
from .report import write_json


def _tracked_identity(repository: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "-z"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode(errors="replace"))
    files = [item for item in completed.stdout.decode().split("\0") if item]
    digest = hashlib.sha256()
    entries = []
    for name in sorted(files):
        path = repository / name
        if not path.is_file():
            continue
        value = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append((name, value))
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(value.encode())
        digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "file_count": len(entries)}


def _selected_source(report: dict[str, Any], source: Path) -> str:
    selection = report.get("selection") or {}
    source_range = selection.get("source_range")
    text = source.read_text(errors="replace")
    if isinstance(source_range, list) and len(source_range) == 2:
        begin, end = int(source_range[0]), int(source_range[1])
        if 0 <= begin < end <= len(text):
            return text[begin:end]
    return ""


def classify_cpp_dataflow(source: str, function: str) -> dict[str, Any]:
    compact = any(token in source for token in ("changed.push_back", "changed.emplace_back", "copy_if", "remove_copy_if"))
    state = compact and any(token in source for token in ("cache.", "next_cache", "frame_id", "aggregate_hash"))
    codec = any(token in source for token in ("append_u16", "append_u32", "append_u64", "pack_envelope", "serialize", "append_header"))
    aos = any(token in source for token in ("count_if", "record_kind", "packets"))
    block = any(token in source for token in ("hpc_comp_encode_block", "rgb565", "4x4", "palette_index"))
    invalidation = any(token in source for token in ("dirty", "revision", "sort", "deduplicate", "perspective"))
    geometry = any(token in source for token in ("transform", "matrix", "aabb", "frustum"))
    families: list[dict[str, Any]] = []
    for present, family, evidence in (
        (compact, "predicate-stable-compaction", "variable-output append driven by a predicate"),
        (state, "stateful-delta-transducer", "baseline comparison, delta output, and state mutation coexist"),
        (codec, "fixed-width-codec", "fixed-width payload or envelope helpers are present"),
        (aos, "aos-fused-multi-reduction", "structured-record projection and predicate reduction are present"),
        (block, "quantized-block-4x4", "fixed block encoder or packed palette operation is present"),
    ):
        if present:
            families.append({"family": family, "evidence": evidence, "status": "archetype_detected"})
    deferred = []
    if invalidation:
        deferred.append({
            "family": "incremental-dependency-invalidation",
            "status": "lifetime_protocol_workflow_required",
            "reason": "correctness depends on identity, dependency closure, revision ordering, and publication",
        })
    if geometry:
        deferred.append({
            "family": "batched-geometry-matrix",
            "status": "numerical_contract_required",
            "reason": "floating-point order, NaN, determinism, and layout observables are not declared",
        })
    span = "std::span" in source
    vector = "std::vector" in source or ".push_back(" in source or ".emplace_back(" in source
    capacity_guard = "capacity()" in source and any(token in source for token in ("size() >=", "size() +", "capacity() -", "<= capacity()"))
    reserve_only = ".reserve(" in source and not capacity_guard
    noexcept = "noexcept" in source
    trivial_hint = any(token in source for token in ("uint8_t", "uint16_t", "uint32_t", "uint64_t", "std::byte"))
    if vector and not capacity_guard:
        closure = "bounded_container_contract_required"
    elif vector and capacity_guard and noexcept and trivial_hint:
        closure = "no_growth_container_closure_candidate"
    elif span and noexcept:
        closure = "borrowed_span_closure_candidate"
    else:
        closure = "owning_or_protocol_boundary"
    return {
        "schema_version": "vladder-cpp-bounded-dataflow-classification-v1",
        "function": function,
        "families": families,
        "deferred_families": deferred,
        "container_closure": {
            "status": closure,
            "span_detected": span,
            "vector_or_append_detected": vector,
            "checked_capacity_guard_detected": capacity_guard,
            "reserve_without_capacity_proof": reserve_only,
            "noexcept_boundary_detected": noexcept,
            "trivial_element_hint": trivial_hint,
            "required_obligations": [
                "size + maximum_output <= capacity before the first write",
                "trivially copyable and destructible output element",
                "no throwing construction or helper call",
                "declared input/output alias relation",
                "exact output extent and failure observables",
            ] if vector else [],
        },
        "claim_boundary": (
            "archetype detection and bounded closure planning only; no production candidate, proof, "
            "benchmark, source rewrite, owning-wrapper proof, or whole application equivalence claim"
        ),
    }


def audit_dataflow_manifest(
    manifest: Path,
    output_directory: Path,
    grammar: BoundedDataflowGrammar | None = None,
) -> dict[str, Any]:
    grammar = grammar or load_bounded_dataflow_grammar()
    payload = yaml.safe_load(manifest.read_text())
    if not isinstance(payload, dict) or not isinstance(payload.get("regions"), list):
        raise ValueError("bounded dataflow audit manifest requires a regions list")
    repository = Path(str(payload["repository_root"])).resolve()
    compile_commands = Path(str(payload["compile_commands"])).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    before = _tracked_identity(repository)
    rows = []
    for ordinal, item in enumerate(payload["regions"]):
        if not isinstance(item, dict):
            raise ValueError("audit region entries must be objects")
        identifier = str(item.get("id", f"region-{ordinal}"))
        source = Path(str(item["source"]))
        if not source.is_absolute():
            source = repository / source
        source = source.resolve()
        report = inspect_cpp_region(
            source,
            str(item["function"]),
            compile_commands,
            output_directory / identifier / "cpp-inspect",
            symbol=str(item["symbol"]) if item.get("symbol") else None,
            command_index=int(item["command_index"]) if item.get("command_index") is not None else None,
        )
        selected_source = _selected_source(report, source)
        classification = classify_cpp_dataflow(selected_source, str(item["function"]))
        classification["selected_source_available"] = bool(selected_source)
        if not selected_source:
            classification["selection_disposition"] = "resolve compilation command and symbol before archetype classification"
        family_rows = []
        for family in classification["families"]:
            family_name = family["family"]
            family_rows.append({
                **family,
                "terminals": list(grammar.family_terminals(family_name)),
                "next_action": "supply and prove a bounded output/state contract before source regeneration",
            })
        classification["families"] = family_rows
        row = {
            "id": identifier,
            "source": str(source),
            "function": str(item["function"]),
            "cpp_status": report.get("status"),
            "cpp_support_tier": report.get("support_tier"),
            "cpp_proof_classification": report.get("proof_classification"),
            "dataflow": classification,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_changes_performed": False,
        }
        write_json(output_directory / identifier / "bounded-dataflow-classification.json", row)
        rows.append(row)
    after = _tracked_identity(repository)
    unchanged = before == after
    unresolved_selection = [row["id"] for row in rows if not row["dataflow"].get("selected_source_available")]
    status = "source_changed" if not unchanged else "incomplete_selection" if unresolved_selection else "pass"
    report = {
        "schema_version": "vladder-bounded-dataflow-audit-v1",
        "status": status,
        "manifest": str(manifest.resolve()),
        "repository_root": str(repository),
        "grammar_version": grammar.version,
        "grammar_hash": grammar.hash,
        "region_count": len(rows),
        "regions_with_archetypes": sum(bool(row["dataflow"]["families"]) for row in rows),
        "selection_complete": not unresolved_selection,
        "unresolved_selection_regions": unresolved_selection,
        "regions": rows,
        "repository_identity": {"before": before, "after": after, "unchanged": unchanged},
        "source_changes_performed": not unchanged,
        "optimization_performed": False,
        "claim_boundary": "read-only semantic acceptance audit; no NeuralFusion implementation or speedup claim",
    }
    write_json(output_directory / "bounded-dataflow-audit.json", report)
    return report
