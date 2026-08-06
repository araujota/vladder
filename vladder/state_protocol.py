from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from z3 import And, Bool, BoolVal, Int, Not, Or, Solver, sat

from .resource_protocol import verify_resource_protocol


PROTOCOLS = ("versioned_cache", "transactional_publication", "finite_resource")


def verify_state_protocol(manifest_path: Path, output_directory: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("protocol manifest must be a mapping")
    protocol = str(raw.get("protocol", ""))
    if protocol not in PROTOCOLS:
        raise ValueError(f"unsupported protocol {protocol!r}; expected one of {PROTOCOLS}")
    if protocol == "finite_resource":
        return verify_resource_protocol(manifest_path, output_directory)
    if protocol == "versioned_cache":
        result, smt2 = _verify_versioned_cache(raw)
    else:
        result, smt2 = _verify_transactional_publication(raw)
    (output_directory / "protocol-obligations.smt2").write_text(smt2)
    report = {
        "schema_version": "vladder-state-protocol-proof-v1",
        "protocol": protocol,
        "manifest": str(manifest_path),
        "status": "PASS" if all(item["status"] == "PROVED" for item in result) else "FAIL",
        "proof_method": "bounded Z3 state-transition obligations",
        "proof_scope": "declared finite state projection only; owning C++ and external runtime behavior remain integration obligations",
        "obligations": result,
        "artifact": str(output_directory / "protocol-obligations.smt2"),
    }
    (output_directory / "protocol-proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _check(name: str, assumptions: list[Any], violation: Any) -> tuple[dict[str, Any], str]:
    solver = Solver()
    solver.add(*assumptions)
    solver.add(violation)
    status = solver.check()
    model = {str(item): str(solver.model()[item]) for item in solver.model()} if status == sat else {}
    result = {
        "name": name,
        "status": "FAIL" if status == sat else "PROVED",
        "solver_result": str(status).upper(),
        "counterexample": model,
    }
    return result, solver.to_smt2()


def _verify_versioned_cache(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    policy = raw.get("policy", {})
    mutations = {str(item) for item in raw.get("mutations", [])}
    invalidators = {str(item) for item in raw.get("invalidators", [])}
    non_invalidators = {str(item) for item in raw.get("non_invalidators", [])}
    overlap = invalidators & non_invalidators
    uncovered = mutations - invalidators - non_invalidators
    obligations: list[dict[str, Any]] = []
    smt: list[str] = []

    classification_ok = not overlap and not uncovered and bool(mutations)
    result, text = _check(
        "complete mutation classification",
        [],
        BoolVal(not classification_ok),
    )
    result["detail"] = {"overlap": sorted(overlap), "uncovered": sorted(uncovered)}
    obligations.append(result); smt.append(text)

    source_before, source_after = Int("source_before"), Int("source_after")
    cache_version_after = Int("cache_version_after")
    cache_valid_after = Bool("cache_valid_after")
    action = str(policy.get("on_invalidating_mutation", "none"))
    action_constraints = {
        "invalidate": Not(cache_valid_after),
        "refresh": And(cache_valid_after, cache_version_after == source_after),
        "none": And(cache_valid_after, cache_version_after == source_before),
    }
    result, text = _check(
        "invalidating mutation cannot leave a stale readable cache",
        [source_after == source_before + 1, action_constraints.get(action, BoolVal(False))],
        And(cache_valid_after, cache_version_after != source_after),
    )
    obligations.append(result); smt.append(text)

    retain = str(policy.get("on_non_invalidating_mutation", "retain"))
    result, text = _check(
        "non-invalidating transition preserves represented version",
        [source_after == source_before, cache_version_after == source_before],
        Or(BoolVal(retain not in {"retain", "refresh"}), cache_version_after != source_after),
    )
    obligations.append(result); smt.append(text)

    atomic = bool(policy.get("publish_atomic", False))
    retired_safely = bool(policy.get("retire_after_readers", False))
    result, text = _check("publication is atomic", [], BoolVal(not atomic))
    obligations.append(result); smt.append(text)
    result, text = _check("retirement waits for readers", [], BoolVal(not retired_safely))
    obligations.append(result); smt.append(text)
    return obligations, "\n; ---- obligation ----\n".join(smt)


def _verify_transactional_publication(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    policy = raw.get("policy", {})
    checks = (
        ("prepared state is not reader-visible", not bool(policy.get("prepare_private", False))),
        ("commit publishes atomically", not bool(policy.get("commit_atomic", False))),
        ("rollback restores the prior committed state", not bool(policy.get("rollback_restores", False))),
        ("readers observe committed generations only", not bool(policy.get("readers_committed_only", False))),
        ("retirement waits for readers", not bool(policy.get("retire_after_readers", False))),
    )
    obligations: list[dict[str, Any]] = []
    smt: list[str] = []
    for name, violates in checks:
        result, text = _check(name, [], BoolVal(violates))
        obligations.append(result); smt.append(text)
    return obligations, "\n; ---- obligation ----\n".join(smt)
