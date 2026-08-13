from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Iterable, Mapping

from .cpp_closure import cpp_schedule_variants, materialize_cpp_schedule_candidate
from .deep_benchmark import _hot_assembly_identity
from .language_adapter import canonical_hash
from .lazy_search import LazyState
from .search_decision_context import selected_build_projection


SELECTED_BUILD_GRAMMAR_VERSION = "selected-build-cpp-composition-v4"
SELECTED_BUILD_TERMINAL_VERSION = "selected-build-terminal-realization-v4"


@dataclass(frozen=True)
class SelectedBuildChoice:
    region: str
    choice: str


class SelectedBuildCppGrammar:
    """Lazily choose one realization for each region in any semantically legal order.

    Region choice maps, rather than action order, identify partial states.  The lazy-search
    engine can therefore collapse exact transpositions such as ``A then B`` and ``B then A``
    while retaining the distinct action histories as evidence for composition policy training.
    """

    def __init__(
        self,
        report: Mapping[str, Any],
        selected_regions: Iterable[str] | None = None,
    ) -> None:
        closure = report.get("closure", {})
        candidates = tuple(item for item in closure.get("candidates", ()) if isinstance(item, dict))
        by_region: dict[str, dict[str, dict[str, Any]]] = {}
        for candidate in candidates:
            region = _candidate_region(candidate)
            choice = _candidate_choice(candidate, region)
            if not region or not choice:
                continue
            by_region.setdefault(region, {})[choice] = candidate
        if not by_region:
            for region in closure.get("regions", ()):
                if not isinstance(region, dict) or not (
                    region.get("eligible") or region.get("schedule_eligible")
                ):
                    continue
                region_id = str(region.get("id") or "")
                if not region_id:
                    continue
                by_region[region_id] = {
                    str(variant["choice"]): {
                        "id": f"{region_id}-{variant['choice']}",
                        "region_id": region_id,
                        "schedule_choice": variant["choice"],
                        "schedule_family": variant["schedule_family"],
                        "rule": (
                            "effect-preserving-owning-loop-schedule-hint"
                            if region.get("isolation_mode") == "effect_preserving_schedule"
                            else
                            "whole-function-clang-loop-schedule-hint"
                            if region.get("isolation_mode") == "whole_function_cfg"
                            else "clang-loop-schedule-hint"
                        ),
                        "factor": variant["factor"],
                        "source_range": list(region.get("source_range") or ()),
                        "isolation_mode": region.get("isolation_mode"),
                        "materialization": "deferred",
                    }
                    for variant in cpp_schedule_variants()
                }
        requested = None if selected_regions is None else frozenset(str(item) for item in selected_regions)
        if requested is not None:
            missing = requested - set(by_region)
            if missing:
                raise ValueError(f"selected-build regions are absent from compiler capture: {sorted(missing)}")
            by_region = {region: values for region, values in by_region.items() if region in requested}
        unique_regions: dict[str, dict[str, dict[str, Any]]] = {}
        seen_realizations: set[tuple[tuple[str, str], ...]] = set()
        for region in sorted(by_region):
            signature = tuple(
                (choice, _candidate_source_hash(candidate))
                for choice, candidate in sorted(by_region[region].items())
            )
            if signature in seen_realizations:
                continue
            seen_realizations.add(signature)
            unique_regions[region] = by_region[region]
        self.report = dict(report)
        self.by_region = unique_regions
        self.regions = tuple(self.by_region)
        if not self.regions:
            raise ValueError("selected-build search requires at least one executable region")

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return (self._state({}, 0, {"family": "selected-build-cpp", "op": "enter"}),)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return tuple(
            child
            for action in self.enabled_actions(state, root_context)
            if (child := self.apply_action(state, action, root_context)) is not None
        )

    def enabled_actions(
        self, state: LazyState, root_context: Mapping[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        current = {
            str(key): str(value)
            for key, value in state.semantic_state.get("selection", {}).items()
        }
        return tuple(
            self._action(region, choice)
            for region in self.regions
            if region not in current
            for choice in ("baseline", *sorted(self.by_region[region]))
        )

    def apply_action(
        self,
        state: LazyState | None,
        action: Mapping[str, Any],
        root_context: Mapping[str, Any],
    ) -> LazyState | None:
        if state is None:
            return None
        region = str(action.get("region") or "")
        choice = str(action.get("choice") or "")
        current = {
            str(key): str(value)
            for key, value in state.semantic_state.get("selection", {}).items()
        }
        if not region or region in current or region not in self.by_region:
            return None
        if choice != "baseline" and choice not in self.by_region[region]:
            return None
        return self._state({**current, region: choice}, len(current) + 1, action)

    def _action(self, region: str, choice: str) -> dict[str, Any]:
        if choice == "baseline":
            return {
                "action_key": f"{region}={choice}",
                "family": "selected-build-cpp",
                "op": "select_schedule",
                "rule": "baseline-schedule",
                "region": region,
                "choice": choice,
                "footprint": {
                    "complete": True,
                    "reads": [f"region:{region}:candidates"],
                    "writes": [f"region:{region}:selection"],
                    "owners": [f"region:{region}"],
                },
            }
        candidate = self.by_region[region][choice]
        return {
            "action_key": f"{region}={choice}",
            "family": str(candidate.get("schedule_family") or _schedule_family(choice)),
            "op": "select_schedule",
            "rule": str(candidate.get("rule") or choice),
            "region": region,
            "choice": choice,
            "factor": candidate.get("factor"),
            "footprint": {
                "complete": True,
                "reads": [f"region:{region}:candidates"],
                "writes": [f"region:{region}:selection"],
                "owners": [f"region:{region}"],
            },
        }

    def _state(self, selection: Mapping[str, str], next_region: int, action: Mapping[str, Any]) -> LazyState:
        remaining = tuple(region for region in self.regions if region not in selection)
        terminal = not remaining
        semantic_state = {
            "selection": dict(sorted(selection.items())),
            "next_region": next_region,
            "remaining_regions": list(remaining),
        }
        return LazyState(
            str(action.get("family") or "selected-build-cpp"),
            "composition" if terminal else "candidate_family",
            semantic_state,
            dict(action),
            terminal=terminal,
            identity=canonical_hash({
                "family": "selected-build-cpp",
                "selection": semantic_state["selection"],
                "next_region": next_region,
            }),
            decision_projection=selected_build_projection(
                self.report,
                current_region=str(action.get("region")) if action.get("region") else None,
            ),
        )


def selected_build_parameter_domains(
    report: Mapping[str, Any], selected_regions: Iterable[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    grammar = SelectedBuildCppGrammar(report, selected_regions)
    return {
        region: ("baseline", *tuple(sorted(grammar.by_region[region])))
        for region in grammar.regions
    }


def prepare_selected_build_candidates(
    report: Mapping[str, Any], terminal_parent: Path,
    selected_regions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Best-effort materialization of shared regional evidence before composition builds.

    Prewarming is only a cache optimization.  A region-local isolation failure must be
    classified by terminal evaluation; it must not abort unrelated terminals or the campaign.
    """
    grammar = SelectedBuildCppGrammar(report, selected_regions)
    prewarm = terminal_parent / "_regional-prewarm"
    prepared: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for region in grammar.regions:
        for choice in sorted(grammar.by_region[region]):
            try:
                _materialize_selected_build_choice(
                    report,
                    region,
                    choice,
                    grammar.by_region[region][choice],
                    prewarm,
                )
                prepared.append({"region": region, "choice": choice})
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                failures.append({
                    "region": region,
                    "choice": choice,
                    "error": str(error)[:4000],
                })
    return {
        "schema_version": "vladder-selected-build-prewarm-v1",
        "status": "pass" if not failures else "partial",
        "prepared": prepared,
        "failures": failures,
    }


def evaluate_selected_build_candidate(
    report: Mapping[str, Any], selection: Mapping[str, Any], output_directory: Path,
    selected_regions: Iterable[str] | None = None,
) -> dict[str, Any]:
    construction_started = time.perf_counter()
    output_directory.mkdir(parents=True, exist_ok=True)
    grammar = SelectedBuildCppGrammar(report, selected_regions)
    normalized = {
        region: _normalize_choice(selection.get(region, "baseline"), grammar.by_region[region])
        for region in grammar.regions
    }
    cache_key = canonical_hash({
        "grammar_version": SELECTED_BUILD_GRAMMAR_VERSION,
        "terminal_version": SELECTED_BUILD_TERMINAL_VERSION,
        "selected_regions": list(grammar.regions),
        "selection": normalized,
        "source_sha256": report.get("source_sha256"),
        "closure_hash": report.get("closure", {}).get("closure_hash"),
        "compile_command": report.get("compile_command", {}).get("command_sha256"),
    })
    result_path = output_directory / "terminal-result.json"
    cached = _load_terminal_result(result_path, cache_key)
    if cached is not None:
        return cached
    selected = [
        _materialize_selected_build_choice(
            report,
            region,
            choice,
            grammar.by_region[region][choice],
            output_directory,
        )
        for region, choice in normalized.items()
        if choice != "baseline"
    ]
    original = Path(str(report["source"])).resolve()
    source_text = original.read_text()
    generated = _compose_candidate_source(source_text, selected)
    source_path = output_directory / original.name
    source_path.write_text(generated)
    candidate_construction_wall_ms = (time.perf_counter() - construction_started) * 1000.0
    proof_started = time.perf_counter()
    proof = _compose_proof(report, normalized, selected)
    proof_path = output_directory / "proof.json"
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    proof_wall_ms = (time.perf_counter() - proof_started) * 1000.0
    compiler_started = time.perf_counter()
    compiled = _compile_translation_unit(report, original, source_path, output_directory)
    compiler_wall_ms = (time.perf_counter() - compiler_started) * 1000.0
    baseline = all(choice == "baseline" for choice in normalized.values())
    candidate_id = canonical_hash({
        "source_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "selection": normalized,
        "compile_command": report.get("compile_command", {}).get("command_sha256"),
    })
    result = {
        "candidate_id": candidate_id,
        "realization": "baseline" if baseline else "composed-loop-schedule",
        "parameters": {"selection": normalized},
        "source_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "proof_status": proof["status"],
        "proof_class": "selected-build-source-schedule-v3",
        "proof_calls": 1,
        "proof_wall_ms": proof_wall_ms,
        "compile_status": compiled["status"],
        "compiler_invocation_count": 2 if compiled.get("identity_mode") == "no-inline-internal-symbol-identity" else 1,
        "compiler_wall_ms": compiler_wall_ms,
        "candidate_construction_wall_ms": candidate_construction_wall_ms,
        "assembly_identity": compiled.get("assembly_identity"),
        "artifacts": {
            "source": str(source_path),
            "proof": str(proof_path),
            "assembly": compiled.get("assembly"),
        },
        "compile": compiled,
        "replacement_ready": proof["status"] == "PASS" and compiled["status"] == "PASS",
        "source_reconstruction": {
            "status": "PASS" if proof["status"] == "PASS" and compiled["status"] == "PASS" else "FAIL",
            "scope": "complete_translation_unit",
            "source": str(source_path),
            "original_source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            "candidate_source_sha256": hashlib.sha256(generated.encode()).hexdigest(),
            "edit_policy": "proved non-overlapping loop-directive insertions",
        },
    }
    temporary = output_directory / ".terminal-result.tmp"
    temporary.write_text(json.dumps({
        "schema_version": "vladder-selected-build-terminal-cache-v2",
        "cache_key": cache_key,
        "result": result,
    }, indent=2, sort_keys=True) + "\n")
    temporary.replace(result_path)
    return result


def _load_terminal_result(path: Path, cache_key: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("cache_key") != cache_key or not isinstance(payload.get("result"), dict):
        return None
    result = dict(payload["result"])
    artifacts = result.get("artifacts", {})
    required = (artifacts.get("source"), artifacts.get("proof"), artifacts.get("assembly"))
    if any(not value or not Path(str(value)).is_file() for value in required):
        return None
    return result


def _materialize_selected_build_choice(
    report: Mapping[str, Any],
    region: str,
    choice: str,
    descriptor: Mapping[str, Any],
    output_directory: Path,
) -> dict[str, Any]:
    candidate_path = Path(str(descriptor.get("repository_candidate_source") or ""))
    if candidate_path.is_file():
        return dict(descriptor)
    command = report.get("compile_command", {})
    original = Path(str(report["source"])).resolve()
    shared = output_directory.parents[1] / "regional-candidates" / region / choice
    failure_key = canonical_hash({
        "terminal_version": SELECTED_BUILD_TERMINAL_VERSION,
        "source_sha256": report.get("source_sha256"),
        "closure_hash": report.get("closure", {}).get("closure_hash"),
        "compile_command": command.get("command_sha256"),
        "region": region,
        "choice": choice,
    })
    failure_path = shared / "materialization-failure.json"
    if failure_path.is_file():
        try:
            failure = json.loads(failure_path.read_text())
        except (OSError, json.JSONDecodeError):
            failure = {}
        if failure.get("cache_key") == failure_key:
            raise ValueError(str(failure.get("error") or "cached regional materialization failure"))
    try:
        return materialize_cpp_schedule_candidate(
            dict(report),
            original,
            [str(item) for item in command.get("semantic_arguments", ())],
            Path(str(command.get("directory") or original.parent)),
            region,
            choice,
            shared,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        shared.mkdir(parents=True, exist_ok=True)
        temporary = failure_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({
            "schema_version": "vladder-selected-build-materialization-failure-v1",
            "cache_key": failure_key,
            "region": region,
            "choice": choice,
            "error": str(error)[:4000],
        }, indent=2, sort_keys=True) + "\n")
        temporary.replace(failure_path)
        raise


def _compose_candidate_source(original: str, selected: list[Mapping[str, Any]]) -> str:
    edits: list[tuple[int, int, str]] = []
    for candidate in selected:
        edits.append(_selected_build_source_edit(original, candidate))
    ordered = sorted(edits, key=lambda item: (item[0], item[1]))
    for previous, current in zip(ordered, ordered[1:]):
        if current[0] < previous[1]:
            raise ValueError("selected-build candidate edits overlap")
    result = original
    for start, end, replacement in reversed(ordered):
        result = result[:start] + replacement + result[end:]
    return result


def _selected_build_source_edit(
    original: str,
    candidate: Mapping[str, Any],
) -> tuple[int, int, str]:
    """Recover the exact guarded pragma insertion without diffing the full translation unit."""
    declared = candidate.get("source_edit")
    if isinstance(declared, Mapping):
        start = int(declared["start"])
        end = int(declared.get("end", start))
        replacement = str(declared["replacement"])
    else:
        placement = candidate.get("placement")
        if not isinstance(placement, Mapping) or placement.get("insert_before") is None:
            raise ValueError(
                f"selected-build candidate lacks an exact source edit: {candidate.get('id')}"
            )
        start = int(placement["insert_before"])
        end = start
        candidate_source = Path(str(candidate["repository_candidate_source"])).read_text()
        inserted_size = len(candidate_source) - len(original)
        if inserted_size <= 0:
            raise ValueError(
                f"selected-build candidate is not an insertion: {candidate.get('id')}"
            )
        replacement = candidate_source[start:start + inserted_size]
        if (
            candidate_source[:start] != original[:start]
            or candidate_source[start + inserted_size:] != original[start:]
        ):
            raise ValueError(
                f"selected-build candidate changed source outside its declared insertion: "
                f"{candidate.get('id')}"
            )
    if start < 0 or end < start or end > len(original):
        raise ValueError(f"selected-build candidate edit is out of bounds: {candidate.get('id')}")
    return start, end, replacement


def _compose_proof(
    report: Mapping[str, Any], selection: Mapping[str, str], selected: list[Mapping[str, Any]],
) -> dict[str, Any]:
    obligations: list[dict[str, Any]] = []
    for candidate in selected:
        proof = candidate.get("proof", {})
        schedule = proof.get("schedule", {})
        body = proof.get("body_refinement", {})
        obligations.append({
            "candidate": candidate.get("id"),
            "schedule_status": schedule.get("status"),
            "body_status": body.get("status"),
            "repository_syntax": candidate.get("repository_syntax", {}).get("status"),
            "schedule_artifact": schedule.get("artifact"),
            "body_artifact": body.get("sanitized_ir"),
        })
    source_integrity = report.get("closure", {}).get("source_integrity", {})
    passed = bool(source_integrity.get("unchanged", True)) and all(
        item["schedule_status"] == "PROVED"
        and item["body_status"] == "correct"
        and item["repository_syntax"] == "pass"
        for item in obligations
    )
    return {
        "schema_version": "vladder-selected-build-composition-proof-v1",
        "status": "PASS" if passed else "FAIL",
        "selection": dict(selection),
        "obligations": obligations,
        "source_integrity": source_integrity,
        "claim": (
            "each source directive preserves the selected loop body, Z3 proves partition coverage, "
            "and non-overlapping source edits compose without changing owning C++ observables"
        ),
        "excluded_claims": ["performance improvement", "external protocol behavior"],
    }


def _compile_translation_unit(
    report: Mapping[str, Any], original: Path, source: Path, output_directory: Path,
) -> dict[str, Any]:
    command = report.get("compile_command", {})
    semantic_arguments = [str(item) for item in command.get("semantic_arguments", ())]
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return {"status": "FAIL", "reason": "clang++ unavailable"}
    assembly = output_directory / "candidate.s"
    argv = [
        compiler, *semantic_arguments, "-iquote", str(original.parent),
        "-O3", "-S", str(source), "-o", str(assembly),
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
    requested_symbol = str(report.get("selection", {}).get("symbol") or report.get("function"))
    symbol = _selected_identity_symbol(report)
    identity_assembly = assembly
    identity_command = argv
    identity_mode = "production-assembly"
    if _internal_linkage_symbol(symbol, report):
        identity_assembly = output_directory / "candidate.identity.s"
        identity_command = [
            compiler, *semantic_arguments, "-iquote", str(original.parent),
            "-O3", "-fno-inline-functions", "-S", str(source),
            "-o", str(identity_assembly),
        ]
        identity_completed = subprocess.run(
            identity_command,
            cwd=str(command.get("directory") or original.parent),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        )
        if identity_completed.returncode:
            return {
                "status": "FAIL", "command": argv, "assembly": str(assembly),
                "identity_command": identity_command,
                "stdout": identity_completed.stdout[-4000:],
                "stderr": identity_completed.stderr[-8000:],
                "reason": "internal-linkage identity build failed",
            }
        identity_mode = "no-inline-internal-symbol-identity"
    identity = _hot_assembly_identity(identity_assembly, symbol)
    return {
        "status": "PASS" if identity.get("status") == "resolved" else "FAIL",
        "command": argv,
        "assembly": str(assembly),
        "identity_assembly": str(identity_assembly),
        "identity_command": identity_command,
        "identity_mode": identity_mode,
        "assembly_identity": identity.get("normalized_sha256"),
        "identity": identity,
        "requested_ast_symbol": requested_symbol,
        "resolved_identity_symbol": symbol,
        "stderr": completed.stderr[-4000:],
    }


def _selected_identity_symbol(report: Mapping[str, Any]) -> str:
    requested = str(report.get("selection", {}).get("symbol") or report.get("function"))
    production_ir = report.get("production_ir", {})
    resolved = (
        production_ir.get("resolved_symbols", {}).get("production")
        if isinstance(production_ir, Mapping)
        else None
    )
    return str(resolved) if resolved else requested


def _candidate_source_hash(candidate: Mapping[str, Any]) -> str:
    path = Path(str(candidate.get("repository_candidate_source", "")))
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if candidate.get("materialization") == "deferred":
        return canonical_hash({
            "choice": candidate.get("schedule_choice"),
            "source_range": candidate.get("source_range"),
            "isolation_mode": candidate.get("isolation_mode"),
        })
    return canonical_hash(candidate)


def _candidate_region(candidate: Mapping[str, Any]) -> str:
    declared = str(candidate.get("region_id") or "")
    if declared:
        return declared
    match = re.match(r"^(region-[0-9]+)-", str(candidate.get("id") or ""))
    return match.group(1) if match else ""


def _candidate_choice(candidate: Mapping[str, Any], region: str) -> str:
    declared = str(candidate.get("schedule_choice") or "")
    if declared:
        return declared
    identifier = str(candidate.get("id") or "")
    prefix = f"{region}-"
    return identifier[len(prefix):] if region and identifier.startswith(prefix) else ""


def _schedule_family(choice: str) -> str:
    if "vector" in choice:
        return "loop-vector-width"
    if "interleave" in choice:
        return "loop-interleave-schedule"
    return "loop-unroll-schedule"


def _normalize_choice(value: Any, candidates: Mapping[str, Mapping[str, Any]]) -> str:
    if value in {None, 1, "1", "baseline"}:
        return "baseline"
    text = str(value)
    if text in candidates:
        return text
    legacy = f"unroll-{text}"
    if legacy in candidates:
        return legacy
    legacy_cfg = f"cfg-unroll-{text}"
    if legacy_cfg in candidates:
        return legacy_cfg
    raise ValueError(f"selected-build schedule choice is absent: {text}")


def _internal_linkage_symbol(symbol: str, report: Mapping[str, Any]) -> bool:
    if report.get("selection", {}).get("storage_class") == "static":
        return True
    if symbol.startswith("_ZL"):
        return True
    return re.search(r"L\d+[A-Za-z_]", symbol) is not None
