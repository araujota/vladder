from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Iterable, Mapping
import yaml

from .bit_reduction import (
    BIT_REDUCTION_GRAMMAR_VERSION,
    BitReductionContract,
    bit_reduction_realizations,
    build_bit_reduction_graph,
    detect_bit_reduction,
    enumerate_bit_reduction_candidates,
    prove_bit_reduction_candidate,
)
from .canonical_executable import (
    CANONICAL_EXECUTABLE_VERSION,
    CanonicalDerivation,
    CanonicalExecutableGrammar,
    emit_canonical_candidate,
    prove_canonical_candidate,
)
from .canonical_search import CanonicalSearchEngine, canonical_result_to_lazy
from .production_search import (
    ProductionCanonicalSearchEngine,
    ProductionSearchConfig,
)
from .canonical_regions import (
    CanonicalRegionError,
    build_canonical_graph,
    classify_canonical_region,
    corroborate_compiler_shape,
)
from .composition_native import build_composition_trace
from .dataflow_grammar import load_bounded_dataflow_grammar
from .dataflow_inference import infer_bounded_dataflow_contracts
from .dataflow_ir import BoundedDataflowContract, build_bounded_dataflow_graph
from .dataflow_lazy import BoundedDataflowLazyGrammar
from .cpp_dataflow_reconstruction import (
    exact_dataflow_reconstruction_applicable,
    reconstruct_exact_dataflow_translation_unit,
)
from .dataflow_multilang import emit_dataflow_native
from .dataflow_proof import prove_dataflow_candidate
from .cross_tu_adapter import cross_tu_semantic_flow_graph
from .cross_tu_selected_build import (
    applicable_region_domains,
    capture_cross_tu_selected_build_regions,
    evaluate_cross_tu_selected_build_candidate,
    region_key,
)
from .cpp_regions import CPP_SUPPORT_VERSION, inspect_cpp_region, matching_compilation_command_indices
from .deep_audit import extract_named_source_region
from .deep_benchmark import _hot_assembly_identity, compile_deep_harness
from .deep_grammar import DeepDerivation, load_deep_grammar, search_deep_grammar
from .deep_ir import DeepKernelContract, build_deep_realization_graph, inspect_source_realization
from .deep_lowering import emit_deep_candidate
from .deep_proof import prove_deep_candidate
from .executable_closure import EXECUTABLE_STAGES, ExecutableFamilyClosure, closure_coverage, stage
from .language_adapter import canonical_hash
from .lazy_search import (
    ExpansionPolicy,
    FiniteParameterGrammar,
    JsonLineFrontierPolicy,
    LazyGrammar,
    LazySearchEngine,
    LazySearchResult,
    LazyState,
)
from .ordered_prefix import (
    ORDERED_PREFIX_GRAMMAR_VERSION,
    OrderedReductionContract,
    build_ordered_reduction_graph,
    detect_ordered_reduction,
    enumerate_ordered_candidates,
    prove_ordered_candidate,
)
from .lifetime_adapter import lifetime_semantic_flow_graph
from .lifetime_attribution import assess_trace_quality, attribute_lifetimes, load_lifetime_trace
from .lifetime_grammar import LifetimeCandidate, discover_lifetime_candidates_for_information
from .lifetime_graph import load_lifetime_flow_graph
from .lifetime_realization import build_agent_realization_contract, write_agent_realization_bundle
from .lifetime_verification import verify_lifetime_candidate, write_verification_report
from .llvm_function_search import (
    LLVM_FUNCTION_GRAMMAR_VERSION,
    capture_llvm_function,
    evaluate_llvm_function_pipeline,
    load_llvm_function_pipelines,
)
from .prior_data import make_root
from .predicate_reduction import (
    PREDICATE_REDUCTION_GRAMMAR_VERSION,
    PREDICATE_REDUCTION_STYLES,
    PREDICATE_REDUCTION_UNROLLS,
    PredicateReductionContract,
    build_predicate_reduction_graph,
    detect_predicate_reduction,
    enumerate_predicate_reduction_candidates,
    prove_predicate_reduction_candidate,
)
from .protocol_adapter import protocol_projection_domains, protocol_semantic_flow_graph
from .device_protocol import verify_device_protocol
from .state_protocol import verify_state_protocol
from .search_training import make_branch, make_branch_observation, make_search
from .search_decision_context import build_decision_context, selected_build_projection
from .selected_build_search import (
    SELECTED_BUILD_GRAMMAR_VERSION,
    SelectedBuildCppGrammar,
    evaluate_selected_build_candidate,
    prepare_selected_build_candidates,
    selected_build_parameter_domains,
)
from .toolchain import compiler_version, cpu_model
from .whole_build import run_cross_tu_closure


EXECUTABLE_SEARCH_VERSION = "executable-source-search-v20"
TERMINAL_EVALUATION_CACHE_VERSION = "executable-source-search-v20"
EXECUTABLE_GRAMMAR_REGISTRY_VERSION = "executable-grammar-registry-v2"
EXECUTABLE_SEARCH_MANIFEST_VERSION = "vladder-executable-search-manifest-v1"
SOURCE_DISPATCH_FAMILIES = (
    "canonical-bounded-region",
    "deep-information-realization",
    "ordered-prefix-suffix",
    "bit-popcount-reduction",
    "predicate-reduction",
    "predicate-stable-compaction",
    "fixed-width-codec",
    "stateful-delta-transducer",
    "aos-fused-multi-reduction",
    "quantized-block-4x4",
)
COMPILER_SOURCE_FAMILIES = ("llvm-function-pipeline",)


@dataclass(frozen=True)
class ExecutableSearchRequest:
    identifier: str
    output_directory: Path
    source: Path | None = None
    function: str | None = None
    language: str | None = None
    family: str = "auto"
    contract: Mapping[str, Any] | None = None
    project_id: str = "local"
    workload: Mapping[str, Any] | None = None
    hardware: Mapping[str, Any] | None = None
    node_budget: int = 100_000
    terminal_workers: int = 1
    lifetime_manifest: Path | None = None
    lifetime_trace: Path | None = None
    compile_commands: Path | None = None
    symbol: str | None = None
    source_line: int | None = None
    command_index: int | None = None
    cross_tu_seeds: tuple[str, ...] = ()
    max_upstream: int = 1
    max_downstream: int = 3
    max_cross_tu_nodes: int = 128
    protocol_manifest: Path | None = None
    oracle_command: tuple[str, ...] = ()
    oracle_timeout_seconds: float = 30.0
    oracle_prune_confidence: float = 0.999
    oracle_exploration_modulus: int = 100
    oracle_exploration_slots: int = 5
    # Direct API compatibility remains path-oriented unless the caller opts into a production mode.
    # CLI/manifest loading defaults to exhaustive canonical search below.
    search_mode: str = "legacy"
    search_work_budget: float | None = None
    search_time_budget_seconds: float | None = None
    frontier_oracle_command: tuple[str, ...] = ()
    frontier_oracle_timeout_seconds: float = 30.0
    search_memory_ceiling_bytes: int | None = None
    search_checkpoint: Path | None = None
    search_resume: Path | None = None
    por_policy: str = "adaptive"


def request_workers(request: ExecutableSearchRequest) -> int:
    return max(1, int(request.terminal_workers))


def _campaign_result_summary(
    result: Mapping[str, Any], request: ExecutableSearchRequest,
) -> dict[str, Any]:
    """Retain only campaign-level fields after durable per-root emission.

    Native exhaustive roots can contain gigabytes of repeated semantic graph state. Keeping those
    payloads in the parent process until every worker completes makes campaign memory proportional
    to corpus size even though the full artifacts are already durable on disk.
    """
    terminals = tuple(result.get("terminals", ()))
    return {
        "root": {"identifier": str(result.get("root", {}).get("identifier", request.identifier))},
        "status": str(result.get("status", "unknown")),
        "closure": dict(result.get("closure", {})),
        "terminal_count": len(terminals),
        "terminal_replacement_ready_count": sum(
            bool(item.get("replacement_ready")) for item in terminals
            if isinstance(item, Mapping)
        ),
        "output_directory": str(request.output_directory.resolve()),
    }


def _request_fingerprint(request: ExecutableSearchRequest) -> str:
    def file_identity(path: Path | None) -> dict[str, Any] | None:
        if path is None:
            return None
        resolved = path.resolve()
        if not resolved.is_file():
            return {"path": str(resolved), "sha256": None}
        return {
            "path": str(resolved),
            "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        }

    return canonical_hash({
        "search_version": EXECUTABLE_SEARCH_VERSION,
        "identifier": request.identifier,
        "source": file_identity(request.source),
        "function": request.function,
        "symbol": request.symbol,
        "source_line": request.source_line,
        "language": request.language,
        "family": request.family,
        "contract": dict(request.contract or {}),
        "project_id": request.project_id,
        "workload": dict(request.workload or {}),
        "hardware": dict(request.hardware or {}),
        "node_budget": request.node_budget,
        "lifetime_manifest": file_identity(request.lifetime_manifest),
        "lifetime_trace": file_identity(request.lifetime_trace),
        "compile_commands": file_identity(request.compile_commands),
        "command_index": request.command_index,
        "cross_tu_seeds": request.cross_tu_seeds,
        "max_upstream": request.max_upstream,
        "max_downstream": request.max_downstream,
        "max_cross_tu_nodes": request.max_cross_tu_nodes,
        "protocol_manifest": file_identity(request.protocol_manifest),
            "oracle_command": request.oracle_command,
            "search_mode": request.search_mode,
            "search_work_budget": request.search_work_budget,
            "search_time_budget_seconds": request.search_time_budget_seconds,
        "frontier_oracle_command": request.frontier_oracle_command,
        "search_memory_ceiling_bytes": request.search_memory_ceiling_bytes,
        "search_checkpoint": file_identity(request.search_checkpoint),
        "search_resume": file_identity(request.search_resume),
        "por_policy": request.por_policy,
        "oracle_timeout_seconds": request.oracle_timeout_seconds,
        "oracle_prune_confidence": request.oracle_prune_confidence,
        "oracle_exploration_modulus": request.oracle_exploration_modulus,
        "oracle_exploration_slots": request.oracle_exploration_slots,
    })


@dataclass(frozen=True)
class CapturedRoot:
    request: ExecutableSearchRequest
    family: str
    grammar_version: str
    graph: dict[str, Any]
    contract: dict[str, Any]
    semantic_hash: str
    source_region: str | None
    source_realization: str | None
    parameter_domains: dict[str, tuple[Any, ...]]
    unresolved_contracts: tuple[str, ...]
    external_boundaries: tuple[str, ...]
    recognition: str
    blocked_authority: str = "incomplete"
    family_alternatives: tuple[CapturedRoot, ...] = ()


class ContentAddressedEvidenceCache:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def key(self, payload: Mapping[str, Any]) -> str:
        return canonical_hash(payload)

    def load(self, key: str) -> dict[str, Any] | None:
        path = self.root / key[:2] / f"{key}.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None

    def store(self, key: str, value: Mapping[str, Any]) -> Path:
        directory = self.root / key[:2]
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{key}.json"
        if not path.exists():
            temporary = directory / f".{key}.{os.getpid()}.tmp"
            temporary.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n")
            try:
                temporary.replace(path)
            except FileExistsError:
                temporary.unlink(missing_ok=True)
        return path


def _search_request_process(
    cache_root: Path,
    request: ExecutableSearchRequest,
    shadow_exhaustive: bool,
    compact_decisive: bool = False,
) -> dict[str, Any]:
    """Run one root while returning only a compact reference across the process pipe."""
    artifact = request.output_directory.resolve() / "executable-search.json"
    result = _load_completed_search(artifact, request)
    if result is None:
        result = ExecutableSearchEngine(cache_root).search(
            request,
            shadow_exhaustive=shadow_exhaustive,
            ephemeral_terminal_artifacts=compact_decisive,
        )
    summary = _campaign_result_summary(result, request)
    compaction = (
        _compact_decisive_root_artifacts(request.output_directory, result)
        if compact_decisive and result.get("status") == "pass" else None
    )
    return {
        "artifact": str(artifact),
        "identifier": request.identifier,
        "summary": summary,
        "artifact_compaction": compaction,
    }


def _evaluate_terminal_process(
    cache_root: Path,
    root: CapturedRoot,
    state: LazyState,
    output: Path,
    ephemeral_artifacts: bool,
) -> dict[str, Any]:
    return ExecutableSearchEngine(cache_root)._realize_terminal(
        root, state, output, ephemeral_artifacts=ephemeral_artifacts,
    )


def _load_completed_search(
    path: Path,
    request: ExecutableSearchRequest,
) -> dict[str, Any] | None:
    """Load a durable completed root, rejecting stale or partial campaign artifacts."""
    compressed = path.with_suffix(path.suffix + ".gz")
    if not path.is_file() and not compressed.is_file():
        return None
    try:
        if path.is_file():
            result = json.loads(path.read_text())
        else:
            with gzip.open(compressed, "rt", encoding="utf-8") as stream:
                result = json.load(stream)
    except (OSError, EOFError, json.JSONDecodeError):
        return None
    if not isinstance(result, dict):
        return None
    root = result.get("root")
    if (
        result.get("schema_version") != "vladder-executable-search-result-v1"
        or result.get("search_version") != EXECUTABLE_SEARCH_VERSION
        or result.get("request_fingerprint") != _request_fingerprint(request)
        or not isinstance(root, dict)
        or root.get("identifier") != request.identifier
        or not isinstance(result.get("trace"), dict)
        or not isinstance(result.get("closure"), dict)
    ):
        return None
    return result


class DeepLazyGrammar:
    def __init__(self, grammar: Any, source: str) -> None:
        self.grammar = grammar
        self.source = source

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return (self._grammar_state(
            self.source,
            (),
            {"family": "deep-information-realization", "op": "enter"},
        ),)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        current = str(state.semantic_state["realization"])
        path = tuple(str(item) for item in state.semantic_state.get("rule_path", ()))
        seen = set(state.semantic_state.get("seen", ()))
        children: list[LazyState] = []
        if current in self.grammar.terminals:
            children.append(self._candidate_state(current, path))
        children.extend(
            self._grammar_state(
                rule.target,
                (*path, rule.id),
                {"family": rule.family, "rule": rule.id, "target": rule.target},
                (*seen, rule.target),
            )
            for rule in self.grammar.rules
            if rule.source == current and rule.target not in seen
        )
        return tuple(children)

    def _grammar_state(
        self,
        realization: str,
        path: tuple[str, ...],
        action: Mapping[str, Any],
        seen: tuple[str, ...] | None = None,
    ) -> LazyState:
        semantic = {
            "realization": realization,
            "rule_path": list(path),
            "seen": list(seen or (self.source,)),
        }
        return LazyState(
            "deep-information-realization",
            "partial_candidate",
            semantic,
            action,
            terminal=False,
            identity=canonical_hash({
                "family": "deep-information-realization",
                "stage": "partial_candidate",
                "realization": realization,
            }),
        )

    def _candidate_state(self, realization: str, path: tuple[str, ...]) -> LazyState:
        return LazyState(
            "deep-information-realization",
            "candidate",
            {
                "realization": realization,
                "rule_path": list(path),
                "candidate": True,
            },
            {
                "family": "deep-information-realization",
                "op": "emit",
                "realization": realization,
            },
            terminal=True,
        )


class CanonicalRegionLazyGrammar:
    """Expose each registered canonical rule as a separate lazy decision."""

    def __init__(self, family: str, graph: Mapping[str, Any]) -> None:
        self.grammar = CanonicalExecutableGrammar.load(family)
        self.graph = dict(graph)

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return (self._state("canonical", (), {"family": self.grammar.family, "op": "enter"}),)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        realization = str(state.semantic_state["realization"])
        path = tuple(str(item) for item in state.semantic_state.get("rule_path", ()))
        children: list[LazyState] = []
        if realization != "canonical":
            children.append(LazyState(
                "canonical-bounded-region",
                "candidate",
                {"realization": realization, "rule_path": list(path), "candidate": True},
                {
                    "family": self.grammar.family,
                    "family_version": CANONICAL_EXECUTABLE_VERSION,
                    "op": "emit",
                    "realization": realization,
                },
                terminal=True,
                decision_projection={
                    "quality": "partial_state",
                    "graph": self.graph,
                    "focus_node_ids": ["operation"],
                    "region_count": 1,
                },
            ))
        seen = set(str(item) for item in state.semantic_state.get("seen", ("canonical",)))
        children.extend(
            self._state(
                rule.target,
                (*path, rule.id),
                {
                    "family": self.grammar.family,
                    "family_version": CANONICAL_EXECUTABLE_VERSION,
                    "op": "apply_rule",
                    "rule": rule.id,
                    "proof": rule.proof,
                    "preconditions": list(rule.preconditions),
                    "target": rule.target,
                },
                (*seen, rule.target),
            )
            for rule in self.grammar.by_source.get(realization, ())
            if rule.target not in seen
        )
        return tuple(children)

    def _state(
        self,
        realization: str,
        path: tuple[str, ...],
        action: Mapping[str, Any],
        seen: tuple[str, ...] = ("canonical",),
    ) -> LazyState:
        return LazyState(
            "canonical-bounded-region",
            "partial_candidate",
            {"realization": realization, "rule_path": list(path), "seen": list(seen)},
            dict(action),
            terminal=False,
            identity=canonical_hash({
                "family": self.grammar.family,
                "realization": realization,
                "path": path,
            }),
            decision_projection={
                "quality": "partial_state",
                "graph": self.graph,
                "focus_node_ids": ["operation"],
                "region_count": 1,
            },
        )


class LifetimeLazyGrammar:
    def __init__(self, manifest: Path, trace: Path) -> None:
        self.manifest = manifest.resolve()
        self.trace = trace.resolve()
        self.graph = load_lifetime_flow_graph(self.manifest)
        self.events = load_lifetime_trace(self.trace, self.graph)
        self.attribution = attribute_lifetimes(self.graph, self.events)
        self.quality = assess_trace_quality(self.graph, self.events)

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return tuple(
            LazyState(
                "lifetime-realization",
                "candidate_family",
                {"information_id": item.id},
                {"family": "lifetime-realization", "op": "select_information", "information": item.id},
                terminal=False,
                deterministic_status="possible",
                deterministic_reason=(
                    "" if self.quality[item.id].status == "sufficient"
                    else "insufficient construction, consumption, reuse, or residency attribution"
                ),
            )
            for item in self.graph.information
        )

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        information_id = str(state.semantic_state["information_id"])
        if self.quality[information_id].status != "sufficient":
            return ()
        return tuple(
            LazyState(
                "lifetime-realization",
                "candidate",
                {"information_id": information_id, "candidate": candidate.to_dict()},
                {
                    "family": candidate.family,
                    "op": candidate.mode,
                    "scope": candidate.candidate_scope,
                    "placement": candidate.candidate_placement,
                },
                terminal=True,
                deterministic_status="possible" if candidate.legality == "legal" else "impossible",
                deterministic_reason="; ".join(candidate.diagnostics),
            )
            for candidate in discover_lifetime_candidates_for_information(
                self.graph, self.attribution, information_id,
            )
        )


class CrossTULazyGrammar:
    def __init__(self, report: Mapping[str, Any]) -> None:
        self.report = dict(report)
        self.slice = dict(report["slice"])
        self.functions = frozenset(str(item["id"]) for item in self.slice.get("functions", ()))
        self.edges = tuple(
            (str(item["source"]), str(item["destination"]))
            for item in self.slice.get("edges", ())
            if str(item["source"]) in self.functions and str(item["destination"]) in self.functions
        )
        seeds = {
            value if value in self.functions else f"cpp::{value}"
            for value in self.slice.get("seeds", ())
        }
        self.seeds = frozenset(item for item in seeds if item in self.functions)
        self.boundaries = tuple(dict(item) for item in self.slice.get("boundaries", ()))
        self.selected_build = dict(report.get("selected_build", {}))
        self.region_descriptors = {
            str(item["function_id"]): dict(item)
            for item in self.selected_build.get("functions", ())
            if isinstance(item, Mapping)
        }
        self.region_reports = {
            function_id: json.loads(Path(str(item["report"])).read_text())
            for function_id, item in self.region_descriptors.items()
            if item.get("status") == "applicable" and item.get("report")
        }
        self.domains = applicable_region_domains(self.selected_build)

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        composition = self._state(self.seeds, {"family": "cross-tu-composition", "op": "enter"})
        boundaries = tuple(
            LazyState(
                "cross-tu-composition",
                "cross_tu",
                {"boundary": boundary, "protocol_boundary": True},
                {
                    "family": "cross-tu-composition",
                    "op": "preserve_protocol_boundary",
                    "kind": boundary.get("kind"),
                    "symbol": boundary.get("symbol"),
                },
                terminal=False,
                deterministic_status="impossible",
                deterministic_reason="external or ambiguous call boundary is outside executable cross-TU composition",
                identity=canonical_hash({
                    "family": "cross-tu-composition",
                    "protocol_boundary": boundary,
                }),
            )
            for boundary in self.boundaries
        )
        inapplicable = tuple(
            LazyState(
                "cross-tu-selected-build",
                "cross_tu",
                {"function_id": function_id, "local_region_inapplicable": True},
                {
                    "family": "cross-tu-selected-build",
                    "op": "local_region_inapplicable",
                },
                terminal=False,
                deterministic_status="impossible",
                deterministic_reason=str(descriptor.get("reason") or "no bounded local region"),
                identity=canonical_hash({
                    "family": "cross-tu-selected-build",
                    "function": function_id,
                    "inapplicable": True,
                }),
            )
            for function_id, descriptor in sorted(self.region_descriptors.items())
            if descriptor.get("status") != "applicable"
        )
        return (composition, *boundaries, *inapplicable)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        if state.semantic_state.get("protocol_boundary"):
            return ()
        if state.semantic_state.get("phase") == "schedule":
            return self._expand_schedule(state)
        selected = frozenset(str(item) for item in state.semantic_state["selected_functions"])
        additions: set[tuple[str, str, str]] = set()
        for source, destination in self.edges:
            if source in selected and destination not in selected:
                additions.add((destination, source, destination))
            if destination in selected and source not in selected:
                additions.add((source, source, destination))
        if not additions:
            regions = self._regions(selected)
            if not regions:
                summary = LazyState(
                    "cross-tu-composition",
                    "composition",
                    {"selected_functions": sorted(selected), "summary_only": True},
                    {"family": "cross-tu-composition", "op": "emit_summary_composition"},
                    terminal=True,
                )
                no_regions = LazyState(
                    "cross-tu-selected-build",
                    "cross_tu",
                    {"selected_functions": sorted(selected), "no_executable_regions": True},
                    {"family": "cross-tu-selected-build", "op": "no_executable_regions"},
                    terminal=False,
                    deterministic_status="impossible",
                    deterministic_reason="the closed definition slice contains no executable local grammar region",
                )
                return summary, no_regions
            return (self._schedule_state(
                selected,
                {},
                0,
                {"family": "cross-tu-selected-build", "op": "enter_regional_composition"},
            ),)
        return tuple(
            self._state(
                selected | {addition},
                {
                    "family": "cross-tu-composition",
                    "op": "add_definition_edge",
                    "source": source,
                    "destination": destination,
                },
            )
            for addition, source, destination in sorted(additions)
        )

    @staticmethod
    def _state(selected: frozenset[str], action: Mapping[str, Any]) -> LazyState:
        return LazyState(
            "cross-tu-composition",
            "cross_tu",
            {"selected_functions": sorted(selected), "phase": "function"},
            action,
            terminal=False,
            identity=canonical_hash({
                "family": "cross-tu-composition",
                "selected_functions": sorted(selected),
            }),
        )

    def _regions(self, selected: frozenset[str]) -> tuple[tuple[str, str, str], ...]:
        result: list[tuple[str, str, str]] = []
        for function_id in sorted(selected):
            report = self.region_reports.get(function_id)
            if report is None:
                continue
            grammar = SelectedBuildCppGrammar(report)
            result.extend(
                (region_key(function_id, region), function_id, region)
                for region in grammar.regions
            )
        return tuple(result)

    def _expand_schedule(self, state: LazyState) -> Iterable[LazyState]:
        selected = frozenset(str(item) for item in state.semantic_state["selected_functions"])
        regions = self._regions(selected)
        index = int(state.semantic_state["next_region"])
        if index >= len(regions):
            return ()
        key, function_id, region = regions[index]
        selection = {
            str(name): str(value)
            for name, value in state.semantic_state.get("region_selection", {}).items()
        }
        report = self.region_reports[function_id]
        grammar = SelectedBuildCppGrammar(report)
        return tuple(
            self._schedule_state(
                selected,
                {**selection, key: choice},
                index + 1,
                self._schedule_action(grammar, region, choice),
                function_id=function_id,
                region=region,
            )
            for choice in self.domains[key]
        )

    def _schedule_state(
        self,
        selected: frozenset[str],
        selection: Mapping[str, str],
        next_region: int,
        action: Mapping[str, Any],
        *,
        function_id: str | None = None,
        region: str | None = None,
    ) -> LazyState:
        regions = self._regions(selected)
        terminal = next_region == len(regions)
        projection = (
            selected_build_projection(self.region_reports[function_id], current_region=region)
            if function_id is not None else
            {"quality": "partial_state", "graph": cross_tu_semantic_flow_graph(self.report).to_dict()}
        )
        return LazyState(
            "cross-tu-selected-build",
            "composition" if terminal else "cross_tu",
            {
                "selected_functions": sorted(selected),
                "phase": "schedule",
                "region_selection": dict(sorted(selection.items())),
                "next_region": next_region,
                "remaining_regions": [item[0] for item in regions[next_region:]],
            },
            dict(action),
            terminal=terminal,
            identity=canonical_hash({
                "family": "cross-tu-selected-build",
                "selected_functions": sorted(selected),
                "selection": dict(sorted(selection.items())),
                "next_region": next_region,
            }),
            decision_projection=projection,
        )

    @staticmethod
    def _schedule_action(
        grammar: SelectedBuildCppGrammar,
        region: str,
        choice: str,
    ) -> dict[str, Any]:
        if choice == "baseline":
            return {
                "family": "cross-tu-selected-build",
                "op": "select_schedule",
                "rule": "baseline-schedule",
                "region": region,
                "choice": choice,
            }
        candidate = grammar.by_region[region][choice]
        return {
            "family": str(candidate.get("schedule_family") or "cross-tu-selected-build"),
            "op": "select_schedule",
            "rule": str(candidate.get("rule") or choice),
            "region": region,
            "choice": choice,
            "factor": candidate.get("factor"),
        }


class ProtocolLazyGrammar:
    def __init__(self, projections: tuple[str, ...]) -> None:
        self.projections = projections

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return (LazyState(
            "bounded-protocol",
            "partial_candidate",
            {"projection": None},
            {"family": "bounded-protocol", "op": "enter"},
            terminal=False,
        ),)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return tuple(
            LazyState(
                "bounded-protocol",
                "candidate",
                {"projection": projection},
                {"family": "bounded-protocol", "op": "verify_projection", "projection": projection},
                terminal=True,
            )
            for projection in self.projections
        )


class SourceFamilyDispatchGrammar:
    """Expose source-family selection as the first real lazy-search decision."""

    def __init__(self, engine: ExecutableSearchEngine, alternatives: tuple[CapturedRoot, ...]) -> None:
        self.engine = engine
        self.alternatives = {
            _dispatch_family_id(item): item
            for item in alternatives
        }
        self.delegates = {
            family: engine._lazy_grammar(item)
            for family, item in self.alternatives.items()
            if not item.unresolved_contracts
        }

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        result: list[LazyState] = []
        for family, captured in sorted(self.alternatives.items()):
            soundly_impossible = bool(captured.unresolved_contracts) and captured.blocked_authority == "sound_contract"
            result.append(LazyState(
                family,
                "grammar_family",
                {
                    "dispatch_family": family,
                    "captured_family": captured.family,
                    "captured_semantic_hash": captured.semantic_hash,
                    "unresolved_contracts": list(captured.unresolved_contracts),
                },
                {
                    "action_key": f"dispatch:{family}",
                    "family": family,
                    "family_version": captured.grammar_version,
                    "op": "family_opportunity",
                    "footprint": {
                        "complete": True,
                        "reads": ["captured-family-registry"],
                        "writes": [f"dispatch-selection:{family}"],
                        "owners": [f"dispatch-family:{family}"],
                        "representations_read": ["captured-semantic-root"],
                        "representations_written": [f"family-root:{family}"],
                    },
                },
                terminal=False,
                deterministic_status="impossible" if soundly_impossible else "possible",
                deterministic_reason="; ".join(captured.unresolved_contracts),
                decision_projection={
                    "quality": "partial_state",
                    "graph": captured.graph,
                    "focus_node_ids": [],
                    "region_count": 0,
                },
            ))
        return tuple(result)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        family = str(state.semantic_state["dispatch_family"])
        captured = self.alternatives[family]
        if state.stage == "grammar_family":
            if captured.unresolved_contracts:
                return (LazyState(
                    family,
                    "candidate_family",
                    {
                        "dispatch_family": family,
                        "captured_family": captured.family,
                        "unresolved_contracts": list(captured.unresolved_contracts),
                        "blocked_missing_contract": True,
                    },
                    {
                        "family": family,
                        "family_version": captured.grammar_version,
                        "op": "blocked_missing_contract",
                    },
                    terminal=True,
                    decision_projection={
                        "quality": "partial_state",
                        "graph": captured.graph,
                        "focus_node_ids": [],
                        "region_count": 0,
                    },
                ),)
            return tuple(self._tag(item, family) for item in self.delegates[family].initial_states(root_context))
        return tuple(self._tag(item, family) for item in self.delegates[family].expand(state, root_context))

    def enabled_actions(
        self, state: LazyState, root_context: Mapping[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        family = str(state.semantic_state["dispatch_family"])
        if state.stage != "grammar_family":
            delegate = self.delegates.get(family)
            enabled = getattr(delegate, "enabled_actions", None)
            if callable(enabled):
                return tuple(dict(action) for action in enabled(state, root_context))
        return tuple(dict(child.action) for child in self.expand(state, root_context))

    def apply_action(
        self,
        state: LazyState | None,
        action: Mapping[str, Any],
        root_context: Mapping[str, Any],
    ) -> LazyState | None:
        if state is None:
            return None
        family = str(state.semantic_state["dispatch_family"])
        if state.stage != "grammar_family":
            delegate = self.delegates.get(family)
            apply = getattr(delegate, "apply_action", None)
            if callable(apply):
                child = apply(state, action, root_context)
                return self._tag(child, family) if child is not None else None
        for child in self.expand(state, root_context):
            if dict(child.action) == dict(action):
                return child
        return None

    @staticmethod
    def _tag(state: LazyState, family: str) -> LazyState:
        return replace(
            state,
            semantic_state={**dict(state.semantic_state), "dispatch_family": family},
            # Preserve the delegated grammar's canonical semantic identity. Recomputing from
            # ``state.family`` makes action order observable when the last selected schedule has
            # a different family, defeating exact transposition collapse.
            identity=canonical_hash({
                "dispatch_family": family,
                "delegate_identity": state.identity,
            }),
        )

class ExecutableSearchEngine:
    def __init__(self, cache_directory: Path | None = None) -> None:
        self.cache = ContentAddressedEvidenceCache(cache_directory or Path(".vladder-cache/executable-search"))
        self.lazy = LazySearchEngine()
        self.canonical = CanonicalSearchEngine()
        self.production = ProductionCanonicalSearchEngine()

    def capture(self, request: ExecutableSearchRequest) -> CapturedRoot:
        requested = request.family
        source_region: str | None = None
        language = request.language or _language_from_source(request.source)
        if requested in {"protocol", "bounded-protocol"} or request.protocol_manifest is not None:
            if request.protocol_manifest is None:
                return self._blocked_root(
                    request,
                    "bounded-protocol",
                    None,
                    "language-neutral",
                    ("a bounded protocol manifest is required",),
                    blocked_authority="sound_contract",
                )
            raw = _load_structured_mapping(request.protocol_manifest)
            projections = protocol_projection_domains(raw)
            graph = protocol_semantic_flow_graph(raw, request.identifier).to_dict()
            protocol_kind = "device" if raw.get("kind") in {"queue", "dma", "presentation"} else "state"
            contract = {
                "manifest": str(request.protocol_manifest.resolve()),
                "protocol_kind": protocol_kind,
                "protocol": str(raw.get("protocol") or raw.get("kind")),
            }
            return CapturedRoot(
                request,
                "bounded-protocol",
                "bounded-protocol-search-v1",
                graph,
                contract,
                canonical_hash({"graph": graph, "contract": contract}),
                None,
                "declared-protocol",
                {"projection": projections},
                (),
                ("external implementation internals", "physical timing", "owning source realization"),
                "bounded state/device protocol manifest",
            )
        if requested in {"lifetime", "lifetime-realization"} or request.lifetime_manifest or request.lifetime_trace:
            if request.lifetime_manifest is None or request.lifetime_trace is None:
                return self._blocked_root(
                    request,
                    "lifetime-realization",
                    None,
                    "language-neutral",
                    ("lifetime manifest and runtime trace are both required",),
                    blocked_authority="sound_contract",
                )
            lifetime_graph = load_lifetime_flow_graph(request.lifetime_manifest)
            graph = lifetime_semantic_flow_graph(lifetime_graph).to_dict()
            contract = {
                "manifest": str(request.lifetime_manifest.resolve()),
                "trace": str(request.lifetime_trace.resolve()),
                "semantic_contract": lifetime_graph.contract,
            }
            return CapturedRoot(
                request,
                "lifetime-realization",
                "lifetime-v1",
                graph,
                contract,
                canonical_hash({"graph": graph, "contract": contract}),
                None,
                "current-realization-policy",
                {"information": tuple(item.id for item in lifetime_graph.information)},
                (),
                ("owning repository source reconstruction",),
                "lifetime manifest plus attributed runtime identity trace",
            )
        if requested in {"cross-tu", "cross-tu-composition"} or request.compile_commands and request.cross_tu_seeds:
            if request.compile_commands is None or not request.cross_tu_seeds:
                return self._blocked_root(
                    request,
                    "cross-tu-composition",
                    None,
                    "cpp",
                    ("compile_commands and at least one cross-TU seed are required",),
                    blocked_authority="sound_contract",
                )
            closure_output = request.output_directory.resolve() / "cross-tu-capture"
            report = run_cross_tu_closure(
                request.compile_commands,
                request.cross_tu_seeds,
                closure_output,
                max_upstream=request.max_upstream,
                max_downstream=request.max_downstream,
                max_nodes=request.max_cross_tu_nodes,
            )
            if not report["slice"].get("functions"):
                return self._blocked_root(
                    request,
                    "cross-tu-composition",
                    None,
                    "cpp",
                    ("cross-TU seeds resolved to no unique selected-build definitions",),
                    blocked_authority="sound_contract",
                )
            selected_build = capture_cross_tu_selected_build_regions(
                report,
                request.compile_commands,
                closure_output / "selected-build-regions",
                maximum_functions=request.max_cross_tu_nodes,
            )
            report["selected_build"] = selected_build
            report["candidate_generation_performed"] = bool(selected_build["region_count"])
            report_path = closure_output / "cross-tu-closure-report.json"
            _write_json(report_path, report)
            graph = cross_tu_semantic_flow_graph(report).to_dict()
            contract = {
                "report": str(report_path),
                "seeds": list(request.cross_tu_seeds),
                "budgets": report["slice"]["budgets"],
                "truncated": bool(report["slice"].get("truncated")),
                "selected_build_region_count": int(selected_build["region_count"]),
            }
            return CapturedRoot(
                request,
                "cross-tu-composition",
                "cross-tu-composition-v1",
                graph,
                contract,
                canonical_hash({"graph": graph, "contract": contract}),
                None,
                "baseline" if selected_build["region_count"] else "call-preserving-selected-build-slice",
                {
                    "definition": tuple(sorted(item["id"] for item in report["slice"]["functions"])),
                    **applicable_region_domains(selected_build),
                },
                (),
                tuple(str(item.get("symbol") or item.get("kind")) for item in report["slice"].get("boundaries", ())),
                "whole-build index plus definition-visible summary and selected-build regional closure",
            )
        if request.source is not None:
            if not request.function:
                raise ValueError("source search requires a function")
            text = request.source.read_text(errors="replace")
            source_region = None
            compiler_selection_error: str | None = None
            if language == "cpp" and request.compile_commands is not None:
                report = self._inspect_cpp_report(request)
                selection = report.get("selection") if isinstance(report.get("selection"), dict) else {}
                source_range = selection.get("source_range")
                if (
                    isinstance(source_range, list)
                    and len(source_range) == 2
                    and all(isinstance(item, int) for item in source_range)
                    and 0 <= int(source_range[0]) < int(source_range[1]) <= len(text)
                ):
                    source_region = text[int(source_range[0]):int(source_range[1])]
                else:
                    compiler_selection_error = "Clang selection did not provide one valid exact source range"
            if source_region is None:
                try:
                    source_region = extract_named_source_region(text, request.function, language)
                except ValueError as error:
                    return self._blocked_root(
                        request,
                        requested if requested != "auto" else "unbound-semantic-root",
                        None,
                        language,
                        tuple(item for item in (compiler_selection_error, str(error)) if item),
                    )

        if requested == "auto" and source_region is not None:
            return self._capture_source_dispatch(request, source_region, language)

        if requested == "canonical-bounded-region" and source_region:
            try:
                canonical_region = classify_canonical_region(
                    language,
                    source_region,
                    _canonical_signature(language, source_region, request),
                )
            except (CanonicalRegionError, ValueError) as error:
                reason = error.reason if isinstance(error, CanonicalRegionError) else str(error)
                authority = "sound_contract" if isinstance(error, CanonicalRegionError) else "incomplete"
                return self._blocked_root(
                    request,
                    requested,
                    source_region,
                    language,
                    (reason,),
                    blocked_authority=authority,
                )
            evidence = _compiler_canonical_evidence(
                request, canonical_region, source_region,
                request.output_directory.resolve() / "canonical-capture",
            )
            corroboration = dict(evidence.get("corroboration", {}))
            if corroboration.get("status") != "pass":
                return self._blocked_root(
                    request,
                    requested,
                    source_region,
                    language,
                    (str(evidence.get("reason") or "compiler shape did not corroborate the canonical region"),),
                    blocked_authority="incomplete",
                    contract_override={
                        "canonical_region": canonical_region.to_dict(),
                        "compiler_corroboration": corroboration,
                    },
                )
            graph = build_canonical_graph(
                canonical_region,
                name=request.function or request.identifier,
                language=language,
                compiler_identity=str(evidence.get("compiler_identity") or "captured-native-compiler"),
                semantic_ir=str(evidence.get("semantic_ir") or "compiler-corroborated-canonical-region"),
                function_identity=request.function or request.identifier,
                source_provenance={
                    "language": language,
                    "source": str(request.source.resolve()) if request.source else None,
                    "source_sha256": hashlib.sha256(source_region.encode()).hexdigest(),
                },
                language_contracts=dict(evidence.get("language_contracts", {})),
                compiler_corroboration=corroboration,
                excluded_claims=(
                    "owning wrapper equivalence",
                    "external protocol equivalence",
                    "performance improvement before physical measurement",
                ),
            ).to_dict()
            grammar = CanonicalExecutableGrammar.load(canonical_region.family)
            return CapturedRoot(
                request,
                "canonical-bounded-region",
                CANONICAL_EXECUTABLE_VERSION,
                graph,
                {
                    "canonical_region": canonical_region.to_dict(),
                    "compiler_corroboration": corroboration,
                    "source_assembly_identity": evidence.get("source_assembly_identity"),
                },
                canonical_hash({"graph": graph, "region": canonical_region.region_hash}),
                source_region,
                "canonical",
                {"realization": tuple(item.realization for item in grammar.derivations())},
                (),
                (),
                "compiler-corroborated canonical bounded region",
            )

        if requested == "deep-information-realization" and source_region:
            realization = inspect_source_realization(source_region, language, request.function or "root")
            if realization.representable:
                contract = DeepKernelContract("exact-byte-predicate-reduction", str(realization.predicate))
                graph = build_deep_realization_graph(
                    contract,
                    str(realization.realization),
                    source_language=language,
                    function_identity=request.function or "root",
                ).semantic_graph.to_dict()
                grammar = load_deep_grammar()
                return CapturedRoot(
                    request,
                    "deep-information-realization",
                    grammar.version,
                    graph,
                    contract.to_dict(),
                    canonical_hash({"graph": graph, "contract": contract.to_dict()}),
                    source_region,
                    realization.realization,
                    {"grammar_path": tuple(rule.id for rule in grammar.rules)},
                    (),
                    tuple(realization.blockers),
                    "compiler/source semantic realization classifier",
                )
            if requested == "deep-information-realization":
                return self._blocked_root(
                    request,
                    requested,
                    source_region,
                    language,
                    tuple(realization.blockers) or ("deep source archetype absent",),
                    blocked_authority="sound_contract",
                )

        if requested == "ordered-prefix-suffix" and source_region:
            contract = detect_ordered_reduction(source_region)
            if contract is not None:
                graph = build_ordered_reduction_graph(contract, language=language, function=request.function or "root").to_dict()
                return CapturedRoot(
                    request,
                    "ordered-prefix-suffix",
                    ORDERED_PREFIX_GRAMMAR_VERSION,
                    graph,
                    contract.to_dict(),
                    canonical_hash({"graph": graph, "contract": contract.to_dict()}),
                    source_region,
                    "factor-1",
                    {"factor": (1, 2, 4, 8)},
                    (),
                    (
                        ("embedded owning wrapper and live-value projection",)
                        if contract.source_binding == "embedded-bounded-subregion" else
                        ("contiguous container ownership and mutation",)
                        if contract.source_binding == "borrowed-contiguous" else
                        ()
                    ),
                    "ordered early-termination source classifier",
                )
            if requested == "ordered-prefix-suffix":
                return self._blocked_root(
                    request,
                    requested,
                    source_region,
                    language,
                    ("ordered early-termination pattern absent",),
                    blocked_authority="sound_contract",
                )

        if requested == "bit-popcount-reduction" and source_region:
            bit_contract = detect_bit_reduction(
                source_region,
                source_context=(
                    request.source.read_text(errors="replace")
                    if request.source is not None else None
                ),
                function=request.function,
            )
            if bit_contract is not None:
                graph = build_bit_reduction_graph(
                    bit_contract,
                    language=language,
                    function=request.function or "root",
                ).to_dict()
                return CapturedRoot(
                    request,
                    "bit-popcount-reduction",
                    BIT_REDUCTION_GRAMMAR_VERSION,
                    graph,
                    bit_contract.to_dict(),
                    canonical_hash({"graph": graph, "contract": bit_contract.to_dict()}),
                    source_region,
                    bit_reduction_realizations(bit_contract)[0],
                    {"realization": bit_reduction_realizations(bit_contract)},
                    (),
                    ("nullable or owning wrapper",),
                    "exact fixed-width popcount reduction source classifier",
                )
            if requested == "bit-popcount-reduction":
                return self._blocked_root(
                    request,
                    requested,
                    source_region,
                    language,
                    ("exact byte popcount reduction pattern absent",),
                    blocked_authority="sound_contract",
                )

        if requested == "predicate-reduction" and source_region:
            predicate_contract = detect_predicate_reduction(source_region)
            if predicate_contract is not None:
                graph = build_predicate_reduction_graph(
                    predicate_contract,
                    language=language,
                    function=request.function or "root",
                ).to_dict()
                return CapturedRoot(
                    request,
                    "predicate-reduction",
                    PREDICATE_REDUCTION_GRAMMAR_VERSION,
                    graph,
                    predicate_contract.to_dict(),
                    canonical_hash({"graph": graph, "contract": predicate_contract.to_dict()}),
                    source_region,
                    "branch-u1",
                    {
                        "style": PREDICATE_REDUCTION_STYLES,
                        "unroll": PREDICATE_REDUCTION_UNROLLS,
                    },
                    (),
                    (
                        "owning wrapper projection"
                        if predicate_contract.source_binding != "borrowed-contiguous-sequence"
                        else "owning wrapper lifetime",
                    ),
                    "language-neutral exact predicate reduction source classifier",
                )
            if requested == "predicate-reduction":
                return self._blocked_root(
                    request,
                    requested,
                    source_region,
                    language,
                    ("exact total predicate reduction pattern absent",),
                    blocked_authority="sound_contract",
                )

        contract_raw = dict(request.contract or {})
        dataflow_raw = contract_raw.get("bounded_dataflow", contract_raw if contract_raw.get("family") else None)
        requested_dataflow_family = requested if requested in {
            "predicate-stable-compaction", "fixed-width-codec", "stateful-delta-transducer",
            "aos-fused-multi-reduction", "quantized-block-4x4",
        } else None
        if (
            requested_dataflow_family
            and isinstance(dataflow_raw, dict)
            and dataflow_raw.get("family")
            and dataflow_raw.get("family") != requested_dataflow_family
        ):
            return self._blocked_root(
                request,
                "bounded-variable-output-dataflow",
                source_region,
                language,
                (f"declared bounded dataflow family is {dataflow_raw['family']}, not {requested_dataflow_family}",),
                blocked_authority="sound_contract",
            )
        if dataflow_raw is None and source_region and (
            requested == "bounded-variable-output-dataflow" or requested_dataflow_family
        ):
            overrides = dict(contract_raw)
            if requested_dataflow_family:
                overrides["family"] = requested_dataflow_family
            compiler_report = (
                self._inspect_cpp_report(request)
                if language == "cpp" and request.compile_commands is not None else None
            )
            inferred = infer_bounded_dataflow_contracts(
                source_region,
                request.function or "root",
                overrides=overrides,
                compiler_report=compiler_report,
            )
            if requested_dataflow_family:
                inferred = tuple(item for item in inferred if item.family == requested_dataflow_family)
            complete = tuple(item for item in inferred if item.status == "complete")
            if len(complete) == 1:
                dataflow_raw = dict(complete[0].inferred)
            elif inferred:
                unresolved = tuple(
                    f"{item.family}: {obligation}"
                    for item in inferred for obligation in item.unresolved
                )
                if len(complete) > 1:
                    unresolved = ("multiple complete bounded dataflow families require explicit family selection",)
                return self._blocked_root(
                    request,
                    "bounded-variable-output-dataflow",
                    source_region,
                    language,
                    unresolved,
                    blocked_authority="incomplete",
                    contract_override={
                        "inference_version": "bounded-dataflow-contract-inference-v1",
                        "inferences": [item.to_dict() for item in inferred],
                    },
                )
        if requested == "bounded-variable-output-dataflow" or requested_dataflow_family is not None or dataflow_raw:
            if not isinstance(dataflow_raw, dict):
                return self._blocked_root(
                    request,
                    "bounded-variable-output-dataflow",
                    source_region,
                    language,
                    ("bounded dataflow contract missing",),
                    blocked_authority="sound_contract",
                )
            contract = BoundedDataflowContract.from_dict(dataflow_raw)
            grammar = load_bounded_dataflow_grammar()
            source_realization = grammar.sources[contract.family]
            graph = build_bounded_dataflow_graph(contract, source_realization, source_language=language).semantic_graph.to_dict()
            reconstruction: dict[str, Any] | None = None
            if language == "cpp" and request.compile_commands is not None:
                compiler_report = self._inspect_cpp_report(request)
                applicable, reason = exact_dataflow_reconstruction_applicable(
                    source_region,
                    request.function or "root",
                    contract,
                    compiler_report,
                )
                reconstruction = {
                    "applicable": applicable,
                    "reason": reason,
                    "report": str(
                        request.output_directory.resolve()
                        / "selected-build-capture"
                        / "cpp-support.json"
                    ),
                }
            return CapturedRoot(
                request,
                "bounded-variable-output-dataflow",
                grammar.version,
                graph,
                {
                    "bounded_dataflow": contract.to_dict(),
                    **({"cpp_reconstruction": reconstruction} if reconstruction is not None else {}),
                },
                canonical_hash({"graph": graph, "contract": contract.to_dict()}),
                source_region,
                source_realization,
                {"realization": grammar.family_terminals(contract.family)},
                (),
                (() if reconstruction and reconstruction["applicable"] else ("owning wrapper and publication protocol",)),
                "explicit bounded dataflow contract",
            )

        if (
            requested == "llvm-function-pipeline"
            and language == "cpp"
            and request.source is not None
            and request.compile_commands is not None
        ):
            report = self._inspect_cpp_report(request)
            graph = report.get("region_closure", {}).get("semantic_graph")
            capture = capture_llvm_function(
                report,
                request.output_directory.resolve() / "llvm-function-capture",
            )
            if capture.get("status") == "pass" and isinstance(graph, dict):
                contract = {
                    "capture": str(capture["artifact"]),
                    "selected_symbol": capture["symbol"],
                    "claim_boundary": capture["claim_boundary"],
                }
                return CapturedRoot(
                    request,
                    "llvm-function-pipeline",
                    LLVM_FUNCTION_GRAMMAR_VERSION,
                    graph,
                    contract,
                    canonical_hash({"graph": graph, "contract": contract}),
                    source_region,
                    "baseline",
                    {"pipeline": tuple(item.id for item in load_llvm_function_pipelines())},
                    (),
                    tuple(
                        str(item.get("category"))
                        for item in report.get("closure", {}).get("protocol_scopes", ())
                        if item.get("categorical_for_generic_ingestion")
                    ),
                    "selected-function LLVM module plus finite refinement-checked pass grammar",
                )
            return self._blocked_root(
                request,
                "llvm-function-pipeline",
                source_region,
                language,
                (str(capture.get("reason") or "selected function LLVM extraction failed"),),
                contract_override={
                    "selected_symbol": report.get("selection", {}).get("symbol"),
                    "capture": capture,
                },
            )

        if (
            requested == "selected-build-cpp"
            and language == "cpp"
            and request.source is not None
            and request.compile_commands is not None
        ):
            selected_directory = request.output_directory.resolve() / "selected-build-capture"
            report = self._inspect_cpp_report(request)
            closure = report.get("closure", {})
            selected_regions_raw = dict(request.contract or {}).get("selected_build_regions")
            selected_regions = (
                tuple(str(item) for item in selected_regions_raw)
                if isinstance(selected_regions_raw, (list, tuple)) else None
            )
            available_regions_ordered = tuple(
                str(item.get("id"))
                for item in closure.get("regions", ())
                if isinstance(item, dict) and (item.get("eligible") or item.get("schedule_eligible"))
            )
            available_regions = frozenset(available_regions_ordered)
            max_selected_raw = dict(request.contract or {}).get("max_selected_build_regions")
            max_selected = int(max_selected_raw) if max_selected_raw is not None else None
            if max_selected is not None and max_selected < 1:
                return self._blocked_root(
                    request,
                    "selected-build-cpp",
                    source_region,
                    language,
                    ("max_selected_build_regions must be positive",),
                    blocked_authority="sound_contract",
                )
            if selected_regions is None and max_selected is not None:
                selected_regions = available_regions_ordered[:max_selected]
            omitted_regions = tuple(
                region for region in available_regions_ordered
                if selected_regions is not None and region not in selected_regions
            )
            missing_regions = set(selected_regions or ()) - available_regions
            if missing_regions:
                return self._blocked_root(
                    request,
                    "selected-build-cpp",
                    source_region,
                    language,
                    (f"selected compiler regions are absent or ineligible: {sorted(missing_regions)}",),
                    blocked_authority="sound_contract",
                )
            eligible_regions = tuple(
                item for item in closure.get("regions", ())
                if isinstance(item, dict)
                and (item.get("eligible") or item.get("schedule_eligible"))
                and (selected_regions is None or str(item.get("id")) in selected_regions)
            )
            graph = report.get("region_closure", {}).get("semantic_graph")
            if report.get("selection") and eligible_regions and isinstance(graph, dict):
                report_path = selected_directory / "cpp-support.json"
                contract = {
                    "report": str(report_path),
                    "compile_command_sha256": report.get("compile_command", {}).get("command_sha256"),
                    "selected_symbol": report.get("selection", {}).get("symbol"),
                    "selected_regions": list(selected_regions or ()),
                    "omitted_regions": list(omitted_regions),
                    "max_selected_build_regions": max_selected,
                    "claim_boundary": (
                        f"{closure.get('claim_boundary')}; exhaustive composition is bounded to "
                        f"{len(selected_regions or available_regions_ordered)} selected regions and "
                        f"excludes {len(omitted_regions)} additional eligible regions"
                    ),
                }
                return CapturedRoot(
                    request,
                    "selected-build-cpp",
                    SELECTED_BUILD_GRAMMAR_VERSION,
                    graph,
                    contract,
                    canonical_hash({"graph": graph, "contract": contract}),
                    source_region,
                    "baseline",
                    selected_build_parameter_domains(report, selected_regions),
                    (),
                    tuple(
                        str(item.get("category"))
                        for item in closure.get("protocol_scopes", ())
                        if item.get("categorical_for_generic_ingestion")
                    ),
                    "Clang selected-build closure plus proved source schedule capsules",
                )
            if report.get("selection") and isinstance(graph, dict):
                contract = {
                    "support_tier": report.get("support_tier"),
                    "selected_symbol": report.get("selection", {}).get("symbol"),
                    "candidate_generation": "no applicable typed loop schedule regions",
                }
                return CapturedRoot(
                    request,
                    "selected-build-cpp",
                    SELECTED_BUILD_GRAMMAR_VERSION,
                    graph,
                    contract,
                    canonical_hash({"graph": graph, "contract": contract}),
                    source_region,
                    None,
                    {},
                    ("typed loop-schedule family is soundly inapplicable to the selected build region",),
                    (),
                    "Clang selected-build closure with no eligible schedule region",
                    "sound_contract",
                )
            if report.get("adapters"):
                return self._blocked_root(
                    request,
                    "selected-build-cpp",
                    source_region,
                    language,
                    tuple(str(item.get("reason")) for item in report["adapters"]),
                    contract_override={
                        "support_tier": report.get("support_tier"),
                        "adapter_kinds": [item.get("kind") for item in report["adapters"]],
                    },
                )

        if requested == "selected-build-cpp":
            return self._blocked_root(
                request,
                requested,
                source_region,
                language,
                ("selected-build C++ requires C++ source and compile_commands.json",),
                blocked_authority="sound_contract",
            )

        return self._blocked_root(
            request,
            requested if requested != "auto" else "unbound-semantic-root",
            source_region,
            language,
            ("no executable bounded grammar recognized",),
        )

    def _capture_source_dispatch(
        self,
        request: ExecutableSearchRequest,
        source_region: str,
        language: str,
    ) -> CapturedRoot:
        families = list(SOURCE_DISPATCH_FAMILIES)
        if language == "cpp":
            families.extend(("selected-build-cpp", *COMPILER_SOURCE_FAMILIES))
        compiler_report = (
            self._inspect_cpp_report(request)
            if language == "cpp" and request.compile_commands is not None else None
        )
        detected_dataflow = {
            item.family
            for item in infer_bounded_dataflow_contracts(
                source_region,
                request.function or "root",
                overrides=request.contract or {},
                compiler_report=compiler_report,
            )
        }
        declared_dataflow = dict(request.contract or {}).get("bounded_dataflow")
        if not isinstance(declared_dataflow, dict):
            declared_dataflow = request.contract if isinstance(request.contract, dict) else {}
        declared_family = declared_dataflow.get("family") if isinstance(declared_dataflow, dict) else None
        if declared_family in {
            "predicate-stable-compaction", "fixed-width-codec", "stateful-delta-transducer",
            "aos-fused-multi-reduction", "quantized-block-4x4",
        }:
            detected_dataflow.add(str(declared_family))
        alternatives_list: list[CapturedRoot] = []
        for family in families:
            if family in {
                "predicate-stable-compaction", "fixed-width-codec", "stateful-delta-transducer",
                "aos-fused-multi-reduction", "quantized-block-4x4",
            } and family not in detected_dataflow:
                alternatives_list.append(self._blocked_root(
                    replace(request, family=family),
                    "bounded-variable-output-dataflow",
                    source_region,
                    language,
                    (f"{family} source archetype absent",),
                    blocked_authority="sound_contract",
                ))
            else:
                alternatives_list.append(self.capture(replace(request, family=family)))
        alternatives = tuple(alternatives_list)
        successful = tuple(item for item in alternatives if not item.unresolved_contracts)
        preferred = next(
            (item for item in successful if item.family == "selected-build-cpp"),
            max(successful, key=lambda item: len(item.graph.get("nodes", ())), default=None),
        )
        graph = preferred.graph if preferred is not None else _generic_graph(
            request.function or request.identifier,
            language,
            source_region,
        )
        contract = {
            "source_contract": dict(request.contract or {}),
            "family_registry": [
                {
                    "dispatch_family": _dispatch_family_id(item),
                    "captured_family": item.family,
                    "grammar_version": item.grammar_version,
                    "status": "applicable" if not item.unresolved_contracts else (
                        "inapplicable" if item.blocked_authority == "sound_contract" else "missing_contract"
                    ),
                }
                for item in alternatives
            ],
            "family_contracts": [
                {
                    "dispatch_family": _dispatch_family_id(item),
                    "captured_family": item.family,
                    "contract": {
                        key: item.contract[key]
                        for key in (
                            "selected_regions", "omitted_regions", "max_selected_build_regions",
                            "selected_symbol", "claim_boundary", "bounded_dataflow",
                        )
                        if key in item.contract
                    },
                }
                for item in alternatives
            ],
        }
        semantic_hash = canonical_hash({"graph": graph, "contract": contract})
        parameter_domains = {"family": tuple(_dispatch_family_id(item) for item in alternatives)}
        for item in alternatives:
            for name, values in item.parameter_domains.items():
                parameter_domains[f"{_dispatch_family_id(item)}.{name}"] = values
        return CapturedRoot(
            request,
            "source-family-dispatch",
            EXECUTABLE_GRAMMAR_REGISTRY_VERSION,
            graph,
            contract,
            semantic_hash,
            source_region,
            None,
            parameter_domains,
            (),
            tuple(sorted({boundary for item in alternatives for boundary in item.external_boundaries})),
            "source semantic root plus independent family applicability closures",
            "complete",
            alternatives,
        )

    def _inspect_cpp_report(self, request: ExecutableSearchRequest) -> dict[str, Any]:
        if request.source is None or request.compile_commands is None:
            raise ValueError("C++ compiler capture requires source and compile_commands.json")
        selected_directory = request.output_directory.resolve() / "selected-build-capture"
        artifact = selected_directory / "cpp-support.json"
        if artifact.is_file():
            try:
                cached = json.loads(artifact.read_text())
            except (OSError, json.JSONDecodeError):
                cached = None
            if (
                isinstance(cached, dict)
                and cached.get("support_version") == CPP_SUPPORT_VERSION
                and cached.get("source_sha256") == hashlib.sha256(request.source.read_bytes()).hexdigest()
                and cached.get("compile_command", {}).get("database") == str(request.compile_commands.resolve())
                and cached.get("requested_symbol") == request.symbol
                and cached.get("requested_source_line") == request.source_line
            ):
                return cached
        return inspect_cpp_region(
            request.source,
            request.function or "root",
            request.compile_commands,
            selected_directory,
            symbol=request.symbol,
            source_line=request.source_line,
            command_index=request.command_index,
        )

    def _blocked_root(
        self,
        request: ExecutableSearchRequest,
        family: str,
        source_region: str | None,
        language: str,
        blockers: tuple[str, ...],
        *,
        blocked_authority: str = "incomplete",
        contract_override: Mapping[str, Any] | None = None,
    ) -> CapturedRoot:
        graph = _generic_graph(request.function or request.identifier, language, source_region or "")
        contract = dict(contract_override if contract_override is not None else request.contract or {})
        return CapturedRoot(
            request,
            family,
            "unbound",
            graph,
            contract,
            canonical_hash({"graph": graph, "contract": contract}),
            source_region,
            None,
            {},
            blockers,
            (),
            "no executable recognizer closure",
            blocked_authority,
        )

    def search(
        self,
        request: ExecutableSearchRequest,
        *,
        policy: ExpansionPolicy | None = None,
        frontier_policy=None,
        shadow_exhaustive: bool = True,
        ephemeral_terminal_artifacts: bool = False,
    ) -> dict[str, Any]:
        root = self.capture(request)
        output = request.output_directory.resolve()
        output.mkdir(parents=True, exist_ok=True)
        if root.unresolved_contracts:
            result = self._blocked_result(root)
            result["request_fingerprint"] = _request_fingerprint(request)
            if result.get("trace") is not None:
                _write_json(output / "executable-search-trace.json", result["trace"])
            _write_json(output / "executable-closure.json", result["closure"])
            _write_json(output / "executable-search.json", result)
            return result

        grammar = self._lazy_grammar(root)
        owned_frontier_oracle: JsonLineFrontierPolicy | None = None
        search_mode = (
            request.search_mode
            if request.search_mode != "legacy"
            else "shadow_exhaustive" if shadow_exhaustive else "live"
        )
        if search_mode not in {
            "shadow_exhaustive", "live", "legacy_path_debug", "fast", "guided", "exhaustive",
            "exhaustive_canonical", "exhaustive_reduced", "guided_reduced",
        }:
            raise ValueError(f"unsupported source-search mode: {search_mode}")
        if policy is None and search_mode == "live" and request.oracle_command:
            raise ValueError(
                "learned deletion oracle is retired; configure frontier_oracle and use fast, guided, or exhaustive"
            )
        if frontier_policy is None and request.frontier_oracle_command:
            owned_frontier_oracle = JsonLineFrontierPolicy(
                request.frontier_oracle_command,
                timeout_seconds=request.frontier_oracle_timeout_seconds,
            )
            frontier_policy = owned_frontier_oracle
        root_context = {
            "semantic_hash": root.semantic_hash,
            "semantic_graph": root.graph,
            "contract": root.contract,
            "grammar_version": root.grammar_version,
            "workload": dict(request.workload or {}),
            "hardware": dict(request.hardware or {}),
            "search_cost": dict((request.workload or {}).get("search_cost", {})),
        }
        canonical_result = None
        production_result = None
        try:
            if search_mode in {
                "fast", "guided", "exhaustive", "exhaustive_canonical",
                "exhaustive_reduced", "guided_reduced",
            }:
                production_result = self.production.run(
                    grammar,
                    root_context,
                    frontier_policy=frontier_policy,
                    config=ProductionSearchConfig(
                        mode=search_mode,
                        node_budget=request.node_budget,
                        work_budget=(
                            int(request.search_work_budget)
                            if request.search_work_budget is not None else None
                        ),
                        time_budget_seconds=request.search_time_budget_seconds,
                        memory_ceiling_bytes=request.search_memory_ceiling_bytes,
                        por_policy=request.por_policy,
                        checkpoint_path=request.search_checkpoint,
                        resume_path=request.search_resume,
                    ),
                )
                canonical_result = production_result.canonical_result
                lazy_result = canonical_result_to_lazy(canonical_result)
            else:
                legacy_mode = "shadow_exhaustive" if search_mode == "legacy_path_debug" else search_mode
                lazy_result = self.lazy.run(
                    grammar,
                    root_context,
                    policy=policy,
                    frontier_policy=frontier_policy,
                    mode=legacy_mode,
                    node_budget=request.node_budget,
                    work_budget=request.search_work_budget,
                    time_budget_seconds=request.search_time_budget_seconds,
                )
        finally:
            if owned_frontier_oracle is not None:
                owned_frontier_oracle.close()
        terminal_results = self._evaluate_terminals(
            root,
            lazy_result,
            output,
            ephemeral_artifacts=ephemeral_terminal_artifacts,
        )
        if canonical_result is not None and production_result is not None:
            terminal_by_digest = {
                str(item.get("state_id")): item for item in terminal_results
            }
            for record in canonical_result.states:
                terminal_row = terminal_by_digest.get(record.envelope.digest)
                if terminal_row is None:
                    continue
                record.proof_status = str(terminal_row.get("proof_status", "not_evaluated"))
                record.compiler_status = str(terminal_row.get("compile_status", "not_evaluated"))
                record.terminal_status = str(terminal_row.get("physical_outcome", "terminal"))
            proof_calls = sum(int(item.get("search_cost", {}).get("proof_calls") or 0) for item in terminal_results)
            compiler_calls = sum(
                int(item.get("search_cost", {}).get("compiler_invocation_count") or 0)
                for item in terminal_results
            )
            benchmark_calls = sum(
                int(item.get("search_cost", {}).get("benchmark_invocation_count") or 0)
                for item in terminal_results
            )
            evaluation_wall_ms = sum(
                float(item.get("search_cost", {}).get("evaluation_wall_ms") or 0.0)
                for item in terminal_results
            )
            canonical_result = replace(canonical_result, metrics=replace(
                canonical_result.metrics,
                proof_calls=proof_calls,
                compiler_calls=compiler_calls,
                benchmark_calls=benchmark_calls,
                terminal_evaluation_wall_ms=evaluation_wall_ms,
            ))
            self.production.cost_model.update_from_result(canonical_result)
            production_result = replace(
                production_result,
                canonical_result=canonical_result,
                cost_model=self.production.cost_model.to_dict(),
            )
        trace = self._build_trace(root, lazy_result, terminal_results)
        composition_trace = build_composition_trace(
            root={
                "root_id": canonical_hash({"project": request.project_id, "semantic": root.semantic_hash}),
                "canonical_root_hash": root.semantic_hash,
                "semantic_graph": root.graph,
                "contracts": root.contract,
                "cross_tu_scope": {
                    "seeds": list(request.cross_tu_seeds),
                    "maximum_upstream": request.max_upstream,
                    "maximum_downstream": request.max_downstream,
                },
            },
            project_id=request.project_id,
            source_frontend=request.language or _language_from_source(request.source),
            compiler_target=_compiler_identity(request.language or _language_from_source(request.source)),
            hardware_context=dict(request.hardware or {"architecture": "local", "cpu": cpu_model()}),
            lazy_result=lazy_result,
            terminal_results=terminal_results,
        )
        closure = self._closure(root, lazy_result, terminal_results)
        executable_terminals = tuple(
            item for item in terminal_results
            if item.get("realization") != "blocked-missing-contract"
        )
        result = {
            "schema_version": "vladder-executable-search-result-v1",
            # Trace-only search changes do not invalidate proven source/assembly terminals.
            "search_version": EXECUTABLE_SEARCH_VERSION,
            "request_fingerprint": _request_fingerprint(request),
            # Workflow completion and promotion evidence are deliberately
            # separate.  A solver-unsupported LLVM construct is a completed,
            # uncertain terminal rather than a failed search run.
            "status": "pass" if lazy_result.complete else "incomplete",
            "evidence_status": (
                "resolved" if all(item["resolved"] for item in executable_terminals)
                else "unresolved_terminals"
            ),
            "family_evidence": _family_evidence_summary(root, terminal_results),
            "root": {
                "identifier": request.identifier,
                "family": root.family,
                "grammar_version": root.grammar_version,
                "semantic_hash": root.semantic_hash,
                "contract": root.contract,
                "recognition": root.recognition,
            },
            "closure": closure.to_dict(),
            "lazy_search": lazy_result.to_dict(),
            "canonical_state_dag": canonical_result.to_dict() if canonical_result is not None else None,
            "production_canonical_search": production_result.to_dict() if production_result is not None else None,
            "composition_native_trace": composition_trace,
            "terminals": terminal_results,
            "trace": trace,
            "claim_boundary": "bounded grammar exhaustive only when closure.exhaustive_within_domain is true",
        }
        _write_json(output / "executable-search-trace.json", trace)
        if canonical_result is not None:
            _write_json(output / "canonical-state-dag.json", canonical_result.to_dict())
        if production_result is not None:
            _write_json(output / "production-canonical-search.json", production_result.to_dict())
        _write_json(output / "composition-native-search-trace.json", composition_trace)
        _write_json(output / "executable-closure.json", closure.to_dict())
        _write_json(output / "executable-search.json", result)
        return result

    def search_many(
        self,
        requests: Iterable[ExecutableSearchRequest],
        *,
        workers: int = 1,
        shadow_exhaustive: bool = True,
        training_output_directory: Path | None = None,
        artifact_retention: str = "full",
        full_artifact_identifiers: Iterable[str] = (),
    ) -> dict[str, Any]:
        ordered = sorted(tuple(requests), key=lambda item: item.identifier)
        training_records: dict[str, dict[str, Any]] = {}
        if artifact_retention not in {"full", "decisive"}:
            raise ValueError("artifact_retention must be 'full' or 'decisive'")
        retained_identifiers = frozenset(str(value) for value in full_artifact_identifiers)
        if training_output_directory is not None:
            progress_path = training_output_directory / "training-v3-progress.json"
            if progress_path.is_file():
                try:
                    previous_progress = json.loads(progress_path.read_text())
                except (OSError, json.JSONDecodeError):
                    previous_progress = {}
                if not isinstance(previous_progress, dict):
                    previous_progress = {}
                request_by_identifier = {item.identifier: item for item in ordered}
                for record in previous_progress.get("records", ()):
                    if not isinstance(record, dict):
                        continue
                    identifier = str(record.get("identifier", ""))
                    request = request_by_identifier.get(identifier)
                    if (
                        request is not None
                        and record.get("status") == "pass"
                        and record.get("request_fingerprint") == _request_fingerprint(request)
                    ):
                        training_records[identifier] = dict(record)

        def record_training(request: ExecutableSearchRequest, result: Mapping[str, Any]) -> None:
            record: dict[str, Any] | None = None
            if training_output_directory is not None:
                record = _emit_training_v3_record(
                    result,
                    request,
                    training_output_directory,
                    training_output_directory / "producer-identity.json",
                )
                record["request_fingerprint"] = _request_fingerprint(request)
                training_records[request.identifier] = record
            if (
                artifact_retention == "decisive"
                and request.identifier not in retained_identifiers
                and result.get("status") == "pass"
            ):
                compaction = _compact_decisive_root_artifacts(request.output_directory, result)
                if record is not None:
                    record["artifact_compaction"] = compaction
            if training_output_directory is not None:
                _write_json(
                    training_output_directory / "training-v3-progress.json",
                    _training_v3_summary(
                        training_records.values(), training_output_directory,
                        expected_record_count=len(ordered),
                    ),
                )

        if workers <= 1:
            rows = []
            for item in ordered:
                artifact = item.output_directory.resolve() / "executable-search.json"
                result = _load_completed_search(artifact, item)
                if result is None:
                    result = self.search(
                        item,
                        shadow_exhaustive=shadow_exhaustive,
                        ephemeral_terminal_artifacts=(
                            artifact_retention == "decisive"
                            and item.identifier not in retained_identifiers
                        ),
                    )
                record_training(item, result)
                rows.append(_campaign_result_summary(result, item))
        else:
            by_id: dict[str, dict[str, Any]] = {}
            request_by_id = {item.identifier: item for item in ordered}
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        _search_request_process,
                        self.cache.root,
                        item,
                        shadow_exhaustive,
                        (
                            training_output_directory is None
                            and artifact_retention == "decisive"
                            and item.identifier not in retained_identifiers
                        ),
                    ): item.identifier
                    for item in ordered
                }
                for future in as_completed(futures):
                    identifier = futures[future]
                    reference = future.result()
                    if training_output_directory is None:
                        by_id[identifier] = dict(reference["summary"])
                        continue
                    artifact = Path(str(reference["artifact"]))
                    result = _load_completed_search(artifact, request_by_id[identifier])
                    if result is None:
                        raise RuntimeError(
                            f"worker returned an invalid executable-search artifact: {artifact}"
                        )
                    record_training(request_by_id[identifier], result)
                    by_id[identifier] = _campaign_result_summary(
                        result, request_by_id[identifier],
                    )
            rows = [by_id[item.identifier] for item in ordered]
        closures = [_closure_from_dict(item["closure"]) for item in rows]
        coverage = closure_coverage(closures)
        coverage["terminal_count"] = sum(int(item.get("terminal_count", 0)) for item in rows)
        coverage["terminal_replacement_ready_count"] = sum(
            int(item.get("terminal_replacement_ready_count", 0)) for item in rows
        )
        report = {
            "schema_version": "vladder-executable-search-campaign-v1",
            "search_version": EXECUTABLE_SEARCH_VERSION,
            "root_count": len(rows),
            "complete_count": sum(item["status"] == "pass" for item in rows),
            "artifact_retention": artifact_retention,
            "full_artifact_identifiers": sorted(retained_identifiers),
            "closure_coverage": coverage,
            "roots": [
                {
                    "identifier": item["root"]["identifier"],
                    "status": item["status"],
                    "artifact": str(_retained_root_artifact(
                        Path(str(item["output_directory"])),
                    )),
                }
                for item in rows
            ],
        }
        if training_output_directory is not None:
            report["training_v3"] = _training_v3_summary(
                training_records.values(), training_output_directory,
                expected_record_count=len(ordered),
            )
        return report

    def _lazy_grammar(self, root: CapturedRoot) -> LazyGrammar:
        if root.family == "source-family-dispatch":
            return SourceFamilyDispatchGrammar(self, root.family_alternatives)
        if root.family == "deep-information-realization":
            return DeepLazyGrammar(load_deep_grammar(), root.source_realization or "scalar")
        if root.family == "canonical-bounded-region":
            return CanonicalRegionLazyGrammar(
                str(root.contract["canonical_region"]["family"]), root.graph,
            )
        if root.family == "ordered-prefix-suffix":
            return FiniteParameterGrammar(root.family, root.parameter_domains)
        if root.family == "bit-popcount-reduction":
            return FiniteParameterGrammar(root.family, root.parameter_domains)
        if root.family == "predicate-reduction":
            return FiniteParameterGrammar(root.family, root.parameter_domains)
        if root.family == "bounded-variable-output-dataflow":
            contract = BoundedDataflowContract.from_dict(dict(root.contract["bounded_dataflow"]))
            return BoundedDataflowLazyGrammar(contract, load_bounded_dataflow_grammar())
        if root.family == "lifetime-realization":
            return LifetimeLazyGrammar(
                Path(str(root.contract["manifest"])),
                Path(str(root.contract["trace"])),
            )
        if root.family == "cross-tu-composition":
            report = json.loads(Path(str(root.contract["report"])).read_text())
            return CrossTULazyGrammar(report)
        if root.family == "bounded-protocol":
            return ProtocolLazyGrammar(tuple(str(item) for item in root.parameter_domains["projection"]))
        if root.family == "selected-build-cpp":
            return SelectedBuildCppGrammar(
                json.loads(Path(str(root.contract["report"])).read_text()),
                tuple(str(item) for item in root.contract.get("selected_regions", ())) or None,
            )
        if root.family == "llvm-function-pipeline":
            return FiniteParameterGrammar(root.family, root.parameter_domains)
        raise ValueError(f"no executable lazy grammar for {root.family}")

    def _evaluate_terminals(
        self,
        root: CapturedRoot,
        lazy_result: LazySearchResult,
        output: Path,
        *,
        ephemeral_artifacts: bool = False,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        identity_owner: dict[str, str] = {}
        baseline_identity: str | None = (
            str(root.contract.get("source_assembly_identity"))
            if root.contract.get("source_assembly_identity") else None
        )
        states = sorted(lazy_result.terminals, key=lambda item: item.identity)

        selected_root = next(
            (
                _terminal_root(root, state)
                for state in states
                if _terminal_root(root, state).family == "selected-build-cpp"
                and _terminal_root(root, state).contract.get("report")
            ),
            None,
        )
        if selected_root is not None and request_workers(root.request) > 1:
            prewarm = prepare_selected_build_candidates(
                json.loads(Path(str(selected_root.contract["report"])).read_text()),
                output / "terminals",
                tuple(str(item) for item in selected_root.contract.get("selected_regions", ())) or None,
            )
            _write_json(output / "selected-build-prewarm.json", prewarm)

        workers = request_workers(root.request)
        if workers > 1 and len(states) > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                rows = list(pool.map(
                    _evaluate_terminal_process,
                    (self.cache.root for _ in states),
                    (root for _ in states),
                    states,
                    (output for _ in states),
                    (ephemeral_artifacts for _ in states),
                ))
        else:
            rows = [
                self._realize_terminal(
                    root,
                    state,
                    output,
                    ephemeral_artifacts=ephemeral_artifacts,
                )
                for state in states
            ]

        for row in rows:
            identity = row.get("assembly_identity")
            source_realization = row.pop("_source_realization", None)
            terminal_family = row.pop("_terminal_family", None)
            is_baseline = (
                source_realization is not None
                and row.get("realization") == source_realization
            ) or (
                terminal_family == "ordered-prefix-suffix"
                and row.get("parameters", {}).get("factor") == 1
            )
            if is_baseline and identity:
                baseline_identity = identity
            row["baseline_realization"] = is_baseline
            if identity and identity in identity_owner:
                row["identity_disposition"] = "duplicate"
                row["duplicate_of"] = identity_owner[identity]
            elif identity:
                identity_owner[identity] = str(row.get("candidate_id"))
                row["identity_disposition"] = "resolved"
            else:
                row["identity_disposition"] = "unresolved"
        for row in rows:
            identity = row.get("assembly_identity")
            if row.get("compile_status") == "FAIL":
                row["physical_outcome"] = "illegal"
            elif row["baseline_realization"] or (
                identity
                and identity == (row.get("source_baseline_identity") or baseline_identity)
            ):
                row["physical_outcome"] = "compiler_identical"
            elif row["identity_disposition"] == "duplicate":
                row["physical_outcome"] = "duplicate"
            elif identity:
                row["physical_outcome"] = "distinct_realization"
            else:
                row["physical_outcome"] = "proof_unknown"
            row["resolved"] = (
                row.get("compile_status") in {"PASS", "FAIL"}
                and row.get("proof_status") in {"PASS", "FAIL"}
                and row["physical_outcome"] != "proof_unknown"
            )
            if row.get("evaluation_resolved") is not None:
                row["resolved"] = bool(row["evaluation_resolved"])
        return rows

    def _realize_terminal(
        self,
        root: CapturedRoot,
        state: LazyState,
        output: Path,
        *,
        ephemeral_artifacts: bool = False,
    ) -> dict[str, Any]:
        terminal_root = _terminal_root(root, state)
        key_payload = {
            "search_version": TERMINAL_EVALUATION_CACHE_VERSION,
            "semantic_hash": terminal_root.semantic_hash,
            "grammar_version": terminal_root.grammar_version,
            "state": state.identity,
            "compiler": _compiler_identity(
                terminal_root.request.language or _language_from_source(terminal_root.request.source)
            ),
            "hardware": dict(root.request.hardware or {"cpu": cpu_model()}),
            "proof_policy": "exact-bounded-v1",
        }
        cache_key = self.cache.key(key_payload)
        evaluation_started = time.perf_counter()
        cached = self.cache.load(cache_key)
        if cached is not None and cached.get("compile_status") != "FAIL":
            row = {**cached, "cache": {"hit": True, "key": cache_key}}
        else:
            row = self._evaluate_terminal(
                terminal_root, state, output / "terminals" / state.identity[:16],
            )
            row = {**row, "cache": {"hit": False, "key": cache_key}}
        evaluation_wall_ms = (time.perf_counter() - evaluation_started) * 1000.0
        cache_hit = bool(row.get("cache", {}).get("hit"))
        cached_cost = row.get("search_cost") if isinstance(row.get("search_cost"), Mapping) else None
        if cache_hit and cached_cost:
            row["search_cost"] = {
                **dict(cached_cost),
                "cache_hit": True,
                "cache_read_wall_ms": evaluation_wall_ms,
            }
        else:
            proof_calls = int(row.get("proof_calls", row.get("proof_status") not in {None, "NOT_RUN", "UNAVAILABLE"}))
            compiler_calls = int(row.get("compiler_invocation_count", row.get("compile_status") not in {None, "NOT_RUN"}))
            benchmark_calls = int(row.get("benchmark_invocation_count", row.get("benchmark_status") not in {None, "not_run", "NOT_RUN"}))
            row["search_cost"] = {
                "candidate_construction_wall_ms": row.get("candidate_construction_wall_ms"),
                "proof_calls": proof_calls,
                "proof_wall_ms": row.get("proof_wall_ms"),
                "compiler_invocation_count": compiler_calls,
                "compiler_wall_ms": row.get("compiler_wall_ms"),
                "benchmark_invocation_count": benchmark_calls,
                "benchmark_wall_ms": row.get("benchmark_wall_ms"),
                "evaluation_wall_ms": evaluation_wall_ms,
                "cache_hit": False,
            }
        row["dispatch_family"] = str(
            state.semantic_state.get("dispatch_family") or terminal_root.family
        )
        row["source_baseline_identity"] = terminal_root.contract.get("source_assembly_identity")
        row["_source_realization"] = terminal_root.source_realization
        row["_terminal_family"] = terminal_root.family
        if not cache_hit and row.get("compile_status") not in {"FAIL", "NOT_RUN"}:
            self.cache.store(cache_key, {key: value for key, value in row.items() if key != "cache"})
        if ephemeral_artifacts:
            terminal_directory = output / "terminals" / state.identity[:16]
            if terminal_directory.is_dir():
                shutil.rmtree(terminal_directory)
        return row

    def _evaluate_terminal(self, root: CapturedRoot, state: LazyState, directory: Path) -> dict[str, Any]:
        directory.mkdir(parents=True, exist_ok=True)
        if state.semantic_state.get("blocked_missing_contract"):
            return {
                "candidate_id": canonical_hash({"state": state.identity, "blocked": True}),
                "state_id": state.identity,
                "realization": "blocked-missing-contract",
                "parameters": {},
                "proof_status": "UNAVAILABLE",
                "proof_class": "none",
                "compile_status": "NOT_RUN",
                "assembly_identity": None,
                "evaluation_resolved": False,
                "reason": "; ".join(str(item) for item in state.semantic_state.get("unresolved_contracts", ())),
            }
        if root.family == "deep-information-realization":
            contract = DeepKernelContract(**_tuple_contract(root.contract, "target_isa"))
            target = str(state.semantic_state["realization"])
            grammar = load_deep_grammar()
            search = search_deep_grammar(contract, grammar, source=root.source_realization or "scalar", targets=(target,))
            derivation = _matching_deep_derivation(search.derivations, tuple(state.semantic_state.get("rule_path", ())))
            if derivation is None:
                return _failed_terminal(state, target, "derivation missing")
            language = root.request.language or _language_from_source(root.request.source)
            candidate = emit_deep_candidate(contract, derivation, language, "deep_candidate", grammar)
            proof = prove_deep_candidate(contract, derivation, candidate, directory / "proof")
            build = compile_deep_harness(contract, candidate, directory / "build") if proof.get("status") == "PASS" else {"status": "NOT_RUN"}
            identity = (build.get("hot_assembly_identity") or {}).get("normalized_sha256")
            return {
                "candidate_id": candidate.id,
                "state_id": state.identity,
                "realization": target,
                "parameters": {},
                "source_sha256": candidate.source_sha256,
                "proof_status": proof.get("status"),
                "proof_class": proof.get("proof_classification", "deep-v2"),
                "compile_status": "PASS" if build.get("status") == "pass" else "FAIL",
                "assembly_identity": identity,
                "artifacts": {"proof": str(directory / "proof"), "build": str(directory / "build")},
            }
        if root.family == "canonical-bounded-region":
            from .canonical_executable import canonical_region_from_dict

            region = canonical_region_from_dict(dict(root.contract["canonical_region"]))
            grammar = CanonicalExecutableGrammar.load(region.family)
            path = tuple(str(item) for item in state.semantic_state.get("rule_path", ()))
            derivation = next(
                (
                    item for item in grammar.derivations()
                    if item.realization == str(state.semantic_state["realization"])
                    and tuple(rule.id for rule in item.rules) == path
                ),
                None,
            )
            if derivation is None:
                return _failed_terminal(state, str(state.semantic_state.get("realization")), "canonical derivation missing")
            language = root.request.language or _language_from_source(root.request.source)
            candidate = emit_canonical_candidate(region, derivation, language)
            proof = prove_canonical_candidate(region, derivation, candidate, directory / "proof")
            compiled = _compile_assembly(
                candidate.source,
                candidate.language,
                candidate.function,
                directory / "build",
                julia_signature="(Vector{Float32}, Vector{Float32})",
            )
            return {
                "candidate_id": candidate.id,
                "state_id": state.identity,
                "realization": candidate.realization,
                "parameters": {"rule_path": list(path)},
                "source_sha256": candidate.source_sha256,
                "proof_status": proof.get("status"),
                "proof_class": proof.get("proof_classification"),
                "compile_status": compiled.get("status"),
                "assembly_identity": compiled.get("assembly_identity"),
                "artifacts": {
                    "proof": str(directory / "proof/proof.json"),
                    "assembly": compiled.get("assembly"),
                },
                "compile": compiled,
            }
        if root.family == "predicate-reduction":
            contract = PredicateReductionContract(**root.contract)
            parameters = dict(state.semantic_state["parameters"])
            style = str(parameters["style"])
            unroll = int(parameters["unroll"])
            language = root.request.language or _language_from_source(root.request.source)
            candidate = next(
                item for item in enumerate_predicate_reduction_candidates(
                    contract, language=language,
                )
                if item.style == style and item.unroll == unroll
            )
            proof = prove_predicate_reduction_candidate(candidate, directory / "proof")
            julia_type = {
                "bool": "Bool", "u8": "UInt8", "u16": "UInt16", "u32": "UInt32",
                "u64": "UInt64", "i8": "Int8", "i16": "Int16", "i32": "Int32", "i64": "Int64",
            }[contract.element_type]
            compiled = _compile_assembly(
                candidate.source,
                candidate.language,
                candidate.function,
                directory / "build",
                julia_signature=f"(Vector{{{julia_type}}}, {julia_type})",
            )
            return {
                "candidate_id": candidate.id,
                "state_id": state.identity,
                "realization": candidate.realization,
                "parameters": {"style": style, "unroll": unroll},
                "source_sha256": candidate.source_sha256,
                "proof_status": proof.get("status"),
                "proof_class": proof.get("proof_class"),
                "compile_status": compiled.get("status"),
                "assembly_identity": compiled.get("assembly_identity"),
                "artifacts": {"proof": proof.get("artifact"), "assembly": compiled.get("assembly")},
                "compile": compiled,
            }
        if root.family == "ordered-prefix-suffix":
            contract = OrderedReductionContract(**root.contract)
            factor = int(state.semantic_state["parameters"]["factor"])
            language = root.request.language or _language_from_source(root.request.source)
            candidate = next(
                item for item in enumerate_ordered_candidates(contract, language=language)
                if item.factor == factor
            )
            proof = prove_ordered_candidate(candidate, directory / "proof")
            julia_element = {8: "UInt8", 16: "UInt16", 32: "UInt32", 64: "UInt64"}[contract.element_bits]
            julia_signature = (
                f"(Vector{{{julia_element}}}, Vector{{{julia_element}}})"
                if contract.operand_mode == "pair" else
                f"(Vector{{{julia_element}}}, {julia_element})"
            )
            compiled = _compile_assembly(
                candidate.source,
                candidate.language,
                candidate.function,
                directory / "build",
                julia_signature=julia_signature,
            )
            return {
                "candidate_id": candidate.id,
                "state_id": state.identity,
                "realization": f"factor-{factor}",
                "parameters": {"factor": factor},
                "source_sha256": candidate.source_sha256,
                "proof_status": proof.get("status"),
                "proof_class": proof.get("proof_class"),
                "compile_status": compiled["status"],
                "assembly_identity": compiled.get("assembly_identity"),
                "artifacts": {"proof": proof.get("artifact"), "assembly": compiled.get("assembly")},
                "compile": compiled,
            }
        if root.family == "bit-popcount-reduction":
            contract = BitReductionContract(**root.contract)
            realization = str(state.semantic_state["parameters"]["realization"])
            language = root.request.language or _language_from_source(root.request.source)
            candidate = next(
                item for item in enumerate_bit_reduction_candidates(contract, language=language)
                if item.realization == realization
            )
            proof = prove_bit_reduction_candidate(candidate, directory / "proof")
            compiled = _compile_assembly(
                candidate.source,
                candidate.language,
                candidate.function,
                directory / "build",
                julia_signature=f"(Vector{{UInt{contract.element_bits}}},)",
            )
            return {
                "candidate_id": candidate.id,
                "state_id": state.identity,
                "realization": realization,
                "parameters": {"realization": realization},
                "source_sha256": candidate.source_sha256,
                "proof_status": proof.get("status"),
                "proof_class": proof.get("proof_class"),
                "compile_status": compiled["status"],
                "assembly_identity": compiled.get("assembly_identity"),
                "artifacts": {"proof": proof.get("artifact"), "assembly": compiled.get("assembly")},
                "compile": compiled,
            }
        if root.family == "bounded-variable-output-dataflow":
            contract = BoundedDataflowContract.from_dict(dict(root.contract["bounded_dataflow"]))
            realization = str(state.semantic_state["parameters"]["realization"])
            grammar = load_bounded_dataflow_grammar()
            derivation = grammar.derive(contract, realization)
            language = root.request.language or _language_from_source(root.request.source)
            candidate = emit_dataflow_native(
                contract, derivation, language, grammar=grammar,
            )
            proof = prove_dataflow_candidate(contract, derivation, candidate, directory / "proof")
            compiled = _compile_assembly(
                candidate.source, candidate.language, candidate.function, directory / "build",
                dataflow_family=contract.family,
            )
            reconstruction = None
            reconstruction_contract = root.contract.get("cpp_reconstruction")
            if (
                candidate.language == "cpp"
                and isinstance(reconstruction_contract, Mapping)
                and reconstruction_contract.get("applicable")
            ):
                report = json.loads(Path(str(reconstruction_contract["report"])).read_text())
                reconstruction = reconstruct_exact_dataflow_translation_unit(
                    candidate,
                    contract,
                    report,
                    directory / "source-reconstruction",
                )
                if reconstruction.get("status") == "PASS":
                    compiled = reconstruction["compile"]
            return {
                "candidate_id": candidate.id,
                "state_id": state.identity,
                "realization": realization,
                "parameters": {"realization": realization},
                "source_sha256": candidate.source_sha256,
                "proof_status": proof.get("status"),
                "proof_class": proof.get("proof_classification"),
                "compile_status": compiled["status"],
                "assembly_identity": compiled.get("assembly_identity"),
                "artifacts": {
                    "proof": str(directory / "proof"),
                    "assembly": compiled.get("assembly"),
                    **({"source_reconstruction": reconstruction.get("source")} if reconstruction else {}),
                },
                "compile": compiled,
                "replacement_ready": bool(reconstruction and reconstruction.get("replacement_ready")),
                "source_reconstruction": reconstruction,
            }
        if root.family == "selected-build-cpp":
            report = json.loads(Path(str(root.contract["report"])).read_text())
            try:
                evaluated = evaluate_selected_build_candidate(
                    report,
                    {str(key): value for key, value in state.semantic_state["selection"].items()},
                    directory,
                    tuple(str(item) for item in root.contract.get("selected_regions", ())) or None,
                )
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                return _failed_terminal(
                    state,
                    "selected-build-candidate-generation-failure",
                    str(error),
                )
            return {**evaluated, "state_id": state.identity}
        if root.family == "llvm-function-pipeline":
            capture = json.loads(Path(str(root.contract["capture"])).read_text())
            pipeline = str(state.semantic_state["parameters"]["pipeline"])
            try:
                evaluated = evaluate_llvm_function_pipeline(capture, pipeline, directory)
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                return _failed_terminal(state, "llvm-function-pipeline-failure", str(error))
            return {**evaluated, "state_id": state.identity}
        if root.family == "lifetime-realization":
            graph = load_lifetime_flow_graph(Path(str(root.contract["manifest"])))
            events = load_lifetime_trace(Path(str(root.contract["trace"])), graph)
            candidate = _lifetime_candidate_from_dict(dict(state.semantic_state["candidate"]))
            verification = verify_lifetime_candidate(graph, candidate, events, directory / "proof")
            write_verification_report(directory / "proof/verification.json", verification)
            realization = build_agent_realization_contract(graph, candidate, verification)
            contract_path, prompt_path = write_agent_realization_bundle(directory / "realization", realization)
            return {
                "candidate_id": candidate.candidate_id,
                "state_id": state.identity,
                "realization": candidate.family,
                "parameters": {
                    "mode": candidate.mode,
                    "scope": candidate.candidate_scope,
                    "placement": candidate.candidate_placement,
                },
                "source_sha256": None,
                "proof_status": verification.status,
                "proof_class": "bounded-lifetime-state-transition-v1",
                "compile_status": "NOT_APPLICABLE",
                "assembly_identity": None,
                "evaluation_resolved": verification.status in {"PASS", "FAIL"},
                "artifacts": {
                    "proof": str(directory / "proof/verification.json"),
                    "realization_contract": str(contract_path),
                    "agent_prompt": str(prompt_path),
                },
            }
        if root.family == "cross-tu-composition":
            report = json.loads(Path(str(root.contract["report"])).read_text())
            if "region_selection" in state.semantic_state:
                try:
                    evaluated = evaluate_cross_tu_selected_build_candidate(
                        report.get("selected_build", {}),
                        {
                            str(key): str(value)
                            for key, value in state.semantic_state["region_selection"].items()
                        },
                        directory,
                        selected_functions=tuple(
                            str(item) for item in state.semantic_state["selected_functions"]
                        ),
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    return _failed_terminal(
                        state,
                        "selected-build-candidate-generation-failure",
                        str(error),
                    )
                return {**evaluated, "state_id": state.identity}
            selected = tuple(str(item) for item in state.semantic_state["selected_functions"])
            proof_status = str(report.get("proof", {}).get("status", "UNKNOWN"))
            plan = {
                "schema_version": "vladder-cross-tu-composition-plan-v1",
                "candidate_id": canonical_hash({"selected": selected, "slice": report["slice"].get("slice_sha256")}),
                "selected_functions": list(selected),
                "residual_boundaries": report["slice"].get("boundaries", []),
                "ownership": report.get("ownership", {}),
                "proof": report.get("proof", {}),
                "claim_boundary": "call-preserving composition only; functional cross-call rewrites require helper contracts",
            }
            plan_path = directory / "composition-plan.json"
            _write_json(plan_path, plan)
            return {
                "candidate_id": plan["candidate_id"],
                "state_id": state.identity,
                "realization": "definition-visible-composition",
                "parameters": {"function_count": len(selected)},
                "source_sha256": None,
                "proof_status": proof_status,
                "proof_class": "cross-tu-summary-composition-v1",
                "compile_status": "NOT_APPLICABLE",
                "assembly_identity": None,
                "evaluation_resolved": proof_status in {"PASS", "FAIL"},
                "artifacts": {"composition_plan": str(plan_path), "proof": str(root.contract["report"])},
            }
        if root.family == "bounded-protocol":
            manifest = Path(str(root.contract["manifest"]))
            if root.contract["protocol_kind"] == "device":
                evidence = verify_device_protocol(manifest, directory / "proof").to_dict()
                proof_path = directory / "proof/device-protocol-proof.json"
            else:
                evidence = verify_state_protocol(manifest, directory / "proof")
                proof_path = directory / "proof/protocol-proof.json"
                if not proof_path.exists():
                    proof_path = directory / "proof/resource-protocol-proof.json"
            projection = str(state.semantic_state["projection"])
            return {
                "candidate_id": canonical_hash({"manifest": str(manifest), "projection": projection}),
                "state_id": state.identity,
                "realization": f"protocol-projection:{projection}",
                "parameters": {"projection": projection},
                "source_sha256": None,
                "proof_status": str(evidence.get("status", "UNKNOWN")),
                "proof_class": "bounded-protocol-projection-v1",
                "compile_status": "NOT_APPLICABLE",
                "assembly_identity": None,
                "evaluation_resolved": str(evidence.get("status")) in {"PASS", "FAIL"},
                "artifacts": {"proof": str(proof_path)},
            }
        return _failed_terminal(state, "unknown", "unsupported family")

    def _build_trace(
        self,
        root: CapturedRoot,
        lazy_result: LazySearchResult,
        terminal_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        prior_root = make_root(
            root.graph,
            root.contract,
            [{"source_language": root.request.language or _language_from_source(root.request.source), "family": root.family}],
            project_id=root.request.project_id,
        )
        hardware = dict(root.request.hardware or {"architecture": "local", "cpu": cpu_model()})
        workload = dict(root.request.workload or {"phase": "search-capture"})
        seed = canonical_hash({"root": prior_root["root_id"], "grammar": root.grammar_version, "hardware": hardware, "workload": workload})
        dispatch = root.family == "source-family-dispatch"
        opportunities = () if dispatch else _source_family_opportunities(root)
        dispatch_family_count = len(root.family_alternatives) if dispatch else 1 + len(opportunities)
        emitted_root_count = sum(item.parent_id is None for item in lazy_result.nodes)
        incomplete_reason = (
            "budget"
            if not lazy_result.complete and len(lazy_result.nodes) >= root.request.node_budget
            else "unknown"
        )
        utility_complete = lazy_result.complete and all(
            item.get("physical_outcome") != "proof_unknown"
            for item in terminal_results
            if item.get("realization") != "blocked-missing-contract"
        ) and not any(
            item.unresolved_contracts and item.blocked_authority != "sound_contract"
            for item in root.family_alternatives
        ) and not any(
            str(item.get("disposition")) != "inapplicable"
            for item in opportunities
        )
        baseline_action = {
            "family": "baseline",
            "family_version": "v1",
            "op": "existing_implementation",
        }
        baseline_context = build_decision_context(
            root.graph,
            semantic_state={"baseline": True},
            action=baseline_action,
            depth=0,
            stage="baseline",
            terminal=False,
            projection={"quality": "root_only", "graph": root.graph},
        )
        baseline = make_branch(
            seed,
            {"family": "baseline", "family_version": "v1", "primitives": ["existing_implementation"]},
            parent_branch_id=None,
            depth=0,
            stage="baseline",
            baseline=True,
            state="expanded",
            evidence_coverage="complete" if lazy_result.complete else "partial",
            coverage={
                "children_status": "exhaustive" if lazy_result.complete else "partially_enumerated",
                "emitted_child_count": emitted_root_count if dispatch else dispatch_family_count,
                "expected_child_count": dispatch_family_count if lazy_result.complete else None,
                "completeness_reason": "exhaustive_grammar" if lazy_result.complete else incomplete_reason,
            },
            decision_context=baseline_context,
            identity_material={"seed": seed, "baseline": True},
        )
        family_action = {
            "family": root.family,
            "family_version": root.grammar_version,
            "op": "family_opportunity",
        }
        family_branch = None if dispatch else make_branch(
            seed,
            {
                "family": root.family,
                "family_version": root.grammar_version,
                "primitives": ["family_opportunity"],
                "parameters": {"decision_surface": "synthetic_wrapper"},
            },
            parent_branch_id=baseline["branch_id"],
            depth=1,
            stage="grammar_family",
            state="expanded" if lazy_result.nodes else "terminal",
            evidence_coverage="complete" if lazy_result.complete else "partial",
            coverage={
                "children_status": "exhaustive" if lazy_result.complete else "partially_enumerated",
                "emitted_child_count": sum(item.parent_id is None for item in lazy_result.nodes),
                "expected_child_count": sum(item.parent_id is None for item in lazy_result.nodes) if lazy_result.complete else None,
                "completeness_reason": "exhaustive_grammar" if lazy_result.complete else incomplete_reason,
            },
            decision_context=build_decision_context(
                root.graph,
                semantic_state={"family": root.family},
                action=family_action,
                ancestor_actions=(baseline_action,),
                depth=1,
                stage="grammar_family",
                terminal=not bool(lazy_result.nodes),
                projection={"quality": "partial_state", "graph": root.graph},
            ),
            identity_material={"seed": seed, "family": root.family},
        )
        branches = [baseline] if family_branch is None else [baseline, family_branch]
        observations: list[dict[str, Any]] = []
        for opportunity in opportunities:
            disposition = str(opportunity["disposition"])
            soundly_closed = disposition == "inapplicable"
            branch = make_branch(
                seed,
                {
                    "family": str(opportunity["family"]),
                    "family_version": str(opportunity["grammar_version"]),
                    "primitives": ["family_opportunity"],
                    "parameters": {
                        "disposition": disposition,
                        "decision_surface": "synthetic_wrapper",
                    },
                },
                parent_branch_id=baseline["branch_id"],
                depth=1,
                stage="grammar_family",
                state="terminal" if soundly_closed else "blocked",
                evidence_coverage="complete" if soundly_closed else "partial",
                coverage={
                    "children_status": "not_applicable" if soundly_closed else "not_enumerated",
                    "emitted_child_count": 0,
                    "expected_child_count": 0 if soundly_closed else None,
                    "completeness_reason": "not_applicable" if soundly_closed else "missing_contract",
                    "soundness_proof_class": (
                        str(opportunity["authority"]) if soundly_closed else "none"
                    ),
                },
                decision_context=build_decision_context(
                    root.graph,
                    semantic_state={"family": str(opportunity["family"]), "disposition": disposition},
                    action={
                        "family": str(opportunity["family"]),
                        "family_version": str(opportunity["grammar_version"]),
                        "op": "family_opportunity",
                    },
                    ancestor_actions=(baseline_action,),
                    depth=1,
                    stage="grammar_family",
                    terminal=True,
                    projection={"quality": "partial_state", "graph": root.graph},
                ),
                identity_material={
                    "seed": seed,
                    "family_opportunity": opportunity,
                },
            )
            branches.append(branch)
            observations.append(make_branch_observation(
                branch["branch_id"],
                "grammar_disposition",
                "inapplicable" if soundly_closed else "missing_contract",
                quality_grade="A" if soundly_closed else "C",
                proof_class=str(opportunity["authority"]),
            ))
        lazy_to_branch: dict[str, str] = {}
        terminal_by_state = {str(item["state_id"]): item for item in terminal_results}
        for item in lazy_result.nodes:
            terminal_row = terminal_by_state.get(item.semantic_state_hash)
            parent = (
                baseline["branch_id"] if dispatch else family_branch["branch_id"]
            ) if item.parent_id is None else lazy_to_branch[item.parent_id]
            terminal = item.terminal or item.disposition in {"impossible", "dominated", "canonical_duplicate", "policy_pruned", "deferred"}
            missing_contract = item.action.get("op") == "blocked_missing_contract"
            complete_terminal = item.disposition in {"terminal", "impossible", "dominated", "canonical_duplicate"} and not missing_contract
            deterministic = item.disposition in {"impossible", "dominated"}
            canonicalized = item.disposition == "canonical_duplicate"
            action_parameters = {
                **_training_action_parameters(item.action),
                "decision_surface": (
                    "deterministic" if deterministic else
                    "canonicalized" if canonicalized else
                    "learned_eligible"
                ),
            }
            branch = make_branch(
                seed,
                {
                    "family": item.family,
                    "family_version": str(item.action.get("family_version") or root.grammar_version),
                    "primitives": [str(item.action.get("rule") or item.action.get("parameter") or item.action.get("op") or "expand")],
                    "parameters": action_parameters,
                },
                parent_branch_id=parent,
                depth=item.depth + (1 if dispatch else 2),
                stage=_training_stage(item.stage),
                state=("blocked" if deterministic else "terminal" if terminal else "expanded"),
                evidence_coverage="soundly_blocked" if deterministic else "complete" if complete_terminal else "partial",
                coverage={
                    "children_status": "soundly_closed" if deterministic else "not_enumerated" if missing_contract else "not_applicable" if terminal else "exhaustive" if lazy_result.complete else "partially_enumerated",
                    "emitted_child_count": item.child_count,
                    "expected_child_count": 0 if deterministic else None if missing_contract else item.child_count if lazy_result.complete or terminal else None,
                    "completeness_reason": "sound_dominance" if item.disposition == "dominated" else "sound_legality" if item.disposition == "impossible" else "missing_contract" if missing_contract else "terminal" if terminal else "exhaustive_grammar" if lazy_result.complete else incomplete_reason,
                    "soundness_proof_class": "deterministic-legality" if item.disposition in {"impossible", "dominated"} else "none",
                },
                search_cost={
                    "node_expansions": 1 if item.disposition == "expanded" else 0,
                    "proof_calls": int(terminal_row is not None and terminal_row.get("proof_status") != "NOT_APPLICABLE"),
                    "compiler_invocations": int(
                        terminal_row is not None and terminal_row.get("compile_status") != "NOT_APPLICABLE"
                    ),
                },
                decision_context={
                    **item.decision_context,
                    "context": {
                        **dict(item.decision_context.get("context", {})),
                        "canonical_state_hash": item.semantic_state_hash,
                    },
                },
                identity_material={"seed": seed, "lazy_node": item.node_id},
            )
            branches.append(branch)
            lazy_to_branch[item.node_id] = branch["branch_id"]
            if missing_contract:
                observations.append(make_branch_observation(
                    branch["branch_id"], "grammar_disposition", "missing_contract",
                    quality_grade="C", proof_class="none",
                ))
            elif item.disposition in {"impossible", "dominated"}:
                observations.append(make_branch_observation(branch["branch_id"], "grammar_disposition", "illegal", quality_grade="A", proof_class="deterministic-legality"))
            elif item.disposition == "canonical_duplicate":
                observations.append(make_branch_observation(branch["branch_id"], "assembly", "duplicate", quality_grade="A", proof_class="semantic-state-canonicalization"))
            elif item.disposition == "terminal":
                assert terminal_row is not None
                observations.append(make_branch_observation(
                    branch["branch_id"],
                    "proof",
                    "proof_passed" if terminal_row["proof_status"] == "PASS" else "proof_failed",
                    quality_grade="A" if terminal_row["proof_status"] == "PASS" else "B",
                    proof_class=str(terminal_row.get("proof_class") or "none"),
                ))
                observations.append(make_branch_observation(
                    branch["branch_id"],
                    "assembly",
                    str(terminal_row["physical_outcome"]),
                    quality_grade="A" if terminal_row["physical_outcome"] != "proof_unknown" else "D",
                    proof_class="normalized-hot-assembly-v1",
                ))
        registry_families = sorted(
            [(_dispatch_family_id(item), item.grammar_version) for item in root.family_alternatives]
            if dispatch else
            [(root.family, root.grammar_version)]
            + [(str(item["family"]), str(item["grammar_version"])) for item in opportunities]
        )
        registry_hash = canonical_hash({
            "registry": EXECUTABLE_GRAMMAR_REGISTRY_VERSION,
            "families": registry_families,
        })
        search = make_search(
            prior_root["root_id"],
            baseline["branch_id"],
            hardware,
            workload,
            grammar_version=EXECUTABLE_GRAMMAR_REGISTRY_VERSION,
            grammar_hash=registry_hash,
            selection_policy="bounded_exhaustive" if lazy_result.complete else "model_guided",
            coverage="complete" if utility_complete else "partial",
            stage_coverage={
                "grammar_family": "partial" if any(
                    item.unresolved_contracts and item.blocked_authority != "sound_contract"
                    for item in root.family_alternatives
                ) else "complete",
                "candidate_family": "complete" if lazy_result.complete else "partial",
                "composition": "complete" if any(item.stage == "composition" for item in lazy_result.nodes) else "not_attempted",
                "cross_tu": "complete" if root.family == "cross-tu-composition" and lazy_result.complete else "partial" if root.family == "cross-tu-composition" else "not_attempted",
            },
            exploration_reserve_fraction=0.0,
            identity_material={"seed": seed, "trace": [item.node_id for item in lazy_result.nodes]},
        )
        for branch in branches:
            branch["search_id"] = search["search_id"]
        return {
            "schema_version": "vladder-authoritative-search-trace-v1",
            "grammar_version": EXECUTABLE_GRAMMAR_REGISTRY_VERSION,
            "roots": [prior_root],
            "searches": [search],
            "branches": branches,
            "observations": observations,
            "frontier_decisions": [item.to_dict() for item in lazy_result.frontier_decisions],
            "transposition_evidence": {
                "canonical_state_hashes_available": True,
                "exact_states_collapsed": lazy_result.canonicalized,
                "learned_equivalence_proposals": lazy_result.equivalence_proposals,
                "formally_verified_equivalences": lazy_result.verified_equivalences,
                "claim_boundary": "only exact canonical identity or verifier-accepted equivalence collapses state",
            },
            "best_first_evidence": {
                "mode": lazy_result.mode,
                "complete": lazy_result.complete,
                "maximum_frontier_size": lazy_result.maximum_frontier_size,
                "learned_policy_pruned": lazy_result.policy_pruned,
                "authority": "priority-only in fast/guided/exhaustive modes",
            },
        }

    def _closure(
        self,
        root: CapturedRoot,
        lazy_result: LazySearchResult,
        terminals: list[dict[str, Any]],
    ) -> ExecutableFamilyClosure:
        executable_terminals = tuple(
            item for item in terminals if item.get("realization") != "blocked-missing-contract"
        )
        compile_resolved = bool(executable_terminals) and all(
            item.get("compile_status") in {"PASS", "FAIL"} for item in executable_terminals
        )
        compile_failures = sum(item.get("compile_status") == "FAIL" for item in executable_terminals)
        all_proof = bool(executable_terminals) and all(item.get("proof_status") in {"PASS", "FAIL"} for item in executable_terminals)
        all_identity = bool(executable_terminals) and all(item.get("physical_outcome") != "proof_unknown" for item in executable_terminals)
        if root.family == "source-family-dispatch":
            incomplete = tuple(
                item for item in root.family_alternatives
                if item.unresolved_contracts and item.blocked_authority != "sound_contract"
            )
            applicable = tuple(item for item in root.family_alternatives if not item.unresolved_contracts)
            stages = {
                "recognition": stage("complete", root.recognition, f"{len(root.family_alternatives)} family opportunities are explicit lazy branches"),
                "contract_inference": stage(
                    "partial" if incomplete else "complete",
                    "independent family contract inference",
                    f"{len(applicable)} applicable, {len(incomplete)} require additional contract facts",
                ),
                "applicability": stage("complete", "sound family recognizers", "inapplicable families are closed without learned authority"),
                "enumeration": stage("complete" if lazy_result.complete else "partial", "lazy family and candidate expansion", f"{len(lazy_result.nodes)} decisions reached; no Cartesian candidate list is prebuilt"),
                "emission": stage("complete" if executable_terminals else "not_attempted", "family native emitters", f"{len(executable_terminals)} executable terminals emitted"),
                "compilation": stage("complete" if compile_resolved else "not_attempted" if not executable_terminals else "blocked", "family compiler registry", f"{compile_failures} compile failures"),
                "proof": stage("complete" if all_proof else "not_attempted" if not executable_terminals else "blocked", "family proof registry", "all executable terminals resolved" if all_proof else "proof evidence remains unresolved"),
                "physical_identity": stage("complete" if all_identity else "not_attempted" if not executable_terminals else "blocked", "normalized assembly identity", "all executable terminals resolved" if all_identity else "identity evidence remains unresolved"),
                "source_reconstruction": stage(
                    "complete" if executable_terminals and all(
                        item.get("dispatch_family") == "selected-build-cpp"
                        for item in executable_terminals
                    ) else "partial" if executable_terminals else "not_attempted",
                    "family source emitters",
                    "complete translation-unit reconstruction exists only for selected-build terminals; bounded proof units retain an explicit owning boundary",
                ),
            }
            return ExecutableFamilyClosure(
                root.family,
                root.grammar_version,
                root.semantic_hash,
                stages,
                root.parameter_domains,
                tuple(obligation for item in incomplete for obligation in item.unresolved_contracts),
                root.external_boundaries,
                lazy_result.complete and not incomplete,
            )
        if root.family == "lifetime-realization":
            stages = {
                "recognition": stage("complete", root.recognition, "lifetime information identities are bound"),
                "contract_inference": stage("complete", "explicit lifetime manifest", "scopes, invalidators, consumers, ownership, and fallback are declared"),
                "applicability": stage("complete", "runtime attribution quality", "candidate rules are admitted only for sufficiently attributed information"),
                "enumeration": stage("complete" if lazy_result.complete else "partial", "lazy lifetime grammar", f"{len(lazy_result.terminals)} plans reached"),
                "emission": stage("complete" if terminals else "blocked", "agent realization contract", f"{len(terminals)} source realization plans emitted"),
                "compilation": stage("not_attempted", "none", "owning source has not been regenerated"),
                "proof": stage("complete" if all_proof else "blocked", "bounded lifetime verifier", "every emitted plan has a resolved transition proof" if all_proof else "one or more transition proofs are unresolved"),
                "physical_identity": stage("not_attempted", "none", "no compiled owning realization exists"),
                "source_reconstruction": stage("partial", "agent realization adapter", "ownership, lifecycle hooks, fallback, and debug-oracle requirements are emitted"),
            }
            return ExecutableFamilyClosure(
                root.family,
                root.grammar_version,
                root.semantic_hash,
                stages,
                root.parameter_domains,
                root.unresolved_contracts,
                root.external_boundaries,
                lazy_result.complete,
            )
        if root.family == "selected-build-cpp":
            stages = {
                "recognition": stage("complete", root.recognition, "selected build, symbol, and isolated loop regions are captured"),
                "contract_inference": stage("complete", "Clang AST plus production LLVM", "ABI, loop body, live-ins, live-outs, and schedule proof capsules are bound"),
                "applicability": stage("complete", "typed loop-region classifier", "only source-schedulable isolated regions enter the grammar"),
                "enumeration": stage("complete" if lazy_result.complete else "partial", "lazy regional composition", f"{len(lazy_result.nodes)} partial states and {len(terminals)} composed terminals"),
                "emission": stage("complete" if terminals else "blocked", "non-overlapping source edit composer", f"{len(terminals)} complete translation-unit candidates emitted"),
                "compilation": stage(
                    "complete" if compile_resolved else "blocked",
                    "production compile command",
                    f"all candidates reached a compile disposition; {compile_failures} were rejected by the selected build"
                    if compile_resolved else "one or more selected-build compile dispositions are unresolved",
                ),
                "proof": stage("complete" if all_proof else "blocked", "Z3 schedule partition plus canonical LLVM body identity", "all regional obligations compose" if all_proof else "one or more regional obligations failed"),
                "physical_identity": stage("complete" if all_identity else "blocked", "selected symbol assembly", "all composed candidates have normalized identities" if all_identity else "one or more selected symbols were unresolved"),
                "source_reconstruction": stage("complete" if terminals else "blocked", "full translation-unit source composer", "owning wrappers are preserved and only proved loop directives are inserted"),
            }
            return ExecutableFamilyClosure(
                root.family,
                root.grammar_version,
                root.semantic_hash,
                stages,
                root.parameter_domains,
                root.unresolved_contracts,
                root.external_boundaries,
                lazy_result.complete,
            )
        if root.family == "llvm-function-pipeline":
            stages = {
                "recognition": stage("complete", root.recognition, "selected symbol and complete LLVM module context are captured"),
                "contract_inference": stage("complete", "compiler ABI and LLVM semantics", "the selected same-signature function is the refinement boundary"),
                "applicability": stage("complete", "finite LLVM pipeline registry", "pipelines preserve the selected ABI and external declarations"),
                "enumeration": stage("complete" if lazy_result.complete else "partial", "lazy finite pass-pipeline expansion", f"{len(terminals)} terminal modules reached"),
                "emission": stage("complete" if terminals else "blocked", "LLVM opt pipeline", f"{len(terminals)} selected-function modules emitted"),
                "compilation": stage("complete" if compile_resolved else "blocked", "llc target lowering", f"all modules reached compile disposition; {compile_failures} failed" if compile_resolved else "one or more modules lack compile disposition"),
                "proof": stage("complete" if all_proof else "partial", "Alive2 two-module selected-function refinement", "all candidates resolved" if all_proof else "unsupported LLVM constructs remain explicit rather than being treated as negative"),
                "physical_identity": stage("complete" if all_identity else "partial", "selected-symbol normalized assembly", "all compiled candidates deduplicated" if all_identity else "one or more unproved candidates remain unresolved"),
                "source_reconstruction": stage("partial", "LLVM replacement artifact", "verified LLVM replacement is emitted; an owning source rewrite is not inferred from pass output"),
            }
            return ExecutableFamilyClosure(
                root.family,
                root.grammar_version,
                root.semantic_hash,
                stages,
                root.parameter_domains,
                root.unresolved_contracts,
                root.external_boundaries,
                lazy_result.complete,
            )
        if root.family == "cross-tu-composition":
            regional = any("selection" in item.get("parameters", {}) for item in terminals)
            stages = {
                "recognition": stage("complete", root.recognition, "selected-build functions and call edges are captured"),
                "contract_inference": stage("complete", "call-preserving function summaries", "effects, ownership, provenance, and external boundaries are explicit"),
                "applicability": stage("complete", "whole-build definition index", "only unique definition-visible edges are composed"),
                "enumeration": stage("complete" if lazy_result.complete else "partial", "lazy connected-subgraph and regional schedule expansion", f"{len(lazy_result.nodes)} partial states and {len(terminals)} terminal compositions"),
                "emission": stage("complete" if regional and terminals else "partial", "cross-TU non-overlapping source composer", f"{len(terminals)} bounded compositions reached; executable regional source is emitted where local closure exists"),
                "compilation": stage("complete" if regional and compile_resolved else "partial", "selected production compile commands", f"regional candidates reached compile dispositions; {compile_failures} failed" if regional else "no executable regional terminal was available"),
                "proof": stage("complete" if all_proof else "blocked", "summary composition plus local Z3/LLVM obligations", "definition, ownership, edge, and regional obligations are resolved" if all_proof else "one or more composition obligations are unresolved"),
                "physical_identity": stage("complete" if regional and all_identity else "partial", "selected symbol assembly", "regional translation-unit identities are resolved" if regional and all_identity else "call-preserving plans have no replacement assembly"),
                "source_reconstruction": stage("complete" if regional and terminals else "partial", "cross-TU regional source composer", "proved local schedule changes are regenerated in owning translation units; cross-call functional rewrites remain excluded"),
            }
            return ExecutableFamilyClosure(
                root.family,
                root.grammar_version,
                root.semantic_hash,
                stages,
                root.parameter_domains,
                root.unresolved_contracts,
                root.external_boundaries,
                lazy_result.complete,
            )
        if root.family == "bounded-protocol":
            stages = {
                "recognition": stage("complete", root.recognition, "bounded protocol and authority are explicit"),
                "contract_inference": stage("complete", "protocol manifest", "states, transitions, guards, and excluded authorities are declared"),
                "applicability": stage("complete", "protocol projection registry", "finite proof projections are enumerated"),
                "enumeration": stage("complete" if lazy_result.complete else "partial", "lazy protocol projections", f"{len(terminals)} proof projections reached"),
                "emission": stage("complete" if terminals else "blocked", "bounded protocol proof emitter", f"{len(terminals)} proof artifacts emitted"),
                "compilation": stage("not_attempted", "none", "protocol projection is not an owning source implementation"),
                "proof": stage("complete" if all_proof else "blocked", "bounded Z3 protocol verifier", "all declared projections resolved" if all_proof else "one or more protocol obligations remain unresolved"),
                "physical_identity": stage("not_attempted", "none", "physical runner is not bound"),
                "source_reconstruction": stage("partial", "protocol realization contract", "owning source and external authority adapters remain explicit"),
            }
            return ExecutableFamilyClosure(
                root.family,
                root.grammar_version,
                root.semantic_hash,
                stages,
                root.parameter_domains,
                root.unresolved_contracts,
                root.external_boundaries,
                lazy_result.complete,
            )
        stages = {
            "recognition": stage("complete", root.recognition, f"recognized {root.family}"),
            "contract_inference": stage("complete", "typed bounded contract", "all mandatory contract facts are bound"),
            "applicability": stage("complete", "registered family binding", "family applies to the captured root"),
            "enumeration": stage("complete" if lazy_result.complete else "partial", "lazy grammar trace", f"{len(lazy_result.terminals)} terminals reached"),
            "emission": stage("complete" if terminals else "blocked", "native emitter", f"{len(terminals)} source candidates emitted"),
            "compilation": stage(
                "complete" if compile_resolved else "blocked",
                "native compiler",
                f"all candidates reached a compile disposition; {compile_failures} were rejected"
                if compile_resolved else "one or more compile dispositions are unresolved",
            ),
            "proof": stage("complete" if all_proof else "blocked", "family proof registry", "every terminal has a resolved proof disposition" if all_proof else "proof evidence is unresolved"),
            "physical_identity": stage("complete" if all_identity else "blocked", "normalized hot assembly", "every terminal was deduplicated" if all_identity else "one or more identities are unresolved"),
            "source_reconstruction": stage(
                "complete" if terminals and all(item.get("replacement_ready") for item in terminals) else "partial",
                "bounded C++ source composer" if terminals and all(item.get("replacement_ready") for item in terminals) else "bounded kernel emitter",
                "every terminal reconstructs the complete compiler-selected definition"
                if terminals and all(item.get("replacement_ready") for item in terminals)
                else "generated bounded kernels are available; owning wrapper replacement remains separate",
            ),
        }
        return ExecutableFamilyClosure(
            root.family,
            root.grammar_version,
            root.semantic_hash,
            stages,
            root.parameter_domains,
            root.unresolved_contracts,
            root.external_boundaries,
            lazy_result.complete,
        )

    def _blocked_result(self, root: CapturedRoot) -> dict[str, Any]:
        stages = {name: stage("not_attempted", "none", "blocked before executable search") for name in EXECUTABLE_STAGES}
        stages["recognition"] = stage("partial", root.recognition, "semantic root was captured but no executable family closed")
        stages["contract_inference"] = stage("blocked", "explicit unresolved contract", "; ".join(root.unresolved_contracts))
        closure = ExecutableFamilyClosure(
            root.family,
            root.grammar_version,
            root.semantic_hash,
            stages,
            {},
            root.unresolved_contracts,
            root.external_boundaries,
            False,
        )
        trace = self._build_blocked_trace(root)
        return {
            "schema_version": "vladder-executable-search-result-v1",
            "search_version": EXECUTABLE_SEARCH_VERSION,
            "status": "contract_blocked",
            "root": {"identifier": root.request.identifier, "family": root.family, "semantic_hash": root.semantic_hash},
            "closure": closure.to_dict(),
            "terminals": [],
            "trace": trace,
        }

    def _build_blocked_trace(self, root: CapturedRoot) -> dict[str, Any]:
        prior_root = make_root(
            root.graph,
            root.contract,
            [{"source_language": root.request.language or _language_from_source(root.request.source), "family": root.family}],
            project_id=root.request.project_id,
        )
        hardware = dict(root.request.hardware or {"architecture": "local", "cpu": cpu_model()})
        workload = dict(root.request.workload or {"phase": "search-capture"})
        seed = canonical_hash({
            "root": prior_root["root_id"],
            "family": root.family,
            "blockers": root.unresolved_contracts,
        })
        opportunities = _source_family_opportunities(root)
        baseline = make_branch(
            seed,
            {"family": "baseline", "family_version": "v1", "primitives": ["existing_implementation"]},
            parent_branch_id=None,
            depth=0,
            stage="baseline",
            baseline=True,
            state="expanded",
            evidence_coverage="partial",
            coverage={
                "children_status": "exhaustive",
                "emitted_child_count": 1 + len(opportunities),
                "expected_child_count": 1 + len(opportunities),
                "completeness_reason": "exhaustive_grammar",
            },
            identity_material={"seed": seed, "baseline": True},
        )
        sound_contract = root.blocked_authority == "sound_contract"
        family = make_branch(
            seed,
            {
                "family": root.family,
                "family_version": root.grammar_version,
                "primitives": ["contract_boundary" if sound_contract else "unrecognized_semantics"],
                "parameters": {"unresolved_count": len(root.unresolved_contracts)},
            },
            parent_branch_id=baseline["branch_id"],
            depth=1,
            stage="grammar_family",
            state="blocked" if sound_contract else "terminal",
            evidence_coverage="soundly_blocked" if sound_contract else "partial",
            coverage={
                "children_status": "soundly_closed" if sound_contract else "not_enumerated",
                "emitted_child_count": 0,
                "expected_child_count": 0 if sound_contract else None,
                "completeness_reason": "sound_contract" if sound_contract else "unknown",
                "soundness_proof_class": "typed-contract-boundary-v1" if sound_contract else "none",
            },
            identity_material={"seed": seed, "family": root.family, "blocked": True},
        )
        branches = [baseline, family]
        observations = [make_branch_observation(
            family["branch_id"],
            "grammar_disposition",
            "missing_contract" if sound_contract else "proof_unknown",
            quality_grade="A" if sound_contract else "D",
            proof_class="typed-contract-boundary-v1" if sound_contract else "recognition-incomplete",
        )]
        for opportunity in opportunities:
            disposition = str(opportunity["disposition"])
            soundly_closed = disposition == "inapplicable"
            branch = make_branch(
                seed,
                {
                    "family": str(opportunity["family"]),
                    "family_version": str(opportunity["grammar_version"]),
                    "primitives": ["family_opportunity"],
                    "parameters": {"disposition": disposition},
                },
                parent_branch_id=baseline["branch_id"],
                depth=1,
                stage="grammar_family",
                state="terminal" if soundly_closed else "blocked",
                evidence_coverage="complete" if soundly_closed else "partial",
                coverage={
                    "children_status": "not_applicable" if soundly_closed else "not_enumerated",
                    "emitted_child_count": 0,
                    "expected_child_count": 0 if soundly_closed else None,
                    "completeness_reason": "not_applicable" if soundly_closed else "missing_contract",
                    "soundness_proof_class": (
                        str(opportunity["authority"]) if soundly_closed else "none"
                    ),
                },
                identity_material={"seed": seed, "family_opportunity": opportunity},
            )
            branches.append(branch)
            observations.append(make_branch_observation(
                branch["branch_id"],
                "grammar_disposition",
                "inapplicable" if soundly_closed else "missing_contract",
                quality_grade="A" if soundly_closed else "C",
                proof_class=str(opportunity["authority"]),
            ))
        registry_families = sorted(
            [(root.family, root.grammar_version)]
            + [(str(item["family"]), str(item["grammar_version"])) for item in opportunities]
        )
        search = make_search(
            prior_root["root_id"],
            baseline["branch_id"],
            hardware,
            workload,
            grammar_version=EXECUTABLE_GRAMMAR_REGISTRY_VERSION,
            grammar_hash=canonical_hash({
                "registry": EXECUTABLE_GRAMMAR_REGISTRY_VERSION,
                "families": registry_families,
            }),
            selection_policy="bounded_exhaustive" if sound_contract else "manual",
            coverage="partial",
            stage_coverage={
                "grammar_family": "partial",
                "candidate_family": "not_attempted",
                "composition": "not_attempted",
                "cross_tu": "not_attempted",
            },
            identity_material={"seed": seed, "blocked": True},
        )
        for branch in branches:
            branch["search_id"] = search["search_id"]
        return {
            "schema_version": "vladder-authoritative-search-trace-v1",
            "grammar_version": EXECUTABLE_GRAMMAR_REGISTRY_VERSION,
            "roots": [prior_root],
            "searches": [search],
            "branches": branches,
            "observations": observations,
        }


def _compile_assembly(
    source_text: str,
    language: str,
    function: str,
    output: Path,
    *,
    dataflow_family: str | None = None,
    julia_signature: str | None = None,
) -> dict[str, Any]:
    output = output.resolve()
    if language == "rust":
        compiler = shutil.which("rustc")
        if not compiler:
            return {"status": "UNAVAILABLE", "reason": "rustc unavailable"}
        output.mkdir(parents=True, exist_ok=True)
        source = output / "candidate.rs"
        assembly = output / "candidate.s"
        source.write_text(source_text)
        command = [
            compiler, "--edition=2024", "--crate-type=lib", "-C", "opt-level=3",
            "-C", "target-cpu=native", "--emit", f"asm={assembly}", str(source),
        ]
        completed = subprocess.run(
            command, cwd=output, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if completed.returncode != 0:
            return {"status": "FAIL", "command": command, "stdout": completed.stdout, "stderr": completed.stderr}
        identity = _hot_assembly_identity(assembly, function)
        return {
            "status": "PASS" if identity.get("status") == "resolved" else "FAIL",
            "command": command,
            "assembly": str(assembly),
            "assembly_identity": identity.get("normalized_sha256"),
            "identity": identity,
        }
    if language == "zig":
        compiler = shutil.which("zig")
        if not compiler:
            return {"status": "UNAVAILABLE", "reason": "zig unavailable"}
        output.mkdir(parents=True, exist_ok=True)
        source = output / "candidate.zig"
        assembly = output / "candidate.s"
        obj = output / "candidate.o"
        source.write_text(source_text)
        command = [
            compiler, "build-obj", "-O", "ReleaseFast", "-mcpu", "native",
            f"-femit-bin={obj}", f"-femit-asm={assembly}", str(source),
        ]
        environment = os.environ.copy()
        environment["ZIG_GLOBAL_CACHE_DIR"] = str(output / "zig-global-cache")
        environment["ZIG_LOCAL_CACHE_DIR"] = str(output / "zig-local-cache")
        completed = subprocess.run(
            command, cwd=output, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
        )
        if completed.returncode != 0:
            return {"status": "FAIL", "command": command, "stdout": completed.stdout, "stderr": completed.stderr}
        identity = _hot_assembly_identity(assembly, function)
        return {
            "status": "PASS" if identity.get("status") == "resolved" else "FAIL",
            "command": command,
            "assembly": str(assembly),
            "assembly_identity": identity.get("normalized_sha256"),
            "identity": identity,
        }
    if language == "julia":
        compiler = shutil.which("julia")
        if not compiler:
            return {"status": "UNAVAILABLE", "reason": "julia unavailable"}
        if dataflow_family is None and julia_signature is None:
            return {"status": "FAIL", "reason": "Julia assembly capture requires a typed signature"}
        output.mkdir(parents=True, exist_ok=True)
        source = output / "candidate.jl"
        capture = output / "capture.jl"
        assembly = output / "candidate.s"
        source.write_text(source_text)
        signature = julia_signature or {
            "predicate-stable-compaction": "(Vector{UInt32}, Vector{UInt64}, Int, Vector{UInt64}, Vector{UInt64})",
            "fixed-width-codec": "(UInt16, UInt16, UInt32)",
            "stateful-delta-transducer": "(Vector{UInt64}, Vector{UInt32}, Vector{UInt64}, Int, Vector{UInt64}, Vector{UInt64})",
            "aos-fused-multi-reduction": "(Vector{DataflowRecord}, UInt32)",
            "quantized-block-4x4": "(Vector{DataflowPixel},)",
        }[dataflow_family]
        capture.write_text(
            source_text
            + "\nusing InteractiveUtils\n"
            + f'open(raw"{assembly}", "w") do io; code_native(io, {function}, {signature}; syntax=:intel, debuginfo=:none); end\n'
        )
        command = [compiler, "--startup-file=no", "-O3", "--check-bounds=no", str(capture)]
        completed = subprocess.run(
            command, cwd=output, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if completed.returncode != 0:
            return {"status": "FAIL", "command": command, "stdout": completed.stdout, "stderr": completed.stderr}
        identity = _hot_assembly_identity(assembly, function)
        return {
            "status": "PASS" if identity.get("status") == "resolved" else "FAIL",
            "command": command,
            "assembly": str(assembly),
            "assembly_identity": identity.get("normalized_sha256"),
            "identity": identity,
        }
    compiler = (
        shutil.which("clang-20") or shutil.which("clang")
        if language == "c" else
        shutil.which("clang++-20") or shutil.which("clang++") or shutil.which("g++")
    )
    if not compiler:
        return {"status": "UNAVAILABLE", "reason": "native compiler unavailable"}
    output.mkdir(parents=True, exist_ok=True)
    extension = "c" if language == "c" else "cpp"
    source = output / f"candidate.{extension}"
    assembly = output / "candidate.s"
    source.write_text(source_text)
    command = [compiler, "-std=c99" if language == "c" else "-std=c++20", "-O3", "-march=native", "-S", str(source), "-o", str(assembly)]
    completed = subprocess.run(
        command, cwd=output, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        return {"status": "FAIL", "command": command, "stdout": completed.stdout, "stderr": completed.stderr}
    identity = _hot_assembly_identity(assembly, function)
    return {
        "status": "PASS" if identity.get("status") == "resolved" else "FAIL",
        "command": command,
        "assembly": str(assembly),
        "assembly_identity": identity.get("normalized_sha256"),
        "identity": identity,
    }


def _matching_deep_derivation(derivations: tuple[DeepDerivation, ...], path: tuple[str, ...]) -> DeepDerivation | None:
    return next((item for item in derivations if tuple(rule.id for rule in item.rules) == path), None)


def _tuple_contract(contract: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(contract)
    if field in result:
        result[field] = tuple(result[field])
    return result


def _canonical_signature(
    language: str,
    source_region: str,
    request: ExecutableSearchRequest,
) -> str:
    configured = dict(request.contract or {}).get("canonical_signature")
    if isinstance(configured, str) and configured:
        return configured
    if language == "julia":
        if "Vector{Float32}" in source_region or "Array{Float32" in source_region:
            return "Vector{Float32},Vector{Float32}"
        return "Vector{UInt8},UInt8"
    brace = source_region.find("{")
    return source_region[:brace] if brace >= 0 else source_region.splitlines()[0]


def _nearest_file(start: Path, name: str) -> Path | None:
    current = start.resolve().parent if start.is_file() else start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _compiler_canonical_evidence(
    request: ExecutableSearchRequest,
    region: Any,
    source_region: str,
    output: Path,
) -> dict[str, Any]:
    """Bind source classification to the selected native compiler's semantic shape."""
    language = request.language or _language_from_source(request.source)
    output.mkdir(parents=True, exist_ok=True)
    try:
        if language == "rust" and request.source is not None:
            from .rust_adapter import RustRegionRequest, inspect_rust_region

            manifest = _nearest_file(request.source, "Cargo.toml")
            if manifest is None:
                return {"corroboration": {"status": "fail"}, "reason": "Cargo.toml not found for compiler extraction"}
            report = inspect_rust_region(RustRegionRequest(
                manifest, request.source, request.function or "root", output / "rust",
            ))
            return _canonical_adapter_evidence(report, "rustc MIR/LLVM", request.function or "root")
        if language == "zig" and request.source is not None:
            from .zig_adapter import ZigRegionRequest, inspect_zig_region

            marker = _nearest_file(request.source, "build.zig") or _nearest_file(request.source, "build.zig.zon")
            build_root = marker.parent if marker else request.source.resolve().parent
            report = inspect_zig_region(ZigRegionRequest(
                request.source, request.function or "root", output / "zig", build_root=build_root,
            ))
            return _canonical_adapter_evidence(report, "Zig LLVM", request.function or "root")
        if language == "julia" and request.source is not None:
            from .julia_adapter import JuliaRegionRequest, inspect_julia_region

            project_file = _nearest_file(request.source, "Project.toml")
            project = project_file.parent if project_file else request.source.resolve().parent
            module_match = re.search(r"(?m)^\s*module\s+([A-Za-z_]\w*)", request.source.read_text(errors="replace"))
            module = str(dict(request.contract or {}).get("julia_module") or (module_match.group(1) if module_match else request.source.stem))
            signature = _canonical_signature(language, source_region, request)
            report = inspect_julia_region(JuliaRegionRequest(
                project, request.source, module, request.function or "root", signature,
                output / "julia",
            ))
            return _canonical_adapter_evidence(report, "Julia typed LLVM", request.function or "root")
        if language == "cpp" and request.source is not None and request.compile_commands is not None:
            report = inspect_cpp_region(
                request.source,
                request.function or "root",
                request.compile_commands,
                output / "cpp",
                symbol=request.symbol,
                source_line=request.source_line,
                command_index=request.command_index,
            )
            compiler_text = json.dumps(report.get("region_closure", {}).get("semantic_graph", {}), sort_keys=True)
            corroboration = corroborate_compiler_shape(region, (compiler_text,))
            return {
                "corroboration": corroboration,
                "compiler_identity": str(report.get("compiler", {}).get("version") or "clang-selected-build"),
                "semantic_ir": "Clang AST+LLVM selected build",
                "language_contracts": {"selected_symbol": report.get("selection", {}).get("symbol")},
                "reason": "; ".join(str(item.get("reason")) for item in report.get("adapters", ())),
            }
        if language in {"c", "cpp"} and request.source is not None:
            compiler = (
                shutil.which("clang-20") or shutil.which("clang")
                if language == "c" else
                shutil.which("clang++-20") or shutil.which("clang++")
            )
            if not compiler:
                return {"corroboration": {"status": "fail"}, "reason": "Clang unavailable"}
            llvm = output / "source.ll"
            assembly = output / "source.s"
            command = [
                compiler, "-std=c17" if language == "c" else "-std=c++20",
                "-O1", "-S", "-emit-llvm", str(request.source), "-o", str(llvm),
            ]
            completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if completed.returncode != 0:
                return {
                    "corroboration": {"status": "fail"},
                    "reason": f"native compiler extraction failed: {completed.stderr[-1000:]}",
                }
            text = llvm.read_text(errors="replace")
            assembly_command = [
                compiler, "-std=c17" if language == "c" else "-std=c++20",
                "-O3", "-march=native", "-S", str(request.source), "-o", str(assembly),
            ]
            assembly_result = subprocess.run(
                assembly_command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            identity = (
                _hot_assembly_identity(assembly, request.function or "root")
                if assembly_result.returncode == 0 else {}
            )
            return {
                "corroboration": corroborate_compiler_shape(region, (text,)),
                "compiler_identity": compiler_version(compiler),
                "semantic_ir": "LLVM IR",
                "language_contracts": {"command": command},
                "source_assembly_identity": identity.get("normalized_sha256"),
            }
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"corroboration": {"status": "fail"}, "reason": str(error)}
    return {"corroboration": {"status": "fail"}, "reason": f"unsupported compiler extraction language: {language}"}


def _canonical_adapter_evidence(
    report: Mapping[str, Any], compiler_name: str, function: str,
) -> dict[str, Any]:
    graph = report.get("semantic_graph")
    contracts = graph.get("contracts", {}) if isinstance(graph, Mapping) else {}
    corroboration = contracts.get("compiler_corroboration", {})
    blockers = report.get("blockers", ())
    artifacts = report.get("artifacts", {})
    assembly = Path(str(artifacts.get("assembly"))) if isinstance(artifacts, Mapping) and artifacts.get("assembly") else None
    llvm = Path(str(artifacts.get("llvm_ir"))) if isinstance(artifacts, Mapping) and artifacts.get("llvm_ir") else None
    identity = (
        _hot_assembly_identity(assembly, function, llvm)
        if assembly is not None and assembly.is_file() else {}
    )
    return {
        "corroboration": dict(corroboration) if isinstance(corroboration, Mapping) else {"status": "fail"},
        "compiler_identity": compiler_name,
        "semantic_ir": str(graph.get("semantic_ir") if isinstance(graph, Mapping) else compiler_name),
        "language_contracts": dict(contracts.get("language_contracts", {})) if isinstance(contracts.get("language_contracts"), Mapping) else {},
        "source_assembly_identity": identity.get("normalized_sha256"),
        "reason": "; ".join(str(item.get("reason") if isinstance(item, Mapping) else item) for item in blockers),
    }


def _lifetime_candidate_from_dict(raw: Mapping[str, Any]) -> LifetimeCandidate:
    values = dict(raw)
    for name in (
        "invalidators", "non_invalidators", "proof_obligations",
        "lower_level_families", "diagnostics",
    ):
        values[name] = tuple(str(item) for item in values.get(name, ()))
    return LifetimeCandidate(**values)


def _language_from_source(source: Path | None) -> str:
    if source is None:
        return "cpp"
    return {
        ".c": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".rs": "rust",
        ".zig": "zig",
        ".jl": "julia",
    }.get(source.suffix.lower(), "cpp")


def _dispatch_family_id(root: CapturedRoot) -> str:
    requested = root.request.family
    if requested in SOURCE_DISPATCH_FAMILIES or requested in COMPILER_SOURCE_FAMILIES or requested == "selected-build-cpp":
        return requested
    return root.family


def _terminal_root(root: CapturedRoot, state: LazyState) -> CapturedRoot:
    if root.family != "source-family-dispatch":
        return root
    family = str(state.semantic_state.get("dispatch_family") or "")
    return next(
        item for item in root.family_alternatives
        if _dispatch_family_id(item) == family
    )


def _training_stage(stage_name: str) -> str:
    return stage_name if stage_name in {"grammar_family", "candidate_family", "composition", "cross_tu"} else "candidate_family"


def _training_action_parameters(action: Mapping[str, Any]) -> dict[str, Any]:
    parameters = {
        str(key): value
        for key, value in action.items()
        if key not in {"family", "family_version", "rule", "op", "parameter", "value"}
    }
    parameter = action.get("parameter")
    if isinstance(parameter, str) and parameter and "value" in action:
        parameters[parameter] = action["value"]
    return parameters


def _source_family_opportunities(root: CapturedRoot) -> tuple[dict[str, str], ...]:
    """Classify sibling local grammar families without manufacturing descendants.

    Negative authority is limited to the finite recognizer's declared source pattern. A family
    whose contract may apply but is not closed remains missing-contract rather than becoming a
    pruning negative.
    """
    source = root.source_region
    if not source:
        return ()
    language = root.request.language or _language_from_source(root.request.source)
    selected = root.family
    opportunities: list[dict[str, str]] = []

    def add(family: str, version: str, applicable: bool, authority: str) -> None:
        if family == selected:
            return
        opportunities.append({
            "family": family,
            "grammar_version": version,
            "disposition": "missing_contract" if applicable else "inapplicable",
            "authority": authority,
        })

    deep = inspect_source_realization(source, language, root.request.function or "root")
    add(
        "deep-information-realization",
        load_deep_grammar().version,
        deep.representable,
        "deep-source-archetype-recognizer-v2",
    )
    add(
        "ordered-prefix-suffix",
        ORDERED_PREFIX_GRAMMAR_VERSION,
        detect_ordered_reduction(source) is not None,
        "ordered-reduction-source-recognizer-v1",
    )
    add(
        "bit-popcount-reduction",
        BIT_REDUCTION_GRAMMAR_VERSION,
        detect_bit_reduction(
            source,
            source_context=(
                root.request.source.read_text(errors="replace")
                if root.request.source is not None else None
            ),
            function=root.request.function,
        ) is not None,
        "bit-reduction-source-recognizer-v1",
    )
    add(
        "predicate-reduction",
        PREDICATE_REDUCTION_GRAMMAR_VERSION,
        detect_predicate_reduction(source) is not None,
        "predicate-reduction-source-recognizer-v1",
    )
    inferred = infer_bounded_dataflow_contracts(
        source,
        root.request.function or "root",
    )
    add(
        "bounded-variable-output-dataflow",
        load_bounded_dataflow_grammar().version,
        bool(inferred),
        "bounded-dataflow-source-recognizer-v1",
    )
    add(
        "selected-build-cpp",
        SELECTED_BUILD_GRAMMAR_VERSION,
        language == "cpp" and root.request.compile_commands is not None,
        "selected-build-language-and-database-contract-v1",
    )
    return tuple(sorted(opportunities, key=lambda item: item["family"]))


def _compiler_identity(language: str) -> str:
    tool = {
        "c": shutil.which("clang-20") or shutil.which("clang"),
        "cpp": shutil.which("clang++-20") or shutil.which("clang++"),
        "rust": shutil.which("rustc"),
        "zig": shutil.which("zig"),
        "julia": shutil.which("julia"),
    }.get(language)
    return compiler_version(tool) if tool else "unavailable"


def _generic_graph(function: str, language: str, source: str) -> dict[str, Any]:
    return {
        "schema_version": "semantic-flow-v2",
        "name": function,
        "source_language": language,
        "nodes": [{"id": "region", "kind": "Call", "operation": "unbound-region", "output_type": None}],
        "edges": [],
        "obligations": [],
        "effects": [],
        "protocols": [],
        "claims": [{"status": "unverified", "scope": "region"}],
        "contracts": {"source_sha256": hashlib.sha256(source.encode()).hexdigest()},
    }


def _family_evidence_summary(
    root: CapturedRoot,
    terminals: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Expose terminal closure by real lazy family without inspecting artifacts."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in terminals:
        family = str(item.get("dispatch_family") or root.family)
        grouped.setdefault(family, []).append(item)
    return {
        family: {
            "terminal_count": len(items),
            "resolved_count": sum(bool(item.get("resolved")) for item in items),
            "proof_status_counts": dict(sorted(Counter(
                str(item.get("proof_status") or "UNKNOWN") for item in items
            ).items())),
            "compile_status_counts": dict(sorted(Counter(
                str(item.get("compile_status") or "UNKNOWN") for item in items
            ).items())),
            "physical_outcome_counts": dict(sorted(Counter(
                str(item.get("physical_outcome") or "unknown") for item in items
            ).items())),
            "distinct_assembly_count": len({
                str(item["assembly_identity"])
                for item in items if item.get("assembly_identity")
            }),
        }
        for family, items in sorted(grouped.items())
    }


def _failed_terminal(state: LazyState, realization: str, reason: str) -> dict[str, Any]:
    return {
        "candidate_id": canonical_hash({"state": state.identity, "failure": reason}),
        "state_id": state.identity,
        "realization": realization,
        "parameters": dict(state.semantic_state.get("parameters", {})),
        "proof_status": "FAIL",
        "proof_class": "none",
        "compile_status": "FAIL",
        "assembly_identity": None,
        "reason": reason,
    }


def _closure_from_dict(raw: Mapping[str, Any]) -> ExecutableFamilyClosure:
    from .executable_closure import ClosureStage

    return ExecutableFamilyClosure(
        str(raw["family"]),
        str(raw["grammar_version"]),
        str(raw["semantic_root_hash"]),
        {name: ClosureStage(**raw["stages"][name]) for name in EXECUTABLE_STAGES},
        {name: tuple(values) for name, values in raw.get("parameter_domains", {}).items()},
        tuple(raw.get("unresolved_contracts", ())),
        tuple(raw.get("external_boundaries", ())),
        bool(raw.get("exhaustive_within_domain")),
        str(raw.get("closure_hash", "")),
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n")


def load_executable_search_manifest(
    manifest_path: Path,
    output_directory: Path,
) -> tuple[dict[str, Any], tuple[ExecutableSearchRequest, ...]]:
    """Load one deterministic multi-root search manifest.

    Paths in the manifest are relative to the manifest, while all generated evidence is rooted
    under ``output_directory``. Contracts, workloads, and hardware profiles may be embedded or
    referenced as JSON/YAML files.
    """
    manifest_path = manifest_path.resolve()
    raw = _load_structured_mapping(manifest_path)
    if raw.get("schema_version") != EXECUTABLE_SEARCH_MANIFEST_VERSION:
        raise ValueError("unsupported executable search manifest schema")
    roots = raw.get("roots")
    if not isinstance(roots, list) or not roots:
        raise ValueError("executable search manifest requires a nonempty roots list")
    base = manifest_path.parent
    output_directory = output_directory.resolve()
    requests: list[ExecutableSearchRequest] = []
    identifiers: set[str] = set()
    for index, item in enumerate(roots):
        if not isinstance(item, dict):
            raise ValueError(f"root {index} must be a mapping")
        identifier = str(item.get("id") or f"root-{index:04d}")
        if identifier in identifiers:
            raise ValueError(f"duplicate executable search root id: {identifier}")
        identifiers.add(identifier)
        source_value = item.get("source")
        source = _resolve_optional_path(base, source_value)
        compile_commands = _resolve_optional_path(base, item.get("compile_commands"))
        command_indices: tuple[int | None, ...] = (
            (int(item["command_index"]),)
            if item.get("command_index") is not None else (None,)
        )
        if (
            str(item.get("compile_command_mode", "require_unique")) == "all"
            and source is not None and compile_commands is not None
            and str(item.get("language") or _language_from_source(source)) == "cpp"
            and item.get("command_index") is None
        ):
            discovered = matching_compilation_command_indices(source, compile_commands)
            command_indices = tuple(discovered) if discovered else (None,)
        for command_index in command_indices:
            expanded_identifier = (
                f"{identifier}@cc-{command_index}" if len(command_indices) > 1 else identifier
            )
            if expanded_identifier in identifiers and expanded_identifier != identifier:
                raise ValueError(f"duplicate expanded executable search root id: {expanded_identifier}")
            if expanded_identifier != identifier:
                identifiers.add(expanded_identifier)
            requests.append(ExecutableSearchRequest(
                identifier=expanded_identifier,
                output_directory=output_directory / "roots" / expanded_identifier,
                source=source,
                function=str(item["function"]) if item.get("function") is not None else None,
                language=str(item["language"]) if item.get("language") is not None else None,
                family=str(item.get("family", "auto")),
                contract=_load_embedded_or_path(base, item.get("contract")),
                project_id=str(item.get("project_id", raw.get("project_id", "local"))),
                workload=_load_embedded_or_path(base, item.get("workload")),
                hardware=_load_embedded_or_path(base, item.get("hardware")),
                node_budget=int(item.get("node_budget", raw.get("node_budget", 100_000))),
                terminal_workers=int(item.get("terminal_workers", raw.get("terminal_workers", 1))),
                lifetime_manifest=_resolve_optional_path(base, item.get("lifetime_manifest")),
                lifetime_trace=_resolve_optional_path(base, item.get("lifetime_trace")),
                compile_commands=compile_commands,
                symbol=str(item["symbol"]) if item.get("symbol") is not None else None,
                source_line=int(item["source_line"]) if item.get("source_line") is not None else (
                    int(item["line"]) if item.get("line") is not None else None
                ),
                command_index=command_index,
                cross_tu_seeds=tuple(str(value) for value in item.get("cross_tu_seeds", ())),
                max_upstream=int(item.get("max_upstream", 1)),
                max_downstream=int(item.get("max_downstream", 3)),
                max_cross_tu_nodes=int(item.get("max_cross_tu_nodes", 128)),
                protocol_manifest=_resolve_optional_path(base, item.get("protocol_manifest")),
                oracle_command=_oracle_command(item, raw),
                oracle_timeout_seconds=float(_oracle_value(item, raw, "timeout_seconds", 30.0)),
                oracle_prune_confidence=float(_oracle_value(item, raw, "prune_confidence", 0.999)),
                oracle_exploration_modulus=int(_oracle_value(item, raw, "exploration_modulus", 100)),
                oracle_exploration_slots=int(_oracle_value(item, raw, "exploration_slots", 5)),
                search_mode=str(item.get("search_mode", raw.get("search_mode", "exhaustive"))),
                search_work_budget=(
                    float(item.get("search_work_budget", raw.get("search_work_budget")))
                    if item.get("search_work_budget", raw.get("search_work_budget")) is not None else None
                ),
                search_time_budget_seconds=(
                    float(item.get("search_time_budget_seconds", raw.get("search_time_budget_seconds")))
                    if item.get("search_time_budget_seconds", raw.get("search_time_budget_seconds")) is not None
                    else None
                ),
                frontier_oracle_command=_frontier_oracle_command(item, raw),
                frontier_oracle_timeout_seconds=float(
                    _frontier_oracle_value(item, raw, "timeout_seconds", 30.0)
                ),
                search_memory_ceiling_bytes=(
                    int(item.get("search_memory_ceiling_bytes", raw.get("search_memory_ceiling_bytes")))
                    if item.get("search_memory_ceiling_bytes", raw.get("search_memory_ceiling_bytes")) is not None
                    else None
                ),
                search_checkpoint=_resolve_optional_path(base, item.get("search_checkpoint")),
                search_resume=_resolve_optional_path(base, item.get("search_resume")),
                por_policy=str(item.get("por_policy", raw.get("por_policy", "adaptive"))),
            ))
    return raw, tuple(requests)


def run_executable_search_manifest(
    manifest_path: Path,
    output_directory: Path,
    *,
    workers: int | None = None,
    shadow_exhaustive: bool | None = None,
    search_mode: str | None = None,
) -> dict[str, Any]:
    raw, requests = load_executable_search_manifest(manifest_path, output_directory)
    if search_mode is not None:
        requests = tuple(replace(item, search_mode=search_mode) for item in requests)
    selected_workers = int(
        workers if workers is not None else raw.get("workers", raw.get("root_workers", 1))
    )
    selected_shadow = bool(
        shadow_exhaustive
        if shadow_exhaustive is not None
        else raw.get("mode", "shadow_exhaustive") == "shadow_exhaustive"
    )
    cache_value = raw.get("cache_directory", ".vladder-cache/executable-search")
    cache_path = _resolve_optional_path(manifest_path.resolve().parent, cache_value)
    engine = ExecutableSearchEngine(cache_path)
    training_directory = (
        output_directory.resolve() / "training-v3"
        if bool(raw.get("emit_training_v3", True)) else None
    )
    report = engine.search_many(
        requests,
        workers=max(1, selected_workers),
        shadow_exhaustive=selected_shadow,
        training_output_directory=training_directory,
        artifact_retention=str(raw.get("artifact_retention", "full")),
        full_artifact_identifiers=tuple(
            str(value) for value in raw.get("full_artifact_identifiers", ())
        ),
    )
    result = {
        **report,
        "manifest": str(manifest_path.resolve()),
        "manifest_hash": canonical_hash(raw),
        "mode": search_mode or str(raw.get("search_mode", "exhaustive")),
        "workers": max(1, selected_workers),
        "terminal_workers": sorted({request_workers(item) for item in requests}),
    }
    _write_json(output_directory.resolve() / "executable-search-campaign.json", result)
    return result


def _emit_training_v3_record(
    result: Mapping[str, Any],
    request: ExecutableSearchRequest,
    output_directory: Path,
    identity_path: Path,
) -> dict[str, Any]:
    from .training_workflow import create_training_bundles_from_search_trace

    output_directory.mkdir(parents=True, exist_ok=True)
    trace = result.get("trace")
    if not isinstance(trace, dict):
        return {"identifier": request.identifier, "status": "missing_trace"}
    bundle_path = output_directory / f"{canonical_hash({'identifier': request.identifier})[:20]}.json"
    try:
        emitted = create_training_bundles_from_search_trace(
            trace,
            bundle_path,
            project_id=request.project_id,
            producer_agent="vladder-source-search",
            producer_model="deterministic-search",
            identity_path=identity_path,
        )
        labels: dict[str, int] = {}
        branch_count = 0
        bundle_paths = []
        decision_bundle_paths = []
        decision_count = 0
        for bundle, path in emitted:
            bundle_paths.append(str(path))
            branch_count += len(bundle.get("branches", ()))
            for branch in bundle.get("branches", ()):
                label = str(branch.get("survival", {}).get("class", "UNKNOWN"))
                labels[label] = labels.get(label, 0) + 1
            from .frontier_training import decision_bundle, reconstruct_search_decisions
            from .model_training_data import graph_learning_examples

            decisions = reconstruct_search_decisions(graph_learning_examples(path))
            if decisions:
                decision_path = path.with_name(path.stem + "-search-decisions.json")
                _write_json(
                    decision_path,
                    decision_bundle(decisions, source_schema=str(bundle.get("schema_version", "unknown"))),
                )
                decision_bundle_paths.append(str(decision_path))
                decision_count += len(decisions)
        return {
            "identifier": request.identifier,
            "status": "pass",
            "bundle": bundle_paths[0] if len(bundle_paths) == 1 else None,
            "bundles": bundle_paths,
            "packet_count": len(bundle_paths),
            "branch_count": branch_count,
            "search_decision_bundles": decision_bundle_paths,
            "search_decision_count": decision_count,
            "labels": dict(sorted(labels.items())),
        }
    except (OSError, ValueError, TypeError) as error:
        return {"identifier": request.identifier, "status": "fail", "error": str(error)[:4000]}


def _compact_decisive_root_artifacts(
    output_directory: Path, result: Mapping[str, Any],
) -> dict[str, Any]:
    """Discard reproducible build products while preserving decisive root evidence."""
    removed: list[str] = []
    reclaimed_bytes = 0
    for name in ("terminals", "regional-candidates", "selected-build-capture"):
        path = output_directory.resolve() / name
        if not path.is_dir():
            continue
        reclaimed_bytes += sum(
            item.stat().st_size for item in path.rglob("*") if item.is_file()
        )
        shutil.rmtree(path)
        removed.append(name)
    compressed: list[dict[str, Any]] = []
    for name in (
        "executable-search.json",
        "executable-search-trace.json",
        "composition-native-search-trace.json",
    ):
        path = output_directory.resolve() / name
        compressed_path = path.with_suffix(path.suffix + ".gz")
        if path.is_file():
            temporary = compressed_path.with_suffix(compressed_path.suffix + ".tmp")
            with path.open("rb") as source, gzip.open(temporary, "wb", compresslevel=9) as target:
                shutil.copyfileobj(source, target)
            temporary.replace(compressed_path)
            path.unlink()
        if compressed_path.is_file():
            compressed.append({
                "path": str(compressed_path),
                "sha256": hashlib.sha256(compressed_path.read_bytes()).hexdigest(),
                "bytes": compressed_path.stat().st_size,
            })
    summary_path = output_directory.resolve() / "executable-search-summary.json"
    _write_json(summary_path, {
        "schema_version": "vladder-executable-search-decisive-summary-v1",
        "search_version": result.get("search_version"),
        "request_fingerprint": result.get("request_fingerprint"),
        "status": result.get("status"),
        "evidence_status": result.get("evidence_status"),
        "family_evidence": result.get("family_evidence"),
        "root": result.get("root"),
        "closure": result.get("closure"),
        "claim_boundary": result.get("claim_boundary"),
        "compressed_artifacts": compressed,
    })
    return {
        "policy": "decisive",
        "removed_directories": removed,
        "reclaimed_bytes": reclaimed_bytes,
        "summary": str(summary_path),
        "compressed_artifacts": compressed,
        "preserved_artifacts": [
            "executable-search-summary.json",
            "executable-search.json.gz",
            "executable-search-trace.json.gz",
            "composition-native-search-trace.json.gz",
            "executable-closure.json",
        ],
    }


def _retained_root_artifact(output_directory: Path) -> Path:
    root = output_directory.resolve()
    for name in (
        "executable-search.json",
        "executable-search.json.gz",
        "executable-search-summary.json",
    ):
        path = root / name
        if path.is_file():
            return path
    return root / "executable-search.json"


def _training_v3_summary(
    records: Iterable[Mapping[str, Any]], output_directory: Path,
    *,
    expected_record_count: int | None = None,
) -> dict[str, Any]:
    ordered = sorted((dict(item) for item in records), key=lambda item: str(item["identifier"]))
    status_counts: dict[str, int] = {}
    labels: dict[str, int] = {}
    for record in ordered:
        status = str(record["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        for label, count in dict(record.get("labels", {})).items():
            labels[str(label)] = labels.get(str(label), 0) + int(count)
    complete = expected_record_count is None or len(ordered) == expected_record_count
    all_valid = bool(ordered) and status_counts.get("pass", 0) == len(ordered)
    return {
        "schema_version": "vladder-executable-search-training-emission-v1",
        "status": "pass" if complete and all_valid else "in_progress" if all_valid else "incomplete",
        "directory": str(output_directory),
        "record_count": len(ordered),
        "expected_record_count": expected_record_count,
        "complete": complete,
        "status_counts": dict(sorted(status_counts.items())),
        "label_counts": dict(sorted(labels.items())),
        "records": ordered,
    }


def _load_structured_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text()) if path.suffix.lower() == ".json" else yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a mapping in {path}")
    return dict(value)


def _oracle_config(item: Mapping[str, Any], manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    value = item.get("oracle", manifest.get("oracle", {}))
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("executable search oracle configuration must be a mapping")
    return value


def _oracle_command(item: Mapping[str, Any], manifest: Mapping[str, Any]) -> tuple[str, ...]:
    value = _oracle_config(item, manifest).get("command", ())
    if not isinstance(value, (list, tuple)) or not all(isinstance(part, str) for part in value):
        raise ValueError("oracle.command must be an argv-form string list")
    return tuple(value)


def _oracle_value(item: Mapping[str, Any], manifest: Mapping[str, Any], key: str, default: Any) -> Any:
    return _oracle_config(item, manifest).get(key, default)


def _frontier_oracle_config(item: Mapping[str, Any], manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    value = item.get("frontier_oracle", manifest.get("frontier_oracle", {}))
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("frontier_oracle configuration must be a mapping")
    return value


def _frontier_oracle_command(item: Mapping[str, Any], manifest: Mapping[str, Any]) -> tuple[str, ...]:
    value = _frontier_oracle_config(item, manifest).get("command", ())
    if not isinstance(value, (list, tuple)) or not all(isinstance(part, str) for part in value):
        raise ValueError("frontier_oracle.command must be an argv-form string list")
    return tuple(value)


def _frontier_oracle_value(item: Mapping[str, Any], manifest: Mapping[str, Any], key: str, default: Any) -> Any:
    return _frontier_oracle_config(item, manifest).get(key, default)


def _resolve_optional_path(base: Path, value: Any) -> Path | None:
    if value is None:
        return None
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _load_embedded_or_path(base: Path, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    path = _resolve_optional_path(base, value)
    if path is None or not path.is_file():
        raise ValueError(f"referenced search input does not exist: {path}")
    return _load_structured_mapping(path)
