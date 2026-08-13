from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from .canonical_search import (
    CANONICAL_SEARCH_VERSION,
    CANONICAL_STATE_ID_VERSION,
    CANONICAL_STATE_SCHEMA_VERSION,
    ActionFootprint,
    CanonicalSearchEdge,
    CanonicalSearchEngine,
    CanonicalSearchResult,
    CanonicalStateRecord,
    Canonicalizer,
    IndependenceEvidence,
    ReductionMetrics,
    reduction_waterfall,
)
from .language_adapter import canonical_hash
from .lazy_search import LazyGrammar, LazyState


PRODUCTION_SEARCH_SCHEMA_VERSION = "vladder-production-canonical-search-v1"
PRODUCTION_CHECKPOINT_SCHEMA_VERSION = "vladder-production-search-checkpoint-v1"
PRODUCTION_SEARCH_VERSION = "production-canonical-search-v1"


class ReductionLevel(str, Enum):
    ENUMERATE = "ENUMERATE"
    CANONICALIZE_ONLY = "CANONICALIZE_ONLY"
    CANONICALIZE_PLUS_POR = "CANONICALIZE_PLUS_POR"
    FULL_EXACT_REDUCTION = "FULL_EXACT_REDUCTION"


@dataclass(frozen=True)
class ProductionSearchConfig:
    mode: str = "exhaustive"
    node_budget: int = 1_000_000
    work_budget: int | None = None
    time_budget_seconds: float | None = None
    memory_ceiling_bytes: int | None = None
    por_strategy: str = "dynamic"
    por_policy: str = "adaptive"
    checkpoint_path: Path | None = None
    resume_path: Path | None = None
    checkpoint_on_completion: bool = True
    exhaustive_cost_minimization: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {
            "fast", "guided", "exhaustive", "exhaustive_canonical",
            "exhaustive_reduced", "guided_reduced",
        }:
            raise ValueError(f"unsupported production search mode: {self.mode}")
        if self.por_policy not in {"adaptive", "force", "off"}:
            raise ValueError("POR policy must be adaptive, force, or off")


@dataclass
class SearchCostSample:
    observations: int = 0
    candidate_construction_ms: float = 0.0
    proof_ms: float = 0.0
    compile_ms: float = 0.0
    benchmark_ms: float = 0.0
    canonicalization_ms: float = 0.0
    commutativity_ms: float = 0.0
    descendant_fanout: float = 1.0
    transposition_rate: float = 0.0

    def update(self, **values: float) -> None:
        self.observations += 1
        weight = 1.0 / self.observations
        for name, value in values.items():
            if not hasattr(self, name):
                continue
            current = float(getattr(self, name))
            setattr(self, name, current + weight * (float(value) - current))


class RollingSearchCostModel:
    """Empirical search-cost model. It has no semantic authority."""

    def __init__(self) -> None:
        self._samples: dict[str, SearchCostSample] = defaultdict(SearchCostSample)

    def sample(self, family: str) -> SearchCostSample:
        return self._samples[str(family)]

    def seed(self, family: str, values: Mapping[str, Any]) -> None:
        numeric = {
            key: float(value)
            for key, value in values.items()
            if key in SearchCostSample.__dataclass_fields__ and key != "observations"
            and isinstance(value, (int, float))
        }
        self.sample(family).update(**numeric)

    def update_from_result(self, result: CanonicalSearchResult) -> None:
        states = max(1, result.metrics.unique_canonical_states)
        terminals = max(1, len(result.terminal_state_ids))
        transposition_rate = result.metrics.exact_transpositions / max(
            1, result.metrics.raw_generated_states,
        )
        families = Counter(record.state.family for record in result.states)
        for family, count in families.items():
            share = count / states
            self.sample(family).update(
                candidate_construction_ms=(result.metrics.search_wall_ms * share) / max(1, count),
                proof_ms=(result.metrics.terminal_evaluation_wall_ms * share) / terminals,
                canonicalization_ms=(result.metrics.canonicalization_wall_ms * share) / max(1, count),
                commutativity_ms=(result.metrics.por_wall_ms * share) / max(
                    1, result.metrics.por_avoided_transitions,
                ),
                descendant_fanout=result.metrics.raw_generated_states / states,
                transposition_rate=transposition_rate,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            family: asdict(sample)
            for family, sample in sorted(self._samples.items())
        }


@dataclass(frozen=True)
class ReductionDecision:
    state_family: str
    depth: int
    frontier_size: int
    footprint_complete_ratio: float
    selected_level: str
    expected_saved_cost_ms: float
    expected_reduction_cost_ms: float
    reason: str


class AdaptiveReductionPolicy:
    """Select exact reduction effort without affecting semantic reachability."""

    def __init__(
        self,
        cost_model: RollingSearchCostModel,
        *,
        policy: str = "adaptive",
        exhaustive_cost_minimization: bool = False,
    ) -> None:
        self.cost_model = cost_model
        self.policy = policy
        self.exhaustive_cost_minimization = exhaustive_cost_minimization
        self.decisions: list[ReductionDecision] = []

    def allow_por(
        self,
        state: LazyState,
        actions: Sequence[Mapping[str, Any]],
        depth: int,
        root_context: Mapping[str, Any],
    ) -> bool:
        footprints = tuple(ActionFootprint.from_action(action) for action in actions)
        complete = sum(item.complete for item in footprints)
        complete_ratio = complete / max(1, len(footprints))
        family = state.family
        sample = self.cost_model.sample(family)
        hints = root_context.get("search_cost", {})
        if isinstance(hints, Mapping):
            self.cost_model.seed(family, hints)
            sample = self.cost_model.sample(family)
        candidate_ms = max(0.001, sample.candidate_construction_ms)
        downstream_ms = max(
            candidate_ms,
            sample.proof_ms + sample.compile_ms + sample.benchmark_ms + candidate_ms,
        )
        fanout = len(actions)
        likely_duplicates = max(0.0, fanout - 1) * max(0.05, sample.transposition_rate or 0.5)
        expected_saved = likely_duplicates * max(1.0, sample.descendant_fanout) * downstream_ms
        pair_count = max(0, fanout * (fanout - 1) // 2)
        commutativity_ms = max(0.01, sample.commutativity_ms or sample.canonicalization_ms * 2.0)
        expected_cost = pair_count * commutativity_ms
        selected = ReductionLevel.CANONICALIZE_ONLY
        reason = "POR cost gate declined"
        if self.policy == "off":
            reason = "POR disabled by configuration"
        elif complete_ratio < 1.0:
            reason = "incomplete footprints fail open as dependent"
        elif fanout < 3:
            reason = "frontier too small for profitable ordering reduction"
        elif self.policy == "force" or self.exhaustive_cost_minimization:
            selected = ReductionLevel.CANONICALIZE_PLUS_POR
            reason = "qualified POR explicitly requested"
        elif expected_saved > expected_cost:
            selected = ReductionLevel.CANONICALIZE_PLUS_POR
            reason = "predicted downstream savings exceed reduction overhead"
        self.decisions.append(ReductionDecision(
            family,
            depth,
            fanout,
            complete_ratio,
            selected.value,
            expected_saved,
            expected_cost,
            reason,
        ))
        return selected == ReductionLevel.CANONICALIZE_PLUS_POR


class StateAnalysisCache:
    """Bounded LRU cache for analyses derived only from canonical identity."""

    def __init__(self, maximum_bytes: int | None = None) -> None:
        self.maximum_bytes = maximum_bytes
        self._values: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self._sizes: dict[tuple[str, str], int] = {}
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.current_bytes = 0
        self._lock = threading.RLock()

    def get_or_compute(self, state_id: str, analysis: str, compute: Callable[[], Any]) -> Any:
        key = (state_id, analysis)
        with self._lock:
            if key in self._values:
                self.hits += 1
                value = self._values.pop(key)
                self._values[key] = value
                return value
        value = compute()
        size = len(json.dumps(value, sort_keys=True, default=str).encode("utf-8"))
        with self._lock:
            self.misses += 1
            self._values[key] = value
            self._sizes[key] = size
            self.current_bytes += size
            self._enforce_limit()
        return value

    def _enforce_limit(self) -> None:
        if self.maximum_bytes is None:
            return
        while self.current_bytes > self.maximum_bytes and self._values:
            key, _ = self._values.popitem(last=False)
            self.current_bytes -= self._sizes.pop(key, 0)
            self.evictions += 1

    def clear_recomputable(self) -> None:
        with self._lock:
            self.evictions += len(self._values)
            self._values.clear()
            self._sizes.clear()
            self.current_bytes = 0

    def stats(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "entries": len(self._values),
            "current_bytes": self.current_bytes,
            "maximum_bytes": self.maximum_bytes,
        }


class FootprintCoverageAudit:
    def __init__(self) -> None:
        self._families: dict[str, Counter[str]] = defaultdict(Counter)

    def observe(self, state: LazyState, action: Mapping[str, Any]) -> None:
        family = str(action.get("family") or state.family)
        footprint = ActionFootprint.from_action(action)
        row = self._families[family]
        row["actions"] += 1
        row["complete" if footprint.complete else "partial" if action.get("footprint") else "missing"] += 1
        if footprint.complete:
            row["por_eligible"] += 1

    def to_dict(self, cost_model: RollingSearchCostModel) -> dict[str, Any]:
        families = []
        for family, counts in sorted(self._families.items()):
            actions = counts["actions"]
            sample = cost_model.sample(family)
            families.append({
                "grammar_family": family,
                "generated_actions": actions,
                "complete_footprints": counts["complete"],
                "partial_footprints": counts["partial"],
                "missing_footprints": counts["missing"],
                "complete_ratio": counts["complete"] / max(1, actions),
                "por_eligible_actions": counts["por_eligible"],
                "average_downstream_cost_ms": (
                    sample.candidate_construction_ms + sample.proof_ms + sample.compile_ms
                ),
            })
        return {"families": families}


def _identity(root_context: Mapping[str, Any], grammar: LazyGrammar) -> dict[str, str]:
    grammar_identity = {
        "class": f"{type(grammar).__module__}.{type(grammar).__qualname__}",
        "version": str(getattr(grammar, "version", getattr(grammar, "grammar_version", "unknown"))),
        "root_grammar_version": str(root_context.get("grammar_version", "unknown")),
    }
    return {
        "canonical_schema": CANONICAL_STATE_SCHEMA_VERSION,
        "canonical_identity_schema": CANONICAL_STATE_ID_VERSION,
        "search_engine": CANONICAL_SEARCH_VERSION,
        "production_engine": PRODUCTION_SEARCH_VERSION,
        "source_identity": str(root_context.get("semantic_hash", "unknown")),
        "grammar_identity": canonical_hash(grammar_identity),
        "target_identity": canonical_hash({
            "hardware": root_context.get("hardware", {}),
            "target": root_context.get("target", {}),
        }),
    }


class ProductionCheckpointStore:
    def __init__(self, canonicalizer: Canonicalizer | None = None) -> None:
        self.canonicalizer = canonicalizer or Canonicalizer()

    def save(
        self,
        path: Path,
        result: CanonicalSearchResult,
        identity: Mapping[str, str],
    ) -> None:
        runtime_states = {
            record.state_id: {
                "family": record.state.family,
                "stage": record.state.stage,
                "semantic_state": dict(record.state.semantic_state),
                "action": dict(record.state.action),
                "terminal": record.state.terminal,
                "deterministic_status": record.state.deterministic_status,
                "deterministic_reason": record.state.deterministic_reason,
                "identity": record.state.identity,
                "decision_projection": dict(record.state.decision_projection),
            }
            for record in result.states
        }
        payload = {
            "schema_version": PRODUCTION_CHECKPOINT_SCHEMA_VERSION,
            "identity": dict(identity),
            "saved_at_unix_ns": time.time_ns(),
            "frontier_state_ids": [
                record.state_id for record in result.states
                if record.exploration_status == "queued"
            ],
            "canonical_result": result.to_dict(),
            "runtime_states": runtime_states,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        temporary.replace(path)

    def load(self, path: Path, expected_identity: Mapping[str, str]) -> CanonicalSearchResult:
        payload = json.loads(path.read_text())
        if payload.get("schema_version") != PRODUCTION_CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("checkpoint schema is incompatible")
        if payload.get("identity") != dict(expected_identity):
            raise ValueError("checkpoint source, grammar, canonical schema, or target is incompatible")
        raw = payload["canonical_result"]
        runtime = payload["runtime_states"]
        records = []
        for item in raw["states"]:
            state_payload = runtime[item["state_id"]]
            state = LazyState(**state_payload)
            envelope = self.canonicalizer.envelope(state)
            if envelope.digest != item["canonical"]["digest"]:
                raise ValueError("checkpoint state digest differs from clean rematerialization")
            records.append(CanonicalStateRecord(
                item["state_id"],
                envelope,
                state,
                tuple(dict(action) for action in item["first_discovery_path"]),
                list(item["parent_edges"]),
                int(item["depth_minimum"]),
                int(item["depth_maximum"]),
                tuple(item["enabled_actions"]),
                str(item.get("proof_status", "not_evaluated")),
                str(item.get("compiler_status", "not_evaluated")),
                str(item.get("terminal_status", "nonterminal")),
                str(item.get("descendant_status", "unknown")),
                str(item.get("exploration_status", "queued")),
                dict(item.get("summaries", {})),
            ))
        metric_fields = ReductionMetrics.__dataclass_fields__
        metrics = ReductionMetrics(**{
            key: value for key, value in raw["metrics"].items() if key in metric_fields
        })
        evidence = tuple(IndependenceEvidence(**item) for item in raw.get("independence_evidence", ()))
        return CanonicalSearchResult(
            raw["schema_version"], raw["engine_version"], raw["mode"], raw["por_strategy"],
            bool(raw["complete"]), tuple(records),
            tuple(CanonicalSearchEdge(**item) for item in raw["edges"]),
            tuple(raw["terminal_state_ids"]), tuple(raw["terminal_canonical_hashes"]),
            metrics, evidence,
        )


@dataclass(frozen=True)
class ProductionSearchResult:
    requested_mode: str
    effective_mode: str
    identity: Mapping[str, str]
    canonical_result: CanonicalSearchResult
    reduction_decisions: tuple[ReductionDecision, ...]
    footprint_audit: Mapping[str, Any]
    cache_stats: Mapping[str, Any]
    cost_model: Mapping[str, Any]
    resource_policy: Mapping[str, Any]
    checkpoint: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PRODUCTION_SEARCH_SCHEMA_VERSION,
            "engine_version": PRODUCTION_SEARCH_VERSION,
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "identity": dict(self.identity),
            "complete": self.canonical_result.complete,
            "production_defaults": {
                "canonical_transposition": "enabled",
                "dependency_filtering": "enabled",
                "por": "qualified_and_cost_gated",
                "alpha_equivalence": "explicit_identity_only",
                "symmetry": "explicit_interchangeability_only",
                "learned_ordering": "optional_ordering_only",
            },
            "disabled_experimental_authorities": [
                "learned_deletion",
                "unqualified_dominance",
                "unqualified_macro_reduction",
                "coarse_optimization_equivalence",
                "global_ownership_or_protocol_egraphs",
            ],
            "canonical_state_dag": self.canonical_result.to_dict(),
            "reduction_waterfall": reduction_waterfall(self.canonical_result),
            "reduction_decisions": [asdict(item) for item in self.reduction_decisions],
            "footprint_audit": dict(self.footprint_audit),
            "analysis_caches": dict(self.cache_stats),
            "cost_model": dict(self.cost_model),
            "resource_policy": dict(self.resource_policy),
            "checkpoint": dict(self.checkpoint),
        }


class ProductionCanonicalSearchEngine:
    def __init__(
        self,
        canonicalizer: Canonicalizer | None = None,
        cost_model: RollingSearchCostModel | None = None,
    ) -> None:
        self.canonicalizer = canonicalizer or Canonicalizer()
        self.canonical = CanonicalSearchEngine(self.canonicalizer)
        self.cost_model = cost_model or RollingSearchCostModel()
        self.checkpoints = ProductionCheckpointStore(self.canonicalizer)

    @staticmethod
    def effective_mode(requested: str) -> str:
        return {
            "fast": "fast",
            "guided": "guided_reduced",
            "exhaustive": "exhaustive_reduced",
        }.get(requested, requested)

    def run(
        self,
        grammar: LazyGrammar,
        root_context: Mapping[str, Any],
        *,
        config: ProductionSearchConfig | None = None,
        frontier_policy: Any | None = None,
        terminal_evaluator: Callable[[LazyState], Mapping[str, Any]] | None = None,
    ) -> ProductionSearchResult:
        config = config or ProductionSearchConfig()
        identity = _identity(root_context, grammar)
        resume = None
        checkpoint_status: dict[str, Any] = {"loaded": False, "saved": False}
        if config.resume_path is not None:
            resume = self.checkpoints.load(config.resume_path, identity)
            checkpoint_status.update({"loaded": True, "loaded_from": str(config.resume_path)})
        audit = FootprintCoverageAudit()
        analysis_cache = StateAnalysisCache(
            maximum_bytes=(config.memory_ceiling_bytes // 8 if config.memory_ceiling_bytes else None),
        )
        reduction_policy = AdaptiveReductionPolicy(
            self.cost_model,
            policy=(
                "force"
                if config.mode in {"exhaustive_reduced", "guided_reduced"}
                and config.por_policy == "adaptive"
                else config.por_policy
            ),
            exhaustive_cost_minimization=config.exhaustive_cost_minimization,
        )
        effective_mode = self.effective_mode(config.mode)
        por_enabled = effective_mode in {"fast", "guided_reduced", "exhaustive_reduced"}
        result = self.canonical.run(
            grammar,
            root_context,
            mode=effective_mode,
            frontier_policy=frontier_policy,
            node_budget=config.node_budget,
            enable_por=por_enabled,
            por_strategy=config.por_strategy,
            terminal_evaluator=terminal_evaluator,
            por_decider=reduction_policy.allow_por if por_enabled else None,
            action_observer=audit.observe,
            analysis_cache=analysis_cache,
            work_budget=config.work_budget,
            time_budget_seconds=config.time_budget_seconds,
            memory_ceiling_bytes=config.memory_ceiling_bytes,
            resume_from=resume,
        )
        self.cost_model.update_from_result(result)
        checkpoint_path = config.checkpoint_path or config.resume_path
        if checkpoint_path is not None and (config.checkpoint_on_completion or not result.complete):
            self.checkpoints.save(checkpoint_path, result, identity)
            checkpoint_status.update({"saved": True, "saved_to": str(checkpoint_path)})
        return ProductionSearchResult(
            config.mode,
            effective_mode,
            identity,
            result,
            tuple(reduction_policy.decisions),
            audit.to_dict(self.cost_model),
            analysis_cache.stats(),
            self.cost_model.to_dict(),
            {
                "node_budget": config.node_budget,
                "work_budget": config.work_budget,
                "time_budget_seconds": config.time_budget_seconds,
                "memory_ceiling_bytes": config.memory_ceiling_bytes,
                "memory_ceiling_stop": bool(result.metrics.memory_ceiling_stops),
                "identity_preserved_on_resource_stop": True,
            },
            checkpoint_status,
        )
