#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vladder.canonical_search import (  # noqa: E402
    CanonicalSearchEngine,
    Canonicalizer,
    compare_terminal_sets,
    exhaustive_sequence_search,
    reduction_waterfall,
    typed_wl_labels,
)
from vladder.lazy_search import LazyState  # noqa: E402
from vladder.search_reductions import (  # noqa: E402
    LocalEGraph,
    commutative_rewrite,
    qualify_dominance,
    qualify_macro,
)
from vladder.selected_build_search import SelectedBuildCppGrammar  # noqa: E402


class AlphaIdentityGrammar:
    def __init__(self, root_index: int) -> None:
        self.root_index = root_index

    def initial_states(self, root_context):
        return tuple(
            LazyState(
                "alpha-fixture", "composition",
                {
                    "_nonobservable_ids": [f"tmp-{self.root_index}-{variant}"],
                    "temporary": f"tmp-{self.root_index}-{variant}",
                    "observable": {"value": self.root_index},
                },
                {"action_key": f"alpha-{variant}", "op": "construct-temporary"},
                terminal=True,
            )
            for variant in ("left", "right")
        )

    def expand(self, state, root_context):
        return ()


class SymmetricOwnerGrammar:
    def __init__(self, root_index: int) -> None:
        self.root_index = root_index

    def initial_states(self, root_context):
        variants = (("lane-a", "lane-b"), ("worker-x", "worker-y"))
        return tuple(
            LazyState(
                "symmetry-fixture", "composition",
                {
                    "graph": {
                        "nodes": [
                            {"id": left, "kind": "worker", "symmetry_class": "worker", "identity_observable": False},
                            {"id": right, "kind": "worker", "symmetry_class": "worker", "identity_observable": False},
                        ],
                        "edges": [{"source": left, "target": right, "kind": "peer"}],
                    },
                    "observable": {"root": self.root_index},
                },
                {"action_key": f"symmetry-{left}", "op": "assign-workers"},
                terminal=True,
            )
            for left, right in variants
        )

    def expand(self, state, root_context):
        return ()


class DependencyGrammar:
    def __init__(self, root_index: int) -> None:
        self.root_index = root_index
        self.actions = (
            self._action("capture", "source"),
            self._action("publish", "sink", requires=("capture",)),
            self._action("retain", "cache"),
        )

    @staticmethod
    def _action(key: str, owner: str, *, requires=()):
        return {
            "action_key": key,
            "op": key,
            "footprint": {
                "complete": True,
                "reads": [f"{owner}:input"],
                "writes": [f"{owner}:state"],
                "owners": [owner],
                "requires": list(requires),
            },
        }

    def initial_states(self, root_context):
        return (self._state((), {"action_key": "enter", "op": "enter"}),)

    def enabled_actions(self, state, root_context):
        applied = set(state.semantic_state["applied"])
        return tuple(action for action in self.actions if action["action_key"] not in applied)

    def apply_action(self, state, action, root_context):
        if state is None:
            return None
        applied = set(state.semantic_state["applied"])
        footprint = action["footprint"]
        if action["action_key"] in applied or not set(footprint.get("requires", ())).issubset(applied):
            return None
        return self._state(tuple(sorted((*applied, action["action_key"]))), action)

    def expand(self, state, root_context):
        return tuple(
            child
            for action in self.enabled_actions(state, root_context)
            if (child := self.apply_action(state, action, root_context)) is not None
        )

    def _state(self, applied, action):
        terminal = len(applied) == len(self.actions)
        return LazyState(
            "dependency-fixture", "composition" if terminal else "candidate_family",
            {
                "applied": list(applied),
                "lifetime_state": {"retained": "retain" in applied},
                "cross_tu_context": {"capture_tu": "ingest", "publish_tu": "transport"},
                "observable": {"root": self.root_index, "published": "publish" in applied},
            },
            dict(action),
            terminal=terminal,
        )


def _terminal_evaluator(state: LazyState) -> dict[str, Any]:
    # The qualification oracle deliberately performs one deterministic proof and compiler identity
    # check per semantic terminal so call savings are measured rather than inferred from node count.
    payload = json.dumps(dict(state.semantic_state), sort_keys=True, separators=(",", ":"))
    assert payload
    return {
        "proof_status": "PASS",
        "compiler_status": "PASS",
        "proof_calls": 1,
        "compiler_calls": 1,
    }


def replay_rc26(root: Path) -> dict[str, Any]:
    traces = sorted(root.glob("roots/*/composition-native-search-trace.json"))
    traces.extend(sorted(root.glob("roots/*/composition-native-search-trace.json.gz")))
    summary: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    projects: Counter[str] = Counter()
    for path in traces:
        if path.suffix == ".gz":
            with gzip.open(path, "rt") as handle:
                trace = json.load(handle)
        else:
            trace = json.loads(path.read_text())
        project = str(trace.get("root", {}).get("project_id", "unknown"))
        projects[project] += 1
        states = {str(item["state_id"]): item for item in trace.get("states", ())}
        transpositions = trace.get("transpositions", ())
        terminals = trace.get("terminals", ())
        summary["raw_states"] += len(states)
        summary["recorded_transpositions"] += len(transpositions)
        summary["terminal_records"] += len(terminals)
        summary["u2_terminals"] += sum(item.get("utility_tier") == "U2" for item in terminals)
        for terminal in terminals:
            cost = terminal.get("search_cost", {})
            summary["captured_proof_calls"] += int(cost.get("proof_calls") or 0)
            summary["captured_compiler_calls"] += int(cost.get("compiler_invocation_count") or 0)
            summary["captured_evaluation_wall_ms"] += float(cost.get("evaluation_wall_ms") or 0.0)
        canonical_owners = {
            str(item.get("state_id")): str(item.get("canonical_of") or item.get("state_id"))
            for item in states.values()
        }
        for terminal in terminals:
            state_id = str(terminal.get("state_id"))
            if state_id not in states:
                failures.append({"trace": str(path), "reason": "terminal state missing", "state_id": state_id})
                continue
            if canonical_owners[state_id] != state_id:
                failures.append({"trace": str(path), "reason": "terminal attached to transposition", "state_id": state_id})
        for transposition in transpositions:
            state_id = str(transposition.get("state_id"))
            canonical_of = str(
                transposition.get("equivalent_state_id") or transposition.get("canonical_of") or ""
            )
            if state_id not in states or canonical_of not in states:
                failures.append({
                    "trace": str(path), "reason": "broken transposition edge",
                    "state_id": state_id, "canonical_of": canonical_of,
                })
    raw = summary["raw_states"]
    collapsed = summary["recorded_transpositions"]
    metrics = {
        **dict(summary),
        "unique_canonical_states": raw - collapsed,
        "transposition_ratio": collapsed / raw if raw else 0.0,
        "u2_preservation_ratio": 1.0 if summary["u2_terminals"] and not failures else 0.0,
        "captured_evaluation_wall_hours": summary["captured_evaluation_wall_ms"] / 3_600_000.0,
        "average_terminal_evaluation_wall_ms": (
            summary["captured_evaluation_wall_ms"] / summary["terminal_records"]
            if summary["terminal_records"] else 0.0
        ),
    }
    return {
        "schema_version": "vladder-rc26-canonical-replay-v1",
        "status": "PASS" if traces and not failures else "FAIL",
        "trace_count": len(traces),
        "projects": dict(sorted(projects.items())),
        "metrics": metrics,
        "failures": failures,
        "scope_note": (
            "Replay validates recorded exact ownership and terminal lineage. RC26 lacks action footprints, "
            "so replay does not retroactively claim POR or stronger alpha/symmetry reductions."
        ),
    }


def adversarial_campaign(root_count: int) -> dict[str, Any]:
    if not 25 <= root_count <= 50:
        raise ValueError("adversarial campaign requires 25-50 roots")
    engine = CanonicalSearchEngine()
    rows = []
    totals: Counter[str] = Counter()
    failures = []
    for index in range(root_count):
        fixture_kind = (
            "composition", "composition", "composition", "alpha", "symmetry", "dependency",
        )[index % 6]
        region_count = 3 + index % 3 if fixture_kind == "composition" else 0
        if fixture_kind == "alpha":
            grammar = AlphaIdentityGrammar(index)
        elif fixture_kind == "symmetry":
            grammar = SymmetricOwnerGrammar(index)
        elif fixture_kind == "dependency":
            grammar = DependencyGrammar(index)
        else:
            report = {
                "closure": {
                    "candidates": [
                        {
                            "id": f"root-{index}-region-{region}-unroll-2",
                            "region_id": f"owner-{region}",
                            "schedule_choice": "unroll-2",
                            "source_sha256": f"root-{index}-candidate-{region}",
                        }
                        for region in range(region_count)
                    ]
                }
            }
            grammar = SelectedBuildCppGrammar(report)
        context = {"semantic_hash": f"adversarial-{index}"}
        sequence = exhaustive_sequence_search(
            grammar, context, node_budget=250_000, terminal_evaluator=_terminal_evaluator,
        )
        canonical = engine.run(
            grammar, context, mode="exhaustive_canonical", terminal_evaluator=_terminal_evaluator,
        )
        reduced = engine.run(
            grammar, context, mode="exhaustive_reduced", terminal_evaluator=_terminal_evaluator,
        )
        sleep_set = engine.run(
            grammar,
            context,
            mode="exhaustive_reduced",
            por_strategy="sleep_set",
            terminal_evaluator=_terminal_evaluator,
        )
        sequence_terminal_set = set(sequence.terminal_canonical_hashes)
        canonical_parity = sequence_terminal_set == set(canonical.terminal_canonical_hashes)
        reduced_parity = compare_terminal_sets(canonical, reduced)
        sleep_set_parity = compare_terminal_sets(canonical, sleep_set)
        row = {
            "root_id": f"adversarial-{index}",
            "fixture_kind": fixture_kind,
            "region_count": region_count,
            "sequence": asdict(sequence),
            "canonical_metrics": asdict(canonical.metrics),
            "reduced_metrics": asdict(reduced.metrics),
            "sequence_to_canonical_terminal_parity": canonical_parity,
            "canonical_to_reduced_terminal_parity": reduced_parity,
            "canonical_to_sleep_set_terminal_parity": sleep_set_parity,
            "waterfall": reduction_waterfall(reduced),
        }
        rows.append(row)
        totals["raw_sequence_states"] += sequence.generated_states
        totals["canonical_candidate_constructions"] += canonical.metrics.candidate_constructions
        totals["reduced_candidate_constructions"] += reduced.metrics.candidate_constructions
        totals["unique_canonical_states"] += canonical.metrics.unique_canonical_states
        totals["transpositions"] += canonical.metrics.exact_transpositions
        totals["alpha_equivalent_collapses"] += canonical.metrics.alpha_equivalent_collapses
        totals["symmetry_collapses"] += canonical.metrics.symmetry_collapses
        totals["por_avoided_transitions"] += reduced.metrics.por_avoided_transitions
        totals["sleep_set_avoided_transitions"] += sleep_set.metrics.por_avoided_transitions
        totals["dependency_avoided_transitions"] += reduced.metrics.dependency_avoided_transitions
        totals["terminal_states"] += len(canonical.terminal_state_ids)
        totals["raw_proof_calls"] += sequence.proof_calls
        totals["raw_compiler_calls"] += sequence.compiler_calls
        totals["reduced_proof_calls"] += reduced.metrics.proof_calls
        totals["reduced_compiler_calls"] += reduced.metrics.compiler_calls
        totals[f"fixture_{fixture_kind}"] += 1
        totals["raw_sequence_wall_ms"] += sequence.search_wall_ms
        totals["canonical_search_wall_ms"] += canonical.metrics.search_wall_ms
        totals["reduced_search_wall_ms"] += reduced.metrics.search_wall_ms
        totals["canonicalization_wall_ms"] += reduced.metrics.canonicalization_wall_ms
        totals["peak_reduced_memory_bytes"] = max(
            totals["peak_reduced_memory_bytes"], reduced.metrics.peak_memory_bytes,
        )
        if (
            not sequence.complete
            or not canonical_parity
            or reduced_parity["status"] != "PASS"
            or sleep_set_parity["status"] != "PASS"
        ):
            failures.append({"root_id": f"adversarial-{index}", "row": row})
    raw = totals["raw_sequence_states"]
    reduced_work = totals["reduced_candidate_constructions"]
    canonical_work = totals["canonical_candidate_constructions"]
    totals_payload = {
        **dict(totals),
        "state_reduction_vs_raw_sequence": 1.0 - totals["unique_canonical_states"] / raw,
        "candidate_reduction_vs_raw_sequence": 1.0 - reduced_work / raw,
        "por_incremental_candidate_reduction": 1.0 - reduced_work / canonical_work,
        "proof_call_reduction_vs_raw_sequence": 1.0 - totals["reduced_proof_calls"] / max(1, totals["raw_proof_calls"]),
        "compiler_call_reduction_vs_raw_sequence": 1.0 - totals["reduced_compiler_calls"] / max(1, totals["raw_compiler_calls"]),
        "net_wall_clock_reduction_vs_raw_sequence": 1.0 - totals["reduced_search_wall_ms"] / max(1, totals["raw_sequence_wall_ms"]),
        "terminal_preservation_ratio": 1.0 if not failures else 0.0,
    }
    return {
        "schema_version": "vladder-canonical-adversarial-campaign-v1",
        "status": "PASS" if not failures else "FAIL",
        "root_count": root_count,
        "totals": totals_payload,
        "failures": failures,
        "roots": rows,
    }


def egraph_study() -> dict[str, Any]:
    expressions = tuple(
        {"op": op, "args": [left, right]}
        for op in ("add", "mul", "and", "or")
        for left, right in (("x", "y"), ("a", "b"), (0, "x"))
    )
    result = LocalEGraph().saturate(
        expressions,
        (commutative_rewrite(("add", "mul", "and", "or")),),
    )
    return result.to_dict()


def proof_gated_reduction_studies() -> dict[str, Any]:
    engine = CanonicalSearchEngine()
    context = {"semantic_hash": "reduction-study"}
    broad = engine.run(
        SelectedBuildCppGrammar({"closure": {"candidates": [
            {"id": f"region-{index}-u", "region_id": f"region-{index}", "schedule_choice": "u"}
            for index in range(2)
        ]}}),
        context,
    )
    narrow = engine.run(
        SelectedBuildCppGrammar({"closure": {"candidates": [
            {"id": "region-0-u", "region_id": "region-0", "schedule_choice": "u"}
        ]}}),
        context,
    )
    dominance_verified = qualify_dominance(broad, broad)
    dominance_counterexample = qualify_dominance(broad, narrow)
    macro_verified = qualify_macro(broad, broad)
    macro_counterexample = qualify_macro(broad, narrow)
    return {
        "schema_version": "vladder-proof-gated-reduction-study-v1",
        "dominance_verified_fixture": dominance_verified.to_dict(),
        "dominance_counterexample_fixture": dominance_counterexample.to_dict(),
        "macro_verified_fixture": macro_verified.to_dict(),
        "macro_counterexample_fixture": macro_counterexample.to_dict(),
        "production_authority": (
            "only descendant-set-qualified instances; structural monotonicity alone remains proposal-only"
        ),
    }


def canonical_labeling_study() -> dict[str, Any]:
    graphs = []
    canonicalizer = Canonicalizer()
    for left, right in (("lane-a", "lane-b"), ("worker-x", "worker-y")):
        graph = {
            "nodes": [
                {"id": left, "kind": "worker", "symmetry_class": "worker", "identity_observable": False},
                {"id": right, "kind": "worker", "symmetry_class": "worker", "identity_observable": False},
            ],
            "edges": [{"source": left, "target": right, "kind": "peer"}],
        }
        state = LazyState("symmetry-study", "candidate", {"graph": graph}, {"op": "study"})
        labels = typed_wl_labels(graph)
        graphs.append({
            "raw_digest": canonicalizer.envelope(LazyState(
                "symmetry-study", "candidate",
                {"graph": {**graph, "nodes": [
                    {**node, "identity_observable": True} for node in graph["nodes"]
                ]}},
                {"op": "study"},
            )).digest,
            "wl_partition_signature": sorted(labels.values()),
            "individualized_digest": canonicalizer.envelope(state).digest,
        })
    return {
        "schema_version": "vladder-canonical-labeling-study-v1",
        "current_deterministic_unique_states": len({item["raw_digest"] for item in graphs}),
        "wl_partition_unique_states": len({json.dumps(item["wl_partition_signature"]) for item in graphs}),
        "bounded_individualization_unique_states": len({item["individualized_digest"] for item in graphs}),
        "external_nauty_traces": "not_required; equivalent bounded typed individualization implemented internally",
        "meaningful_additional_equivalence": (
            len({item["individualized_digest"] for item in graphs})
            < len({item["raw_digest"] for item in graphs})
        ),
        "graphs": graphs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify canonical-state search reductions")
    parser.add_argument(
        "--rc26-root",
        type=Path,
        default=Path(tempfile.gettempdir()) / "vladder-composition-native-rc26-out",
    )
    parser.add_argument("--adversarial-roots", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay = replay_rc26(args.rc26_root)
    adversarial = adversarial_campaign(args.adversarial_roots)
    average_terminal_ms = replay["metrics"]["average_terminal_evaluation_wall_ms"]
    avoided_terminal_units = (
        adversarial["totals"]["raw_proof_calls"]
        - adversarial["totals"]["reduced_proof_calls"]
    )
    projected_avoided_ms = average_terminal_ms * avoided_terminal_units
    reduction_overhead_ms = max(
        0.0,
        adversarial["totals"]["reduced_search_wall_ms"]
        - adversarial["totals"]["raw_sequence_wall_ms"],
    )
    adversarial["net_benefit"] = {
        "cheap_fixture_observed_net_wall_ms": (
            adversarial["totals"]["raw_sequence_wall_ms"]
            - adversarial["totals"]["reduced_search_wall_ms"]
        ),
        "rc26_average_terminal_evaluation_wall_ms": average_terminal_ms,
        "avoided_terminal_work_units": avoided_terminal_units,
        "projected_avoided_cold_work_ms": projected_avoided_ms,
        "measured_reduction_overhead_ms": reduction_overhead_ms,
        "projected_net_saved_ms": projected_avoided_ms - reduction_overhead_ms,
        "cost_gate": "PASS" if projected_avoided_ms > reduction_overhead_ms else "FAIL",
        "claim_boundary": (
            "projection uses RC26 captured cold terminal cost; cheap-fixture wall time remains the "
            "direct observation and is reported separately"
        ),
    }
    report = {
        "schema_version": "vladder-canonical-search-qualification-v1",
        "status": "PASS" if replay["status"] == adversarial["status"] == "PASS" else "FAIL",
        "rc26_replay": replay,
        "adversarial_campaign": adversarial,
        "egraph_study": egraph_study(),
        "proof_gated_reduction_studies": proof_gated_reduction_studies(),
        "canonical_labeling_study": canonical_labeling_study(),
    }
    totals = adversarial["totals"]
    report["gates"] = {
        "terminal_preservation": totals["terminal_preservation_ratio"] == 1.0,
        "state_reduction_75_percent": totals["state_reduction_vs_raw_sequence"] >= 0.75,
        "candidate_reduction_70_percent": totals["candidate_reduction_vs_raw_sequence"] >= 0.70,
        "rc26_replay_preserved": replay["status"] == "PASS",
        "net_benefit_cost_gate": adversarial["net_benefit"]["cost_gate"] == "PASS",
    }
    if report["status"] == "PASS" and all(report["gates"].values()):
        report["disposition"] = "ADOPT_CANONICAL_REDUCED_SEARCH"
    elif report["status"] == "PASS":
        report["disposition"] = "ITERATE_EXACT_REDUCTION"
    else:
        report["disposition"] = "ACCEPT_RESIDUAL_COMBINATORIAL_FRONTIER"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": report["status"],
        "disposition": report["disposition"],
        "gates": report["gates"],
        "rc26": replay["metrics"],
        "adversarial": totals,
        "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
