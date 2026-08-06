from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


STRUCTURED_DATAFLOW_SCHEMA = "vladder-structured-dataflow-v1"


def classify_structured_dataflow(artifact: Path) -> dict[str, Any]:
    artifact = artifact.resolve()
    graph = _load(artifact)
    directory = artifact.parent
    effects = _load_optional(directory / "compiled-effects.json")
    closure = _load_optional(directory / "region-closure.json")
    support = _load_optional(directory / "cpp-support.json")
    nodes = [item for item in graph.get("nodes", ()) if isinstance(item, dict)]
    calls = {
        str(item.get("attributes", {}).get("callee", "")).lower()
        for item in nodes if item.get("kind") in {"Call", "SourceCall"}
    }
    calls |= {str(item).lower() for item in effects.get("calls", ())}
    operations = {str(item.get("operation", "")).lower() for item in nodes}
    counts = {str(key): int(value) for key, value in effects.get("instruction_counts", {}).items()}
    aggregate = effects.get("aggregate_operations", {})
    source = support.get("source_semantics", {})
    features = {
        "loops": int(source.get("loop_count", 0)) + sum("loop" in value for value in operations),
        "branches": counts.get("branches", 0),
        "loads": counts.get("loads", 0),
        "stores": counts.get("stores", 0),
        "aggregate_channels": sum(int(value) for value in aggregate.values()) if isinstance(aggregate, dict) else 0,
        "allocation": bool(effects.get("allocation_calls")),
        "deallocation": bool(effects.get("deallocation_calls")),
        "unwind": bool(effects.get("unwind_operations")),
        "synchronization": bool(effects.get("synchronization_operations")),
        "object_state": bool((graph.get("contracts") or {}).get("object_state")),
        "external_calls": len(effects.get("external_calls", ())),
        "call_count": len(calls),
    }
    archetypes: list[dict[str, Any]] = []

    def add(identifier: str, evidence: list[str], grammar: str, observables: list[str]) -> None:
        if evidence:
            archetypes.append({
                "id": identifier,
                "evidence": sorted(evidence),
                "grammar_family": grammar,
                "required_observables": observables,
                "confidence": "high" if len(evidence) >= 2 else "medium",
            })

    def matching(*needles: str) -> list[str]:
        return sorted({call for call in calls if any(needle in call for needle in needles)})

    add(
        "stable-partition-prefix-scatter",
        matching("stable_partition", "partition", "prefix", "scan", "scatter", "compact"),
        "predicate-mask-prefix-stable-compaction",
        ["stable output order", "exact output extent", "capacity failure", "selected values/indices"],
    )
    sparse = matching("operator[]", "at", "index", "find", "lookup", "patch", "delta", "dirty")
    if features["stores"] and features["branches"]:
        sparse += ["branching-memory-update"]
    add(
        "sparse-indexed-update", sparse,
        "gather-validate-apply-with-bounded-output",
        ["updated state", "failure tag", "untouched locations", "output extent"],
    )
    add(
        "parse-validate-materialize",
        matching("parse", "decode", "validate", "serialize", "encode", "materialize"),
        "parse-validate-pack-tagged-exit",
        ["result fields", "malformed-input disposition", "consumed extent", "output bytes"],
    )
    cache_evidence = matching("find", "lookup", "has_value", "insert", "erase", "swap", "assign", "load")
    if features["object_state"]:
        cache_evidence += ["object-old-new-state"]
    add(
        "retained-cache-conditional-patch", cache_evidence,
        "versioned-cache-lookup-patch-publication",
        ["old/new generation", "hit/miss", "published state", "retirement"],
    )
    state_evidence = matching("coalesce", "publish", "commit", "rollback", "advance", "retire", "detach")
    if features["synchronization"]:
        state_evidence += ["synchronization"]
    add(
        "state-transition-coalescing", state_evidence,
        "finite-resource-protocol-plus-latest-value-coalescing",
        ["state trace", "publication order", "rollback", "terminal state"],
    )
    traversal_evidence = []
    if features["loops"] or features["branches"] >= 2:
        traversal_evidence.append("bounded-control-traversal")
    if features["aggregate_channels"] or any("operator->" in call or "getelementptr" in call for call in calls):
        traversal_evidence.append("structured-field-projection")
    if features["loads"] and features["stores"]:
        traversal_evidence.append("read-modify-write-flow")
    add(
        "structured-traversal-fusion", traversal_evidence,
        "aos-projection-fused-multi-reduction",
        ["field projections", "all reductions", "iteration order", "failure exits"],
    )
    lifetime_evidence = []
    if features["allocation"] or features["deallocation"]:
        lifetime_evidence.append("allocation-retirement")
    if matching("reserve", "resize", "clear", "assign", "emplace", "push_back"):
        lifetime_evidence.append("container-realization")
    add(
        "realization-lifetime", lifetime_evidence,
        "retain-eliminate-split-stream-placement",
        ["construction count", "invalidation frontier", "final use", "memory delta"],
    )

    executable_regions = [
        item for item in support.get("subregions", ())
        if isinstance(item, dict) and item.get("extractable_candidate")
    ]
    remaining_protocols = list(closure.get("remaining_protocols", ()))
    if executable_regions:
        route = "bounded_local_lowerer"
    elif archetypes and any(item["id"] == "state-transition-coalescing" for item in archetypes):
        route = "finite_protocol_plan_then_local_lowerer"
    elif archetypes:
        route = "architectural_realization_plan_adapter_required"
    else:
        route = "no_supported_structured_archetype"
    report = {
        "schema_version": STRUCTURED_DATAFLOW_SCHEMA,
        "artifact": str(artifact),
        "function": graph.get("name") or support.get("function"),
        "features": features,
        "archetypes": archetypes,
        "archetype_count": len(archetypes),
        "lowering_route": route,
        "executable_local_region_count": len(executable_regions),
        "remaining_protocols": remaining_protocols,
        "candidate_generation_eligibility": (
            "executable_local" if executable_regions else
            "protocol_model_required" if route.startswith("finite_protocol") else
            "agent_realization_required" if archetypes else "not_applicable"
        ),
        "claim_boundary": (
            "archetype recognition and lowerer routing are not a source rewrite or equivalence proof; "
            "only explicitly extracted local regions are executable automatically"
        ),
    }
    report["graph_hash"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"structured dataflow artifact must be a mapping: {path}")
    return value


def _load_optional(path: Path) -> dict[str, Any]:
    return _load(path) if path.is_file() else {}
