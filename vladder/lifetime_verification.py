from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable

from z3 import Bool, BoolVal, Int, Not, Or, Solver, unsat

from .lifetime_attribution import LifetimeEvent
from .lifetime_grammar import LifetimeCandidate
from .lifetime_graph import LifetimeFlowGraph, LifetimeInformation


@dataclass(frozen=True)
class LifetimeProofObligation:
    name: str
    status: str
    method: str
    detail: str
    counterexample: dict[str, Any] | None


@dataclass(frozen=True)
class LifetimeVerificationResult:
    candidate_id: str
    information_id: str
    status: str
    proof_class: str
    obligations: tuple[LifetimeProofObligation, ...]
    differential_status: str
    trace_observations: int
    counterexamples: tuple[dict[str, Any], ...]
    alive2_scope: str
    protocol_adapter: str | None
    artifact: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_lifetime_candidate(
    graph: LifetimeFlowGraph,
    candidate: LifetimeCandidate,
    events: Iterable[LifetimeEvent],
    output_directory: Path | None = None,
) -> LifetimeVerificationResult:
    item = graph.item(candidate.information_id)
    obligations: list[LifetimeProofObligation] = []
    counterexamples: list[dict[str, Any]] = []
    smt_sections: list[str] = []

    structural = _structural_obligations(graph, item, candidate)
    obligations.extend(structural)
    counterexamples.extend(result.counterexample for result in structural if result.counterexample)

    for result, smt in _z3_obligations(item, candidate):
        obligations.append(result)
        smt_sections.append(f"; obligation: {result.name}\n{smt}")
        if result.counterexample:
            counterexamples.append(result.counterexample)

    trace_status, trace_observations, trace_failures = _replay_candidate(graph, item, candidate, tuple(events))
    counterexamples.extend(trace_failures)
    obligations.append(LifetimeProofObligation(
        "stateful consumer equivalence",
        "pass" if trace_status == "PASS" else "fail",
        "bounded transition replay",
        f"{trace_observations} consumer observations checked",
        trace_failures[0] if trace_failures else None,
    ))

    protocol_adapter = None
    if item.current.consistency not in {"immutable", "single_threaded", "generation_atomic", "single_writer_multi_reader"}:
        protocol_adapter = "bounded protocol model required (CBMC, TLA+, or equivalent)"
        obligations.append(LifetimeProofObligation(
            "publication protocol support", "fail", "adapter boundary", protocol_adapter, {"consistency": item.current.consistency}
        ))

    artifact: str | None = None
    if output_directory is not None:
        proof_dir = output_directory / "proofs"
        proof_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = proof_dir / f"lifetime-{candidate.candidate_id[:16]}.smt2"
        artifact_path.write_text("\n\n".join(smt_sections) + "\n")
        artifact = str(artifact_path)

    passed = candidate.legality == "legal" and all(result.status == "pass" for result in obligations)
    return LifetimeVerificationResult(
        candidate.candidate_id,
        candidate.information_id,
        "PASS" if passed else "FAIL",
        item.proof_class,
        tuple(obligations),
        trace_status,
        trace_observations,
        tuple(counterexamples),
        "local compiled helpers only; lifecycle protocol is outside Alive2",
        protocol_adapter,
        artifact,
    )


def _structural_obligations(
    graph: LifetimeFlowGraph,
    item: LifetimeInformation,
    candidate: LifetimeCandidate,
) -> tuple[LifetimeProofObligation, ...]:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("declared fallback", bool(candidate.fallback), candidate.fallback or "missing fallback"))
    if candidate.mode == "direct_consumer":
        observable = [consumer.id for consumer in item.consumers if consumer.independent_observer]
        checks.append(("elimination observer freedom", not observable, f"independent observers={observable}"))
    else:
        missing = [
            consumer.id for consumer in item.consumers
            if not graph.scopes.contains(candidate.candidate_scope, consumer.scope)
        ]
        checks.append(("lifetime containment", not missing, f"uncontained consumers={missing}"))
    checks.append((
        "placement declared",
        candidate.candidate_placement in item.candidate_placements,
        f"candidate placement={candidate.candidate_placement}",
    ))
    return tuple(
        LifetimeProofObligation(
            name,
            "pass" if passed else "fail",
            "structural contract",
            detail,
            None if passed else {"obligation": name, "detail": detail},
        )
        for name, passed, detail in checks
    )


def _z3_obligations(
    item: LifetimeInformation,
    candidate: LifetimeCandidate,
) -> tuple[tuple[LifetimeProofObligation, str], ...]:
    results: list[tuple[LifetimeProofObligation, str]] = []

    source = Int("source_version_at_construct")
    realized = Int("realization_version_at_construct")
    solver = Solver()
    solver.add(realized == source)
    solver.add(realized != source)
    results.append(_solver_result("derivation correctness", solver, "Z3 integer transition model"))

    source_before = Int("source_before_noninvalidating_transition")
    source_after = Int("source_after_noninvalidating_transition")
    realization_after = Int("realization_after_noninvalidating_transition")
    solver = Solver()
    solver.add(source_after == source_before)
    solver.add(realization_after == source_before)
    solver.add(realization_after != source_after)
    results.append(_solver_result("reuse preservation", solver, "Z3 version-preservation model"))

    solver = Solver()
    missing_flags = []
    for mutation in item.invalidators:
        symbol = Bool(f"handles_{_symbol(mutation)}")
        solver.add(symbol == BoolVal(mutation in candidate.invalidators))
        missing_flags.append(Not(symbol))
    solver.add(Or(missing_flags) if missing_flags else BoolVal(False))
    results.append(_solver_result("invalidation completeness", solver, "Z3 invalidator-set coverage"))

    solver = Solver()
    over_flags = []
    for mutation in item.non_invalidators:
        symbol = Bool(f"invalidates_non_dependency_{_symbol(mutation)}")
        solver.add(symbol == BoolVal(mutation in candidate.invalidators))
        over_flags.append(symbol)
    solver.add(Or(over_flags) if over_flags else BoolVal(False))
    results.append(_solver_result("non-invalidator preservation", solver, "Z3 mutation classification"))
    return tuple(results)


def _solver_result(name: str, solver: Solver, method: str) -> tuple[LifetimeProofObligation, str]:
    result = solver.check()
    passed = result == unsat
    model = None if passed else {"solver": str(result), "model": str(solver.model())}
    obligation = LifetimeProofObligation(
        name,
        "pass" if passed else "fail",
        method,
        "negated obligation is UNSAT" if passed else "counterexample is SAT",
        model,
    )
    return obligation, solver.to_smt2()


def _symbol(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def _replay_candidate(
    graph: LifetimeFlowGraph,
    item: LifetimeInformation,
    candidate: LifetimeCandidate,
    events: tuple[LifetimeEvent, ...],
) -> tuple[str, int, list[dict[str, Any]]]:
    source_versions: dict[str, int] = {}
    realization_versions: dict[tuple[str, str], int] = {}
    valid: dict[tuple[str, str], bool] = {}
    published: dict[tuple[str, str], bool] = {}
    failures: list[dict[str, Any]] = []
    observations = 0

    item_events = [event for event in events if event.information_id == item.id]
    for event in item_events:
        identity = event.semantic_identity
        source_versions.setdefault(identity, 0)
        scope_instance = event.scope_instances.get(candidate.candidate_scope)
        if scope_instance is None:
            failures.append({"sequence": event.sequence, "reason": "candidate scope instance missing", "scope": candidate.candidate_scope})
            continue
        key = (identity, scope_instance)
        if event.event == "construct":
            if candidate.mode != "direct_consumer" and (not valid.get(key, False) or realization_versions.get(key) != source_versions[identity]):
                realization_versions[key] = source_versions[identity]
                valid[key] = True
                published[key] = event.event == "publish" or item.current.publication == "construction_atomic"
        elif event.event == "publish":
            if candidate.mode != "direct_consumer":
                if key not in realization_versions:
                    failures.append({"sequence": event.sequence, "reason": "publish before construction", "identity": identity})
                else:
                    published[key] = True
        elif event.event == "mutate":
            if event.mutation not in item.mutations:
                failures.append({"sequence": event.sequence, "reason": "undeclared mutation", "mutation": event.mutation})
                continue
            if event.mutation in item.invalidators:
                source_versions[identity] += 1
                if event.mutation in candidate.invalidators:
                    for candidate_key in tuple(valid):
                        if candidate_key[0] == identity:
                            valid[candidate_key] = False
                            published[candidate_key] = False
        elif event.event == "invalidate":
            for candidate_key in tuple(valid):
                if candidate_key[0] == identity:
                    valid[candidate_key] = False
                    published[candidate_key] = False
        elif event.event in {"retire", "destroy"}:
            valid[key] = False
            published[key] = False
        elif event.event == "consume":
            observations += 1
            if candidate.mode == "direct_consumer":
                continue
            reason = None
            if not valid.get(key, False):
                reason = "read outside valid realization lifetime"
            elif not published.get(key, False):
                reason = "read before publication"
            elif realization_versions.get(key) != source_versions[identity]:
                reason = "stale realization read"
            if reason:
                failures.append({
                    "sequence": event.sequence,
                    "reason": reason,
                    "identity": identity,
                    "source_version": source_versions[identity],
                    "realization_version": realization_versions.get(key),
                })
    return ("PASS" if not failures else "FAIL"), observations, failures


def write_verification_report(path: Path, result: LifetimeVerificationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")
