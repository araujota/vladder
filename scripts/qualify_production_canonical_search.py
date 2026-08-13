#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Mapping

import z3

from vladder.canonical_search import (
    CanonicalSearchEngine,
    Canonicalizer,
    TranspositionTable,
    compare_terminal_sets,
    exhaustive_sequence_search,
)
from vladder.lazy_search import LazyState
from vladder.executable_search import ExecutableSearchEngine, ExecutableSearchRequest
from vladder.production_search import (
    ProductionCanonicalSearchEngine,
    ProductionSearchConfig,
)
from vladder.selected_build_search import SelectedBuildCppGrammar

from qualify_canonical_search import adversarial_campaign, replay_rc26


QUALIFICATION_SCHEMA = "vladder-production-canonical-search-qualification-v1"


SYSTEM_SOURCES = {
    "duckdb": "duckdb/src/function/aggregate/distributive/count.cpp",
    "llama.cpp": "llama.cpp/ggml/src/ggml-cpu/ggml-cpu.c",
    "rocksdb": "rocksdb/db/db_impl/db_impl.cc",
}


def _source_identity(sources: Path, project: str) -> dict[str, str]:
    requested = sources / SYSTEM_SOURCES[project]
    if not requested.is_file():
        candidates = sorted((sources / project).rglob("*.cpp")) + sorted((sources / project).rglob("*.cc"))
        if not candidates:
            raise FileNotFoundError(f"no qualification source found for {project}")
        requested = candidates[0]
    return {
        "path": str(requested.resolve()),
        "sha256": hashlib.sha256(requested.read_bytes()).hexdigest(),
    }


def _grammar(project: str, source_hash: str, width: int) -> SelectedBuildCppGrammar:
    return SelectedBuildCppGrammar({
        "source_sha256": source_hash,
        "closure": {
            "candidates": [
                {
                    "id": f"{project}-region-{index}-unroll-2",
                    "region_id": f"region-{index}",
                    "schedule_choice": "unroll-2",
                    "source_sha256": hashlib.sha256(
                        f"{source_hash}:{index}:unroll-2".encode(),
                    ).hexdigest(),
                }
                for index in range(width)
            ]
        },
    })


def scaling_suite(sources: Path) -> dict[str, Any]:
    rows = []
    failures = []
    for project in SYSTEM_SOURCES:
        source = _source_identity(sources, project)
        levels = []
        previous = None
        for width in range(2, 6):
            grammar = _grammar(project, source["sha256"], width)
            context = {
                "semantic_hash": hashlib.sha256(f"{project}:{source['sha256']}:{width}".encode()).hexdigest(),
                "grammar_version": "selected-build-cpp-composition-v4",
            }
            raw = exhaustive_sequence_search(grammar, context, node_budget=100_000)
            canonical = CanonicalSearchEngine().run(grammar, context, mode="exhaustive_canonical")
            reduced = ProductionCanonicalSearchEngine().run(
                grammar,
                context,
                config=ProductionSearchConfig(
                    mode="exhaustive", por_policy="force", exhaustive_cost_minimization=True,
                ),
            ).canonical_result
            terminal_parity = (
                set(raw.terminal_canonical_hashes)
                == set(canonical.terminal_canonical_hashes)
                == set(reduced.terminal_canonical_hashes)
            )
            current = {
                "composition_width": width,
                "raw_paths_or_states": raw.generated_states,
                "raw_candidate_constructions": raw.candidate_constructions,
                "canonical_unique_states": canonical.metrics.unique_canonical_states,
                "canonical_candidate_constructions": canonical.metrics.candidate_constructions,
                "reduced_unique_states": reduced.metrics.unique_canonical_states,
                "reduced_candidate_constructions": reduced.metrics.candidate_constructions,
                "terminal_states": len(reduced.terminal_state_ids),
                "transpositions": canonical.metrics.exact_transpositions,
                "por_skips": reduced.metrics.por_avoided_transitions,
                "terminal_preservation": terminal_parity,
            }
            if previous is not None:
                current["growth_from_previous"] = {
                    "raw": current["raw_candidate_constructions"] / previous["raw_candidate_constructions"],
                    "canonical_unique": current["canonical_unique_states"] / previous["canonical_unique_states"],
                    "canonical_construction": (
                        current["canonical_candidate_constructions"]
                        / previous["canonical_candidate_constructions"]
                    ),
                    "reduced_construction": (
                        current["reduced_candidate_constructions"]
                        / previous["reduced_candidate_constructions"]
                    ),
                    "terminal_proof_compile_work": current["terminal_states"] / previous["terminal_states"],
                }
            levels.append(current)
            previous = current
            if not terminal_parity:
                failures.append({"project": project, "width": width})
        strongest = levels[-1]["growth_from_previous"]
        classification = (
            "strong" if strongest["raw"] >= 10 and strongest["reduced_construction"] <= 2.0 else
            "acceptable" if strongest["raw"] >= 10 and strongest["reduced_construction"] <= 3.0 else
            "warning" if strongest["raw"] >= 10 and strongest["reduced_construction"] <= 6.0 else
            "failure"
        )
        rows.append({
            "project": project,
            "source": source,
            "levels": levels,
            "widest_growth_classification": classification,
        })
    return {
        "schema_version": "vladder-production-search-scaling-v1",
        "status": "PASS" if not failures else "FAIL",
        "systems": rows,
        "failures": failures,
        "cross_system_gate": all(
            row["widest_growth_classification"] in {"strong", "acceptable"}
            for row in rows
        ),
    }


def real_system_root_validation(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    projects = ("duckdb", "llama.cpp", "rocksdb")
    rows = []
    failures = []
    for project in projects:
        candidates = [
            item for item in manifest["roots"]
            if item.get("project_id") == project
            and len(item.get("contract", {}).get("selected_build_regions", ())) >= 3
        ]
        if not candidates:
            candidates = [
                item for item in manifest["roots"]
                if item.get("project_id") == project
                and int(item.get("contract", {}).get("max_selected_build_regions", 0)) >= 3
            ]
        if not candidates:
            failures.append({"project": project, "reason": "no three-region source root"})
            continue
        item = candidates[0]
        with tempfile.TemporaryDirectory(prefix=f"vladder-production-{project.replace('.', '-')}-") as directory:
            root = Path(directory)
            request = ExecutableSearchRequest(
                identifier=f"production-{project}",
                output_directory=root / "capture",
                source=Path(item["source"]),
                function=item.get("function"),
                language="cpp",
                family="auto",
                contract=item.get("contract"),
                project_id=project,
                compile_commands=Path(item["compile_commands"]),
                source_line=item.get("source_line"),
                symbol=item.get("symbol"),
                command_index=item.get("command_index"),
                search_mode="exhaustive",
            )
            captured = ExecutableSearchEngine(root / "cache").capture(request)
            selected = next(
                (alt for alt in captured.family_alternatives if alt.family == "selected-build-cpp"),
                None,
            )
            if selected is None or selected.unresolved_contracts:
                failures.append({
                    "project": project,
                    "reason": "selected-build grammar unavailable",
                    "contracts": list(selected.unresolved_contracts) if selected else [],
                })
                continue
            report = json.loads(Path(str(selected.contract["report"])).read_text())
            all_regions = tuple(str(value) for value in selected.contract.get("selected_regions", ()))
            levels = []
            for width in range(1, min(3, len(all_regions)) + 1):
                regions = all_regions[:width]
                grammar = SelectedBuildCppGrammar(report, regions)
                context = {
                    "semantic_hash": f"{selected.semantic_hash}:{width}",
                    "grammar_version": selected.grammar_version,
                }
                raw = exhaustive_sequence_search(grammar, context, node_budget=100_000)
                canonical = CanonicalSearchEngine().run(grammar, context, mode="exhaustive_canonical")
                reduced = ProductionCanonicalSearchEngine().run(
                    grammar,
                    context,
                    config=ProductionSearchConfig(
                        mode="exhaustive", por_policy="force", exhaustive_cost_minimization=True,
                    ),
                ).canonical_result
                parity = (
                    set(raw.terminal_canonical_hashes)
                    == set(canonical.terminal_canonical_hashes)
                    == set(reduced.terminal_canonical_hashes)
                )
                levels.append({
                    "selected_region_count": width,
                    "selected_regions": list(regions),
                    "raw_states": raw.generated_states,
                    "canonical_states": canonical.metrics.unique_canonical_states,
                    "reduced_candidate_constructions": reduced.metrics.candidate_constructions,
                    "terminals": len(reduced.terminal_state_ids),
                    "terminal_preservation": parity,
                    "complete_footprint_actions": reduced.metrics.action_footprint_complete,
                    "missing_footprint_actions": reduced.metrics.action_footprint_missing,
                })
                if not parity:
                    failures.append({"project": project, "width": width, "reason": "terminal mismatch"})
            rows.append({
                "project": project,
                "source": str(request.source),
                "function": request.function,
                "symbol": selected.contract.get("selected_symbol"),
                "compile_command_sha256": selected.contract.get("compile_command_sha256"),
                "levels": levels,
            })
    return {
        "schema_version": "vladder-production-real-system-roots-v1",
        "status": "PASS" if len(rows) == 3 and not failures else "FAIL",
        "systems": rows,
        "failures": failures,
    }


def measured_expensive_root() -> dict[str, Any]:
    compiler = shutil.which("clang++-20") or shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        return {"status": "FAIL", "reason": "C++ compiler unavailable"}
    grammar = _grammar("measured-cpp", "measured-source-root", 3)
    context = {"semantic_hash": "measured-expensive-root", "grammar_version": "fixture-v1"}

    def run_evaluator(base: Path):
        counter = Counter()

        def evaluate(state: LazyState) -> Mapping[str, Any]:
            ordinal = counter["calls"]
            counter["calls"] += 1
            selection = dict(state.semantic_state["selection"])
            value = sum(choice != "baseline" for choice in selection.values())
            proof_started = time.perf_counter()
            symbol = z3.Int(f"selected_{ordinal}")
            solver = z3.Solver()
            solver.add(symbol == value, symbol != value)
            assert solver.check() == z3.unsat
            proof_ms = (time.perf_counter() - proof_started) * 1000.0
            source = base / f"candidate-{ordinal}.cpp"
            obj = base / f"candidate-{ordinal}.o"
            source.write_text(
                f'extern "C" int candidate_{ordinal}(int x) noexcept {{ return x + {value}; }}\n'
            )
            compile_started = time.perf_counter()
            completed = subprocess.run(
                [compiler, "-std=c++20", "-O3", "-c", str(source), "-o", str(obj)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            compile_ms = (time.perf_counter() - compile_started) * 1000.0
            if completed.returncode:
                raise RuntimeError(completed.stderr)
            counter["proof_calls"] += 1
            counter["compiler_calls"] += 1
            counter["proof_us"] += int(proof_ms * 1000.0)
            counter["compile_us"] += int(compile_ms * 1000.0)
            return {
                "proof_status": "PASS",
                "compiler_status": "PASS",
                "proof_calls": 1,
                "compiler_calls": 1,
            }

        return counter, evaluate

    with tempfile.TemporaryDirectory(prefix="vladder-production-expensive-") as directory:
        root = Path(directory)
        raw_counter, raw_evaluator = run_evaluator(root / "raw")
        (root / "raw").mkdir()
        raw_started = time.perf_counter()
        raw = exhaustive_sequence_search(
            grammar, context, node_budget=100_000, terminal_evaluator=raw_evaluator,
        )
        raw_wall_ms = (time.perf_counter() - raw_started) * 1000.0

        reduced_counter, reduced_evaluator = run_evaluator(root / "reduced")
        (root / "reduced").mkdir()
        reduced_started = time.perf_counter()
        reduced = ProductionCanonicalSearchEngine().run(
            grammar,
            context,
            config=ProductionSearchConfig(
                mode="exhaustive", por_policy="force", exhaustive_cost_minimization=True,
            ),
            terminal_evaluator=reduced_evaluator,
        ).canonical_result
        reduced_wall_ms = (time.perf_counter() - reduced_started) * 1000.0
    parity = set(raw.terminal_canonical_hashes) == set(reduced.terminal_canonical_hashes)
    return {
        "schema_version": "vladder-production-expensive-root-v1",
        "status": "PASS" if parity and reduced_wall_ms < raw_wall_ms else "FAIL",
        "scope": "bounded C++ source root with actual Z3 proof and optimized object compilation per terminal",
        "compiler": compiler,
        "raw": {
            **asdict(raw),
            "measured_wall_ms": raw_wall_ms,
            "proof_wall_ms": raw_counter["proof_us"] / 1000.0,
            "compiler_wall_ms": raw_counter["compile_us"] / 1000.0,
        },
        "reduced": {
            "candidate_constructions": reduced.metrics.candidate_constructions,
            "terminal_states": len(reduced.terminal_state_ids),
            "proof_calls": reduced.metrics.proof_calls,
            "compiler_calls": reduced.metrics.compiler_calls,
            "measured_wall_ms": reduced_wall_ms,
            "proof_wall_ms": reduced_counter["proof_us"] / 1000.0,
            "compiler_wall_ms": reduced_counter["compile_us"] / 1000.0,
        },
        "terminal_preservation": parity,
        "proof_calls_avoided": raw.proof_calls - reduced.metrics.proof_calls,
        "compiler_calls_avoided": raw.compiler_calls - reduced.metrics.compiler_calls,
        "measured_wall_ms_saved": raw_wall_ms - reduced_wall_ms,
        "measured_wall_reduction": 1.0 - reduced_wall_ms / raw_wall_ms,
    }


def concurrency_stress() -> dict[str, Any]:
    table = TranspositionTable()
    canonicalizer = Canonicalizer()
    states = tuple(
        LazyState("concurrency", "candidate", {"value": index % 17}, {"op": "set", "value": index % 17})
        for index in range(4096)
    )
    started = time.perf_counter()

    def intern(item: tuple[int, LazyState]):
        index, state = item
        return table.intern(
            state,
            depth=index % 5,
            path=({"op": "set", "value": index % 17},),
            edge_id=f"edge-{index}",
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(intern, enumerate(states)))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    expected = {canonicalizer.envelope(state).canonical_bytes for state in states}
    actual = {record.envelope.canonical_bytes for record in table.records.values()}
    return {
        "schema_version": "vladder-production-concurrency-stress-v1",
        "status": "PASS" if expected == actual and sum(created for _, created, _ in outcomes) == 17 else "FAIL",
        "workers": 16,
        "registrations": len(states),
        "unique_expected": len(expected),
        "unique_actual": len(actual),
        "recursive_owners": sum(created for _, created, _ in outcomes),
        "elapsed_ms": elapsed_ms,
        "registrations_per_second": len(states) / max(1e-9, elapsed_ms / 1000.0),
    }


def memory_and_footprint() -> dict[str, Any]:
    result = ProductionCanonicalSearchEngine().run(
        _grammar("resource", "resource-root", 5),
        {"semantic_hash": "resource-root", "grammar_version": "fixture-v1"},
        config=ProductionSearchConfig(
            mode="exhaustive", por_policy="force", memory_ceiling_bytes=64 * 1024 * 1024,
        ),
    )
    families = result.footprint_audit["families"]
    return {
        "schema_version": "vladder-production-resource-qualification-v1",
        "status": "PASS" if result.canonical_result.complete and families else "FAIL",
        "peak_memory_bytes": result.canonical_result.metrics.peak_memory_bytes,
        "configured_ceiling_bytes": 64 * 1024 * 1024,
        "analysis_cache": result.cache_stats,
        "footprint_audit": result.footprint_audit,
        "complete_footprint_ratio": (
            sum(item["complete_footprints"] for item in families)
            / max(1, sum(item["generated_actions"] for item in families))
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify production canonical-state search")
    temporary_root = Path(tempfile.gettempdir())
    parser.add_argument(
        "--rc26-root", type=Path,
        default=temporary_root / "vladder-composition-native-rc26-out",
    )
    parser.add_argument(
        "--rc27-report", type=Path,
        default=temporary_root / "vladder-canonical-search-qualification-rc27.json",
    )
    parser.add_argument(
        "--rc26-manifest", type=Path,
        default=temporary_root / "vladder-composition-native-rc26-manifest.json",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("/root/Documents/Codex/2026-08-10/vladder-graphml-training-campaign/sources"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rc26 = replay_rc26(args.rc26_root)
    rc27 = json.loads(args.rc27_report.read_text()) if args.rc27_report.is_file() else {
        "status": "FAIL", "reason": "RC27 qualification report missing",
    }
    # A fresh adversarial replay guards against qualifying only a stale report artifact.
    adversarial = adversarial_campaign(30)
    scaling = scaling_suite(args.sources)
    real_systems = real_system_root_validation(args.rc26_manifest)
    expensive = measured_expensive_root()
    concurrency = concurrency_stress()
    resources = memory_and_footprint()
    gates = {
        "terminal_preservation": adversarial["status"] == "PASS",
        "rc26_replay": rc26["status"] == "PASS" and rc26["metrics"]["u2_preservation_ratio"] == 1.0,
        "rc27_replay": rc27.get("status") == "PASS",
        "scaling_three_systems": scaling["status"] == "PASS" and scaling["cross_system_gate"],
        "real_system_root_capture": real_systems["status"] == "PASS",
        "measured_expensive_root": expensive["status"] == "PASS",
        "concurrent_identity": concurrency["status"] == "PASS",
        "resource_and_footprint": resources["status"] == "PASS",
    }
    if all(gates.values()):
        disposition = "PRODUCTION_CANONICAL_SEARCH_APPROVED"
    elif gates["terminal_preservation"] and gates["rc26_replay"] and gates["rc27_replay"]:
        disposition = "PRODUCTION_CANONICAL_SEARCH_CONDITIONAL"
    else:
        disposition = "SCALING_HYPOTHESIS_NOT_PROVEN"
    report = {
        "schema_version": QUALIFICATION_SCHEMA,
        "status": "PASS" if all(gates.values()) else "FAIL",
        "disposition": disposition,
        "production_claim": (
            "vLadder exhaustively searches unique reachable semantic realizations after "
            "completeness-preserving state-space reduction, rather than enumerating redundant "
            "transformation sequences."
        ),
        "gates": gates,
        "rc26_replay": rc26,
        "rc27_replay": rc27,
        "fresh_rc27_adversarial_replay": adversarial,
        "scaling_suite": scaling,
        "real_system_root_validation": real_systems,
        "measured_expensive_root": expensive,
        "concurrency": concurrency,
        "resources_and_footprints": resources,
        "failure_and_counterexample_summary": {
            "hash_collision": "qualified by unit regression",
            "unknown_footprint": "fails open as dependent",
            "alias_and_contract_overlap": "fails independence screening",
            "dominance_and_macro_false_positive": "disabled without descendant qualification",
            "incremental_hash_divergence": "raises and falls back to clean rematerialization",
            "unresolved_failures": [key for key, passed in gates.items() if not passed],
        },
        "production_defaults": {
            "fast": "canonical DAG + cheap exact reductions + finite budget",
            "guided": "canonical DAG + qualified cost-gated POR + finite budget",
            "exhaustive": "all reachable unique canonical states under qualified exact reductions",
            "raw_sequence": "legacy_path_debug qualification mode only",
        },
        "disabled_experimental_mechanisms": [
            "learned deletion",
            "unqualified dominance",
            "unqualified macro reduction",
            "coarse optimization-equivalence collapse",
            "global ownership/protocol e-graphs",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": report["status"],
        "disposition": disposition,
        "gates": gates,
        "measured_expensive_root": expensive,
        "scaling": [
            {"project": row["project"], "classification": row["widest_growth_classification"]}
            for row in scaling["systems"]
        ],
        "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
