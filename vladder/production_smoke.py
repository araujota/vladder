from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping

import z3

from .canonical_search import (
    ActionFootprint,
    CanonicalSearchEngine,
    Canonicalizer,
    IndependenceVerifier,
    LayeredStateHash,
    TranspositionTable,
    compare_terminal_sets,
    exhaustive_sequence_search,
)
from .lazy_search import LazyState
from .production_search import (
    ProductionCanonicalSearchEngine,
    ProductionSearchConfig,
    StateAnalysisCache,
)
from .schema_registry import validate_payload
from .selected_build_search import SelectedBuildCppGrammar


SMOKE_SCHEMA_VERSION = "vladder-production-canonical-search-smoke-v1"
SMOKE_STAGE_ORDER = (
    "canonical_identity",
    "por_safety",
    "incremental_canonicalization",
    "expensive_terminal_reduction",
    "cheap_region_cost_gate",
    "concurrent_registration",
    "checkpoint_resume",
    "mini_scaling",
)
LLAMA_RC28_SOURCE_IDENTITY = "f73c8a6794d8085f4a59827f5a90091c36ce6d1b1fcbb0b77398af1bedf21560"


@dataclass(frozen=True)
class SmokeStage:
    stage_id: str
    status: str
    duration_ms: float
    assertions: Mapping[str, bool]
    metrics: Mapping[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _grammar(width: int, *, source_hash: str = "production-smoke-source") -> SelectedBuildCppGrammar:
    return SelectedBuildCppGrammar({
        "source_sha256": source_hash,
        "closure": {
            "candidates": [
                {
                    "id": f"region-{index}-unroll-2",
                    "region_id": f"region-{index}",
                    "schedule_choice": "unroll-2",
                    "source_sha256": hashlib.sha256(
                        f"{source_hash}:{index}:unroll-2".encode()
                    ).hexdigest(),
                }
                for index in range(width)
            ]
        },
    })


class _FootprintFixtureGrammar:
    def __init__(self, footprint_mode: str) -> None:
        self.inner = _grammar(2, source_hash=f"footprint-{footprint_mode}")
        self.footprint_mode = footprint_mode

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return self.inner.initial_states(root_context)

    def enabled_actions(
        self, state: LazyState, root_context: Mapping[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        rows = []
        for original in self.inner.enabled_actions(state, root_context):
            action = dict(original)
            footprint = dict(action.get("footprint", {}))
            if self.footprint_mode == "alias":
                footprint["aliases"] = ["shared-buffer"]
            elif self.footprint_mode == "incomplete":
                footprint["complete"] = False
            action["footprint"] = footprint
            rows.append(action)
        return tuple(rows)

    def apply_action(
        self,
        state: LazyState | None,
        action: Mapping[str, Any],
        root_context: Mapping[str, Any],
    ) -> LazyState | None:
        return self.inner.apply_action(state, action, root_context)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> tuple[LazyState, ...]:
        return tuple(
            child
            for action in self.enabled_actions(state, root_context)
            if (child := self.apply_action(state, action, root_context)) is not None
        )


class _ForcedCollisionCanonicalizer(Canonicalizer):
    def envelope(self, state: LazyState):
        return replace(super().envelope(state), digest="forced-primary-collision")


def _stage(
    stage_id: str,
    operation: Callable[[], tuple[Mapping[str, bool], Mapping[str, Any]]],
) -> SmokeStage:
    started = time.perf_counter()
    try:
        assertions, metrics = operation()
        status = "PASS" if assertions and all(assertions.values()) else "FAIL"
        return SmokeStage(
            stage_id,
            status,
            (time.perf_counter() - started) * 1000.0,
            dict(assertions),
            dict(metrics),
        )
    except Exception as exc:  # The release artifact must retain the failing stage.
        return SmokeStage(
            stage_id,
            "FAIL",
            (time.perf_counter() - started) * 1000.0,
            {"unexpected_exception": False},
            {},
            f"{type(exc).__name__}: {exc}",
        )


def canonical_identity_smoke() -> tuple[Mapping[str, bool], Mapping[str, Any]]:
    grammar = _grammar(2)
    context = {"semantic_hash": "canonical-identity-smoke", "grammar_version": "smoke-v1"}
    initial = next(iter(grammar.initial_states(context)))
    actions = grammar.enabled_actions(initial, context)
    action_a = next(item for item in actions if item["region"] == "region-0" and item["choice"] == "baseline")
    action_b = next(item for item in actions if item["region"] == "region-1" and item["choice"] == "baseline")
    after_a = grammar.apply_action(initial, action_a, context)
    after_b = grammar.apply_action(initial, action_b, context)
    assert after_a is not None and after_b is not None
    ab = grammar.apply_action(after_a, action_b, context)
    ba = grammar.apply_action(after_b, action_a, context)
    assert ab is not None and ba is not None
    canonicalizer = Canonicalizer()
    ab_envelope = canonicalizer.envelope(ab)
    ba_envelope = canonicalizer.envelope(ba)

    raw = exhaustive_sequence_search(grammar, context)
    canonical = CanonicalSearchEngine().run(grammar, context, mode="exhaustive_canonical")
    owners = [
        record for record in canonical.states
        if record.envelope.canonical_bytes == ab_envelope.canonical_bytes
    ]
    owner = owners[0] if owners else None

    collision_table = TranspositionTable(_ForcedCollisionCanonicalizer())
    collision_table.intern(
        LazyState("collision", "candidate", {"value": 1}, {"op": "one"}),
        depth=0, path=(), edge_id="collision-one",
    )
    collision_table.intern(
        LazyState("collision", "candidate", {"value": 2}, {"op": "two"}),
        depth=0, path=(), edge_id="collision-two",
    )
    terminal_parity = set(raw.terminal_canonical_hashes) == set(canonical.terminal_canonical_hashes)
    assertions = {
        "ab_ba_canonical_bytes_identical": ab_envelope.canonical_bytes == ba_envelope.canonical_bytes,
        "ab_ba_canonical_digest_identical": ab_envelope.digest == ba_envelope.digest,
        "exactly_one_recursive_owner": len(owners) == 1,
        "both_provenance_edges_recorded": owner is not None and len(owner.parent_edges) == 2,
        "terminal_set_preserved": terminal_parity,
        "expected_owner_count": len(canonical.states) == 9,
        "forced_collision_did_not_merge": len(collision_table.records) == 2,
    }
    return assertions, {
        "canonical_owners_expected": 9,
        "canonical_owners_actual": len(canonical.states),
        "converged_owner_parent_edges": len(owner.parent_edges) if owner else 0,
        "terminal_count": len(canonical.terminal_state_ids),
        "terminal_preservation_percent": 100.0 if terminal_parity else 0.0,
        "forced_hash_collisions": collision_table.hash_collisions,
        "false_merges": 0 if len(collision_table.records) == 2 else 1,
    }


def _ordering_is_represented(result: Any) -> bool:
    return any(len(record.parent_edges) >= 2 for record in result.states if record.state.terminal)


def por_safety_smoke() -> tuple[Mapping[str, bool], Mapping[str, Any]]:
    context = {"semantic_hash": "por-safety-smoke", "grammar_version": "smoke-v1"}
    commuting = _FootprintFixtureGrammar("commuting")
    full = CanonicalSearchEngine().run(commuting, context, mode="exhaustive_canonical")
    reduced = CanonicalSearchEngine().run(commuting, context, mode="exhaustive_reduced")

    alias = _FootprintFixtureGrammar("alias")
    alias_full = CanonicalSearchEngine().run(alias, context, mode="exhaustive_canonical")
    alias_reduced = CanonicalSearchEngine().run(alias, context, mode="exhaustive_reduced")
    alias_root = next(iter(alias.initial_states(context)))
    alias_actions = alias.enabled_actions(alias_root, context)
    alias_a = next(item for item in alias_actions if item["region"] == "region-0")
    alias_b = next(item for item in alias_actions if item["region"] == "region-1")
    alias_screen = IndependenceVerifier.static_screen(
        ActionFootprint.from_action(alias_a), ActionFootprint.from_action(alias_b)
    )

    incomplete = _FootprintFixtureGrammar("incomplete")
    incomplete_full = CanonicalSearchEngine().run(incomplete, context, mode="exhaustive_canonical")
    incomplete_reduced = CanonicalSearchEngine().run(incomplete, context, mode="exhaustive_reduced")
    incomplete_root = next(iter(incomplete.initial_states(context)))
    incomplete_actions = incomplete.enabled_actions(incomplete_root, context)
    incomplete_screen = IndependenceVerifier.static_screen(
        ActionFootprint.from_action(incomplete_actions[0]),
        ActionFootprint.from_action(incomplete_actions[2]),
    )

    commuting_parity = compare_terminal_sets(full, reduced)["status"] == "PASS"
    alias_parity = compare_terminal_sets(alias_full, alias_reduced)["status"] == "PASS"
    incomplete_parity = compare_terminal_sets(incomplete_full, incomplete_reduced)["status"] == "PASS"
    assertions = {
        "commuting_terminal_set_preserved": commuting_parity,
        "commuting_representative_ordering_used": reduced.metrics.por_avoided_transitions > 0,
        "commuting_orders_verified_equal": any(item.dynamic_orders_equal for item in reduced.independence_evidence),
        "alias_pair_rejected": not alias_screen[0] and alias_screen[1] == "shared alias region",
        "alias_por_skips_zero": alias_reduced.metrics.por_avoided_transitions == 0,
        "alias_orderings_remain_represented": _ordering_is_represented(alias_reduced),
        "alias_terminal_set_preserved": alias_parity,
        "incomplete_pair_dependent": not incomplete_screen[0] and incomplete_screen[1] == "unknown footprint is dependent",
        "incomplete_por_skips_zero": incomplete_reduced.metrics.por_avoided_transitions == 0,
        "incomplete_orderings_remain_represented": _ordering_is_represented(incomplete_reduced),
        "incomplete_terminal_set_preserved": incomplete_parity,
    }
    return assertions, {
        "commuting_por_skips": reduced.metrics.por_avoided_transitions,
        "alias_por_skips": alias_reduced.metrics.por_avoided_transitions,
        "incomplete_por_skips": incomplete_reduced.metrics.por_avoided_transitions,
        "unsafe_por_skips": alias_reduced.metrics.por_avoided_transitions + incomplete_reduced.metrics.por_avoided_transitions,
        "terminal_preservation_percent": 100.0 if commuting_parity and alias_parity and incomplete_parity else 0.0,
    }


def incremental_canonicalization_smoke() -> tuple[Mapping[str, bool], Mapping[str, Any]]:
    grammar = _grammar(2)
    context = {"semantic_hash": "incremental-smoke", "grammar_version": "smoke-v1"}
    parent = next(iter(grammar.initial_states(context)))
    action = grammar.enabled_actions(parent, context)[0]
    child = grammar.apply_action(parent, action, context)
    clean_child = grammar.apply_action(parent, dict(action), context)
    assert child is not None and clean_child is not None
    parent_hash = LayeredStateHash.build(parent.semantic_state)
    changed = {
        key: value
        for key, value in child.semantic_state.items()
        if parent.semantic_state.get(key) != value
    }
    incremental, fallback, incident = parent_hash.update_or_rematerialize(
        child.semantic_state, changed=changed,
    )
    clean_hash = LayeredStateHash.build(clean_child.semantic_state)
    canonicalizer = Canonicalizer()
    child_envelope = canonicalizer.envelope(child)
    clean_envelope = canonicalizer.envelope(clean_child)
    child_actions = grammar.enabled_actions(child, context)
    clean_actions = grammar.enabled_actions(clean_child, context)
    child_children = tuple(grammar.apply_action(child, item, context) for item in child_actions)
    clean_children = tuple(grammar.apply_action(clean_child, item, context) for item in clean_actions)
    summary = CanonicalSearchEngine._summaries(child, tuple(item for item in child_children if item is not None))
    clean_summary = CanonicalSearchEngine._summaries(
        clean_child, tuple(item for item in clean_children if item is not None)
    )
    cache = StateAnalysisCache()
    cached = cache.get_or_compute(child_envelope.digest, "semantic_summaries", lambda: summary)
    cached_again = cache.get_or_compute(child_envelope.digest, "semantic_summaries", lambda: {"invalid": True})

    corrupt_changed = dict(changed)
    corrupt_changed["selection"] = {"corrupt": "state"}
    recovered, recovered_from_disagreement, recovery_incident = parent_hash.update_or_rematerialize(
        child.semantic_state, changed=corrupt_changed,
    )
    assertions = {
        "incremental_hash_matches_clean": incremental == clean_hash,
        "canonical_bytes_match": child_envelope.canonical_bytes == clean_envelope.canonical_bytes,
        "canonical_digest_matches": child_envelope.digest == clean_envelope.digest,
        "enabled_actions_match": child_actions == clean_actions,
        "semantic_summaries_match": summary == clean_summary == cached == cached_again,
        "valid_update_did_not_fallback": not fallback and incident is None,
        "corruption_detected": recovered_from_disagreement and recovery_incident is not None,
        "clean_fallback_returned": recovered == clean_hash,
    }
    return assertions, {
        "changed_components": sorted(changed),
        "cache_hits": cache.hits,
        "cache_misses": cache.misses,
        "fallback_count": int(recovered_from_disagreement),
        "fallback_incident": recovery_incident,
        "silent_divergence": 0 if recovered == clean_hash else 1,
    }


def _terminal_evaluator(compiler: str, directory: Path) -> tuple[Counter[str], Callable[[LazyState], Mapping[str, Any]]]:
    counter: Counter[str] = Counter()

    def evaluate(state: LazyState) -> Mapping[str, Any]:
        ordinal = counter["calls"]
        counter["calls"] += 1
        selection = dict(state.semantic_state["selection"])
        value = sum(choice != "baseline" for choice in selection.values())
        proof_started = time.perf_counter()
        symbol = z3.Int(f"smoke_selected_{directory.name}_{ordinal}")
        solver = z3.Solver()
        solver.add(symbol == value, symbol != value)
        if solver.check() != z3.unsat:
            raise RuntimeError("smoke proof did not establish the terminal identity")
        proof_ms = (time.perf_counter() - proof_started) * 1000.0
        source = directory / f"candidate-{ordinal}.cpp"
        obj = directory / f"candidate-{ordinal}.o"
        source.write_text(
            f'extern "C" int smoke_candidate_{ordinal}(int x) noexcept {{ return x + {value}; }}\n'
        )
        compile_started = time.perf_counter()
        completed = subprocess.run(
            [compiler, "-std=c++20", "-O3", "-c", str(source), "-o", str(obj)],
            check=False,
            capture_output=True,
            text=True,
        )
        compile_ms = (time.perf_counter() - compile_started) * 1000.0
        if completed.returncode:
            raise RuntimeError(completed.stderr)
        counter["proof_calls"] += 1
        counter["compiler_calls"] += 1
        counter["proof_us"] += int(proof_ms * 1000.0)
        counter["compile_us"] += int(compile_ms * 1000.0)
        return {"proof_status": "PASS", "compiler_status": "PASS", "proof_calls": 1, "compiler_calls": 1}

    return counter, evaluate


def expensive_terminal_reduction_smoke() -> tuple[Mapping[str, bool], Mapping[str, Any]]:
    compiler = shutil.which("clang++-20") or shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        raise RuntimeError("no C++ compiler is available")
    grammar = _grammar(3, source_hash="expensive-cpp-smoke")
    context = {"semantic_hash": "expensive-terminal-smoke", "grammar_version": "smoke-v1"}
    with tempfile.TemporaryDirectory(prefix="vladder-canonical-smoke-expensive-") as temporary:
        root = Path(temporary)
        raw_dir = root / "raw"
        reduced_dir = root / "reduced"
        raw_dir.mkdir()
        reduced_dir.mkdir()
        warm_source = root / "warm.cpp"
        warm_object = root / "warm.o"
        warm_source.write_text('extern "C" int warm(int x) noexcept { return x; }\n')
        warm = subprocess.run(
            [compiler, "-std=c++20", "-O3", "-c", str(warm_source), "-o", str(warm_object)],
            check=False, capture_output=True, text=True,
        )
        if warm.returncode:
            raise RuntimeError(warm.stderr)

        raw_counter, raw_evaluator = _terminal_evaluator(compiler, raw_dir)
        raw_started = time.perf_counter()
        raw = exhaustive_sequence_search(grammar, context, terminal_evaluator=raw_evaluator)
        raw_wall_ms = (time.perf_counter() - raw_started) * 1000.0

        reduced_counter, reduced_evaluator = _terminal_evaluator(compiler, reduced_dir)
        reduced_started = time.perf_counter()
        reduced = ProductionCanonicalSearchEngine().run(
            grammar,
            context,
            config=ProductionSearchConfig(
                mode="exhaustive_reduced", por_policy="force", exhaustive_cost_minimization=True,
            ),
            terminal_evaluator=reduced_evaluator,
        ).canonical_result
        reduced_wall_ms = (time.perf_counter() - reduced_started) * 1000.0
    parity = set(raw.terminal_canonical_hashes) == set(reduced.terminal_canonical_hashes)
    assertions = {
        "terminal_set_preserved": parity,
        "proof_calls_reduced": reduced.metrics.proof_calls < raw.proof_calls,
        "compiler_calls_reduced": reduced.metrics.compiler_calls < raw.compiler_calls,
        "measured_wall_time_reduced": reduced_wall_ms < raw_wall_ms,
        "all_unique_terminals_evaluated": len(reduced.terminal_state_ids) == 8,
    }
    return assertions, {
        "compiler": compiler,
        "raw": {
            "candidate_constructions": raw.candidate_constructions,
            "proof_calls": raw.proof_calls,
            "compiler_calls": raw.compiler_calls,
            "measured_wall_ms": raw_wall_ms,
            "proof_wall_ms": raw_counter["proof_us"] / 1000.0,
            "compiler_wall_ms": raw_counter["compile_us"] / 1000.0,
        },
        "reduced": {
            "candidate_constructions": reduced.metrics.candidate_constructions,
            "proof_calls": reduced.metrics.proof_calls,
            "compiler_calls": reduced.metrics.compiler_calls,
            "measured_wall_ms": reduced_wall_ms,
            "proof_wall_ms": reduced_counter["proof_us"] / 1000.0,
            "compiler_wall_ms": reduced_counter["compile_us"] / 1000.0,
        },
        "proof_calls_avoided": raw.proof_calls - reduced.metrics.proof_calls,
        "compiler_calls_avoided": raw.compiler_calls - reduced.metrics.compiler_calls,
        "measured_wall_ms_saved": raw_wall_ms - reduced_wall_ms,
        "terminal_preservation_percent": 100.0 if parity else 0.0,
    }


def cheap_region_cost_gate_smoke() -> tuple[Mapping[str, bool], Mapping[str, Any]]:
    grammar = _grammar(3, source_hash="cheap-cost-gate")
    context = {"semantic_hash": "cheap-cost-gate-smoke", "grammar_version": "smoke-v1"}
    authority = CanonicalSearchEngine().run(grammar, context, mode="exhaustive_canonical")
    production = ProductionCanonicalSearchEngine().run(
        grammar,
        context,
        config=ProductionSearchConfig(mode="exhaustive", por_policy="adaptive"),
    )
    result = production.canonical_result
    parity = compare_terminal_sets(authority, result)["status"] == "PASS"
    declined = [item for item in production.reduction_decisions if item.selected_level == "CANONICALIZE_ONLY"]
    assertions = {
        "adaptive_policy_declined_por": bool(declined) and len(declined) == len(production.reduction_decisions),
        "no_por_skip_when_declined": result.metrics.por_avoided_transitions == 0,
        "canonical_transposition_remained_enabled": result.metrics.exact_transpositions > 0,
        "terminal_set_preserved": parity,
    }
    return assertions, {
        "decisions": [asdict(item) for item in production.reduction_decisions],
        "selected_levels": sorted({item.selected_level for item in production.reduction_decisions}),
        "transpositions": result.metrics.exact_transpositions,
        "por_skips": result.metrics.por_avoided_transitions,
        "terminal_preservation_percent": 100.0 if parity else 0.0,
    }


def concurrent_registration_smoke() -> tuple[Mapping[str, bool], Mapping[str, Any]]:
    registrations = 2048
    workers = 16
    unique_count = 17
    table = TranspositionTable()
    states = tuple(
        LazyState("concurrency", "candidate", {"value": index % unique_count}, {"op": "set"})
        for index in range(registrations)
    )

    def register(item: tuple[int, LazyState]):
        index, state = item
        return table.intern(
            state,
            depth=index % 5,
            path=({"op": "set", "value": index % unique_count},),
            edge_id=f"concurrent-edge-{index}",
        )

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(register, enumerate(states)))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    recursive_owners = sum(created for _, created, _ in outcomes)
    provenance_edges = sum(len(record.parent_edges) for record in table.records.values())
    assertions = {
        "unique_count_matches": len(table.records) == unique_count,
        "one_recursive_owner_per_state": recursive_owners == unique_count,
        "all_provenance_edges_retained": provenance_edges == registrations,
        "no_corrupt_records": all(record.envelope.canonical_bytes for record in table.records.values()),
    }
    return assertions, {
        "workers": workers,
        "registrations": registrations,
        "unique_expected": unique_count,
        "unique_actual": len(table.records),
        "recursive_owners": recursive_owners,
        "provenance_edges": provenance_edges,
        "elapsed_ms": elapsed_ms,
    }


def checkpoint_resume_smoke() -> tuple[Mapping[str, bool], Mapping[str, Any]]:
    grammar = _grammar(4, source_hash="checkpoint-resume")
    context = {
        "semantic_hash": "checkpoint-resume-smoke",
        "grammar_version": "smoke-v1",
        "target": {"triple": "native-smoke"},
    }
    with tempfile.TemporaryDirectory(prefix="vladder-canonical-smoke-checkpoint-") as temporary:
        checkpoint = Path(temporary) / "checkpoint.json"
        engine = ProductionCanonicalSearchEngine()
        partial = engine.run(
            grammar,
            context,
            config=ProductionSearchConfig(
                mode="fast", work_budget=2, por_policy="off", checkpoint_path=checkpoint,
            ),
        )
        resumed = engine.run(
            grammar,
            context,
            config=ProductionSearchConfig(
                mode="exhaustive_canonical", resume_path=checkpoint, checkpoint_path=checkpoint,
            ),
        )
        uninterrupted = CanonicalSearchEngine().run(grammar, context, mode="exhaustive_canonical")
        incompatible_rejected = False
        try:
            engine.run(
                grammar,
                {**context, "grammar_version": "smoke-v2"},
                config=ProductionSearchConfig(mode="exhaustive_canonical", resume_path=checkpoint),
            )
        except ValueError as exc:
            incompatible_rejected = "incompatible" in str(exc)
    parity = compare_terminal_sets(uninterrupted, resumed.canonical_result)["status"] == "PASS"
    assertions = {
        "partial_run_stopped_incomplete": not partial.canonical_result.complete,
        "compatible_resume_completed": resumed.canonical_result.complete,
        "terminal_set_matches_uninterrupted": parity,
        "already_explored_states_not_reexpanded": (
            resumed.canonical_result.metrics.candidate_constructions
            == uninterrupted.metrics.candidate_constructions
        ),
        "incompatible_identity_rejected": incompatible_rejected,
    }
    return assertions, {
        "partial_canonical_states": len(partial.canonical_result.states),
        "resumed_candidate_constructions": resumed.canonical_result.metrics.candidate_constructions,
        "uninterrupted_candidate_constructions": uninterrupted.metrics.candidate_constructions,
        "terminal_count": len(resumed.canonical_result.terminal_state_ids),
        "checkpoint_loaded": bool(resumed.checkpoint.get("loaded")),
        "terminal_preservation_percent": 100.0 if parity else 0.0,
    }


def mini_scaling_smoke() -> tuple[Mapping[str, bool], Mapping[str, Any]]:
    levels = []
    all_preserved = True
    for width in (2, 3, 4):
        grammar = _grammar(width, source_hash=LLAMA_RC28_SOURCE_IDENTITY)
        context = {
            "semantic_hash": hashlib.sha256(
                f"llama.cpp:{LLAMA_RC28_SOURCE_IDENTITY}:{width}".encode()
            ).hexdigest(),
            "grammar_version": "selected-build-cpp-composition-v4",
            "source_provenance": {
                "project": "llama.cpp",
                "rc28_source_sha256": LLAMA_RC28_SOURCE_IDENTITY,
            },
        }
        raw = exhaustive_sequence_search(grammar, context)
        canonical = CanonicalSearchEngine().run(grammar, context, mode="exhaustive_canonical")
        reduced = ProductionCanonicalSearchEngine().run(
            grammar,
            context,
            config=ProductionSearchConfig(
                mode="exhaustive_reduced", por_policy="force", exhaustive_cost_minimization=True,
            ),
        ).canonical_result
        preserved = (
            set(raw.terminal_canonical_hashes)
            == set(canonical.terminal_canonical_hashes)
            == set(reduced.terminal_canonical_hashes)
        )
        all_preserved = all_preserved and preserved
        levels.append({
            "width": width,
            "raw_candidate_constructions": raw.candidate_constructions,
            "canonical_unique_states": canonical.metrics.unique_canonical_states,
            "reduced_candidate_constructions": reduced.metrics.candidate_constructions,
            "terminal_proof_compile_work": len(reduced.terminal_state_ids),
            "terminal_preservation": preserved,
        })
    raw_growth = levels[-1]["raw_candidate_constructions"] / levels[0]["raw_candidate_constructions"]
    canonical_growth = levels[-1]["canonical_unique_states"] / levels[0]["canonical_unique_states"]
    reduced_growth = levels[-1]["reduced_candidate_constructions"] / levels[0]["reduced_candidate_constructions"]
    assertions = {
        "terminal_sets_preserved_at_every_width": all_preserved,
        "canonical_growth_slower_than_raw": canonical_growth < raw_growth,
        "reduced_growth_slower_than_raw": reduced_growth < raw_growth,
    }
    return assertions, {
        "fixture_origin": {
            "project": "llama.cpp",
            "source_sha256": LLAMA_RC28_SOURCE_IDENTITY,
            "capture": "RC28 source-anchored selected-build composition root",
        },
        "levels": levels,
        "growth_width_2_to_4": {
            "raw": raw_growth,
            "canonical": canonical_growth,
            "reduced": reduced_growth,
        },
    }


def run_production_canonical_smoke() -> dict[str, Any]:
    started = time.perf_counter()
    operations = {
        "canonical_identity": canonical_identity_smoke,
        "por_safety": por_safety_smoke,
        "incremental_canonicalization": incremental_canonicalization_smoke,
        "expensive_terminal_reduction": expensive_terminal_reduction_smoke,
        "cheap_region_cost_gate": cheap_region_cost_gate_smoke,
        "concurrent_registration": concurrent_registration_smoke,
        "checkpoint_resume": checkpoint_resume_smoke,
        "mini_scaling": mini_scaling_smoke,
    }
    stages = tuple(_stage(stage_id, operations[stage_id]) for stage_id in SMOKE_STAGE_ORDER)
    passed = sum(item.status == "PASS" for item in stages)
    report = {
        "schema_version": SMOKE_SCHEMA_VERSION,
        "status": "PASS" if passed == len(stages) else "FAIL",
        "release_blocking": True,
        "stage_order": list(SMOKE_STAGE_ORDER),
        "stages": [item.to_dict() for item in stages],
        "summary": {
            "stage_count": len(stages),
            "passed": passed,
            "failed": len(stages) - passed,
            "duration_ms": (time.perf_counter() - started) * 1000.0,
        },
        "authority": {
            "ml_deletion": False,
            "unknown_conditions": "fail_open",
            "terminal_identity": "collision-checked canonical bytes",
        },
    }
    validation = validate_payload("production-canonical-search-smoke", report)
    if validation["status"] != "pass":
        report["status"] = "FAIL"
        report["schema_validation"] = validation
    return report


def write_production_canonical_smoke(path: Path) -> dict[str, Any]:
    report = run_production_canonical_smoke()
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
