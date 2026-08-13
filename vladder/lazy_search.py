from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
import heapq
import json
import math
from pathlib import Path
import select
import subprocess
import time
from typing import Any, Callable, Iterable, Mapping, Protocol

from .language_adapter import canonical_hash
from .composition_native import build_interaction_graph, exact_state_delta
from .search_decision_context import build_decision_context


LAZY_SEARCH_VERSION = "lazy-executable-search-v6"


class ExpansionDecision(str, Enum):
    EXPAND = "EXPAND"
    DEFER = "DEFER"
    PRUNE = "PRUNE"


@dataclass(frozen=True)
class PolicyDecision:
    decision: ExpansionDecision
    confidence: float = 1.0
    reason: str = ""
    in_distribution: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("policy confidence must be in [0, 1]")


@dataclass(frozen=True)
class LazyState:
    family: str
    stage: str
    semantic_state: Mapping[str, Any]
    action: Mapping[str, Any]
    terminal: bool = False
    deterministic_status: str = "possible"
    deterministic_reason: str = ""
    identity: str = ""
    decision_projection: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.deterministic_status not in {"possible", "impossible", "dominated"}:
            raise ValueError(f"invalid deterministic status: {self.deterministic_status}")
        if not self.identity:
            object.__setattr__(
                self,
                "identity",
                canonical_hash(
                    {
                        "family": self.family,
                        "stage": self.stage,
                        "semantic_state": dict(self.semantic_state),
                    }
                ),
            )


@dataclass(frozen=True)
class LazyTraceNode:
    node_id: str
    parent_id: str | None
    depth: int
    family: str
    stage: str
    action: dict[str, Any]
    semantic_state_hash: str
    terminal: bool
    disposition: str
    decision: str
    decision_reason: str
    decision_confidence: float
    in_distribution: bool
    canonical_of: str | None = None
    child_count: int = 0
    decision_context: dict[str, Any] = field(default_factory=dict)
    semantic_state: dict[str, Any] = field(default_factory=dict)
    search_cost: dict[str, float | int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Volatile wall-time evidence is emitted by the composition-native trace, not by the
        # deterministic legacy lazy-search serialization.
        return {key: value for key, value in asdict(self).items() if key != "search_cost"}


@dataclass(frozen=True)
class FrontierScore:
    score: float
    uncertainty: float = 0.0
    reason: str = ""
    in_distribution: bool = True


@dataclass(frozen=True)
class FrontierDecisionTrace:
    decision_id: str
    parent_node_id: str | None
    parent_state_hash: str
    depth: int
    history: tuple[dict[str, Any], ...]
    frontier: tuple[dict[str, Any], ...]
    chosen_state_hash: str | None
    parent_semantic_state: dict[str, Any] = field(default_factory=dict)
    parent_decision_context: dict[str, Any] = field(default_factory=dict)
    interaction_graph: dict[str, Any] = field(default_factory=dict)
    scoring_wall_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key != "scoring_wall_ms"}


@dataclass(frozen=True)
class LazySearchResult:
    version: str
    mode: str
    complete: bool
    nodes: tuple[LazyTraceNode, ...]
    terminals: tuple[LazyState, ...]
    expansions: int
    deferred: int
    policy_pruned: int
    deterministic_pruned: int
    canonicalized: int
    frontier_decisions: tuple[FrontierDecisionTrace, ...] = ()
    equivalence_proposals: int = 0
    verified_equivalences: int = 0
    maximum_frontier_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "nodes": [item.to_dict() for item in self.nodes],
            "terminals": [
                {
                    "identity": item.identity,
                    "family": item.family,
                    "stage": item.stage,
                    "semantic_state": dict(item.semantic_state),
                    "action": dict(item.action),
                }
                for item in self.terminals
            ],
            "frontier_decisions": [item.to_dict() for item in self.frontier_decisions],
        }


class ExpansionPolicy(Protocol):
    def decide(self, state: LazyState, *, depth: int, root_context: Mapping[str, Any]) -> PolicyDecision: ...


class ExhaustivePolicy:
    def decide(self, state: LazyState, *, depth: int, root_context: Mapping[str, Any]) -> PolicyDecision:
        return PolicyDecision(ExpansionDecision.EXPAND, 1.0, "exhaustive shadow expansion", True)


class FrontierScoringPolicy(Protocol):
    def score(
        self,
        parent: LazyState | None,
        frontier: tuple[LazyState, ...],
        *,
        depth: int,
        history: tuple[dict[str, Any], ...],
        root_context: Mapping[str, Any],
    ) -> tuple[FrontierScore, ...]: ...


class StableFrontierPolicy:
    """Preserve grammar emission order while using the best-first runtime."""

    def score(
        self,
        parent: LazyState | None,
        frontier: tuple[LazyState, ...],
        *,
        depth: int,
        history: tuple[dict[str, Any], ...],
        root_context: Mapping[str, Any],
    ) -> tuple[FrontierScore, ...]:
        return tuple(FrontierScore(0.0, reason="stable FIFO grammar order") for _ in frontier)


class HandwrittenFrontierPolicy:
    """A deterministic priority baseline using only information available before expansion."""

    def score(
        self,
        parent: LazyState | None,
        frontier: tuple[LazyState, ...],
        *,
        depth: int,
        history: tuple[dict[str, Any], ...],
        root_context: Mapping[str, Any],
    ) -> tuple[FrontierScore, ...]:
        result = []
        for state in frontier:
            remaining = len(state.semantic_state.get("remaining_dimensions", ()))
            parameters = len(state.semantic_state.get("parameters", {}))
            score = 4.0 * float(state.terminal) + parameters - 0.5 * remaining - 0.1 * depth
            result.append(FrontierScore(score, reason="terminal/remaining-depth heuristic"))
        return tuple(result)


class EquivalenceProposalPolicy(Protocol):
    def propose(
        self,
        parent: LazyState | None,
        frontier: tuple[LazyState, ...],
        *,
        history: tuple[dict[str, Any], ...],
        root_context: Mapping[str, Any],
    ) -> Iterable[tuple[int, int]]: ...


class ConservativePolicy:
    """Apply a learned callback while guarding uncertainty, OOD, and exploration reserve."""

    def __init__(
        self,
        callback: Callable[[LazyState, int, Mapping[str, Any]], PolicyDecision],
        *,
        prune_confidence: float = 0.999,
        exploration_modulus: int = 100,
        exploration_slots: int = 5,
    ) -> None:
        if not 0.0 <= prune_confidence <= 1.0:
            raise ValueError("prune confidence must be in [0, 1]")
        if exploration_modulus < 1 or not 0 <= exploration_slots <= exploration_modulus:
            raise ValueError("invalid exploration reserve")
        self.callback = callback
        self.prune_confidence = prune_confidence
        self.exploration_modulus = exploration_modulus
        self.exploration_slots = exploration_slots

    def decide(self, state: LazyState, *, depth: int, root_context: Mapping[str, Any]) -> PolicyDecision:
        result = self.callback(state, depth, root_context)
        reserve = int(state.identity[:8], 16) % self.exploration_modulus < self.exploration_slots
        if result.decision is not ExpansionDecision.PRUNE:
            return result
        if reserve:
            return PolicyDecision(
                ExpansionDecision.EXPAND, result.confidence, "exploration reserve", result.in_distribution
            )
        if not result.in_distribution or result.confidence < self.prune_confidence:
            return PolicyDecision(
                ExpansionDecision.EXPAND,
                result.confidence,
                "fail-open: uncertain or out-of-distribution",
                result.in_distribution,
            )
        return result


class JsonLineExpansionPolicy:
    """Query a persistent external pruning oracle before each lazy expansion.

    The subprocess receives one ``register_root`` message per semantic root and then one
    ``decide`` message per partial state. Protocol failures fail open. Probabilistic
    ``BLOCKED_BY_CONTRACT`` results also fail open because only deterministic contract
    reasoning may eliminate a branch on semantic grounds.
    """

    def __init__(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float = 30.0,
        cwd: Path | None = None,
    ) -> None:
        if not command:
            raise ValueError("oracle command must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("oracle timeout must be positive")
        self.command = tuple(command)
        self.timeout_seconds = float(timeout_seconds)
        self.cwd = cwd
        self._process: subprocess.Popen[str] | None = None
        self._registered_root: str | None = None

    def decide(self, state: LazyState, *, depth: int, root_context: Mapping[str, Any]) -> PolicyDecision:
        root_hash = str(root_context.get("semantic_hash") or "unknown")
        try:
            if self._registered_root != root_hash:
                response = self._exchange(
                    {
                        "schema_version": "vladder-lazy-oracle-protocol-v1",
                        "kind": "register_root",
                        "root_id": root_hash,
                        "root": dict(root_context),
                    }
                )
                if response.get("status") != "ready":
                    raise RuntimeError(f"oracle rejected root: {response}")
                self._registered_root = root_hash
            response = self._exchange(
                {
                    "schema_version": "vladder-lazy-oracle-protocol-v1",
                    "kind": "decide",
                    "root_id": root_hash,
                    "depth": depth,
                    "ancestor_action_path": list(root_context.get("ancestor_action_path", ())),
                    "state": {
                        "identity": state.identity,
                        "family": state.family,
                        "stage": state.stage,
                        "action": dict(state.action),
                        "semantic_state": dict(state.semantic_state),
                        "decision_context": dict(root_context.get("decision_context", {})),
                    },
                }
            )
            return self._decision(response)
        except (BrokenPipeError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
            self.close()
            return PolicyDecision(
                ExpansionDecision.EXPAND,
                0.0,
                f"fail-open: pruning oracle unavailable ({error})",
                False,
            )

    def close(self) -> None:
        process, self._process = self._process, None
        self._registered_root = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self._process = subprocess.Popen(
            self.command,
            cwd=str(self.cwd) if self.cwd is not None else None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        return self._process

    def _exchange(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        process = self._ensure_process()
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("oracle pipes unavailable")
        process.stdin.write(json.dumps(dict(payload), sort_keys=True) + "\n")
        process.stdin.flush()
        ready, _, _ = select.select([process.stdout], [], [], self.timeout_seconds)
        if not ready:
            raise RuntimeError("oracle response timed out")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(f"oracle exited with status {process.poll()}")
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ValueError("oracle response must be a JSON object")
        return response

    @staticmethod
    def _decision(response: Mapping[str, Any]) -> PolicyDecision:
        raw = str(response.get("decision") or response.get("disposition") or "KEEP_UNCERTAIN")
        confidence = float(response.get("confidence", 0.0))
        in_distribution = bool(response.get("in_distribution", not bool(response.get("ood", False))))
        reason = str(response.get("reason") or raw.lower())
        if raw in {"KEEP", "KEEP_UNCERTAIN", "EXPAND"}:
            decision = ExpansionDecision.EXPAND
        elif raw in {"PRUNE", "PRUNE_HIGH_CONFIDENCE"}:
            decision = ExpansionDecision.PRUNE
        elif raw == "DEFER":
            decision = ExpansionDecision.DEFER
        elif raw == "BLOCKED_BY_CONTRACT":
            return PolicyDecision(
                ExpansionDecision.EXPAND,
                confidence,
                "fail-open: learned policy cannot establish contract impossibility",
                in_distribution,
            )
        else:
            return PolicyDecision(
                ExpansionDecision.EXPAND,
                0.0,
                f"fail-open: unknown oracle decision {raw}",
                False,
            )
        return PolicyDecision(decision, confidence, reason, in_distribution)


class JsonLineFrontierPolicy:
    """Query a persistent external oracle for priority scores, never deletion authority."""

    def __init__(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float = 30.0,
        cwd: Path | None = None,
    ) -> None:
        self.transport = JsonLineExpansionPolicy(command, timeout_seconds=timeout_seconds, cwd=cwd)
        self._registered_root: str | None = None

    def score(
        self,
        parent: LazyState | None,
        frontier: tuple[LazyState, ...],
        *,
        depth: int,
        history: tuple[dict[str, Any], ...],
        root_context: Mapping[str, Any],
    ) -> tuple[FrontierScore, ...]:
        root_hash = str(root_context.get("semantic_hash") or "unknown")
        try:
            if self._registered_root != root_hash:
                response = self.transport._exchange(
                    {
                        "schema_version": "vladder-frontier-oracle-protocol-v1",
                        "kind": "register_root",
                        "root_id": root_hash,
                        "root": dict(root_context),
                    }
                )
                if response.get("status") != "ready":
                    raise RuntimeError(f"oracle rejected root: {response}")
                self._registered_root = root_hash
            response = self.transport._exchange(
                {
                    "schema_version": "vladder-frontier-oracle-protocol-v1",
                    "kind": "rank_frontier",
                    "root_id": root_hash,
                    "depth": depth,
                    "parent": _frontier_state(parent),
                    "history": list(history),
                    "frontier": [_frontier_state(state) for state in frontier],
                }
            )
            values = response.get("scores")
            if not isinstance(values, list) or len(values) != len(frontier):
                raise ValueError("oracle must return one frontier score per state")
            result = []
            for value in values:
                if not isinstance(value, dict):
                    raise ValueError("frontier score must be an object")
                result.append(
                    FrontierScore(
                        float(value.get("score", 0.0)),
                        max(0.0, float(value.get("uncertainty", 0.0))),
                        str(value.get("reason", "learned best-first priority")),
                        bool(value.get("in_distribution", not bool(value.get("ood", False)))),
                    )
                )
            return tuple(result)
        except (BrokenPipeError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
            self.close()
            return tuple(
                FrontierScore(0.0, 1.0, f"fail-open stable priority: {error}", False) for _ in frontier
            )

    def close(self) -> None:
        self.transport.close()
        self._registered_root = None


class JsonLineEquivalenceProposalPolicy:
    """Propose potential equivalent sibling pairs; the search verifier remains authoritative."""

    def __init__(self, command: tuple[str, ...], *, timeout_seconds: float = 30.0) -> None:
        self.transport = JsonLineExpansionPolicy(command, timeout_seconds=timeout_seconds)

    def propose(
        self,
        parent: LazyState | None,
        frontier: tuple[LazyState, ...],
        *,
        history: tuple[dict[str, Any], ...],
        root_context: Mapping[str, Any],
    ) -> Iterable[tuple[int, int]]:
        try:
            response = self.transport._exchange(
                {
                    "schema_version": "vladder-frontier-oracle-protocol-v1",
                    "kind": "propose_equivalence",
                    "root_id": str(root_context.get("semantic_hash") or "unknown"),
                    "parent": _frontier_state(parent),
                    "history": list(history),
                    "frontier": [_frontier_state(state) for state in frontier],
                }
            )
            pairs = response.get("pairs", ())
            return tuple((int(pair[0]), int(pair[1])) for pair in pairs if isinstance(pair, list) and len(pair) == 2)
        except (BrokenPipeError, OSError, RuntimeError, ValueError, json.JSONDecodeError):
            self.close()
            return ()

    def close(self) -> None:
        self.transport.close()


def _frontier_state(state: LazyState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "identity": state.identity,
        "family": state.family,
        "stage": state.stage,
        "action": dict(state.action),
        "semantic_state": dict(state.semantic_state),
        "decision_projection": dict(state.decision_projection),
    }


class LazyGrammar(Protocol):
    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]: ...
    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]: ...


class FiniteParameterGrammar:
    """Lazily expands one finite parameter dimension at a time."""

    def __init__(
        self,
        family: str,
        domains: Mapping[str, tuple[Any, ...]],
        *,
        legality: Callable[[Mapping[str, Any], Mapping[str, Any]], tuple[bool, str]] | None = None,
    ) -> None:
        if not domains or any(not values for values in domains.values()):
            raise ValueError("finite parameter grammar requires nonempty domains")
        self.family = family
        self.domains = tuple((str(key), tuple(values)) for key, values in domains.items())
        self.legality = legality

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return (self._state({}, 0, root_context, {"family": self.family, "op": "enter"}),)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return tuple(
            child
            for action in self.enabled_actions(state, root_context)
            if (child := self.apply_action(state, action, root_context)) is not None
        )

    def enabled_actions(
        self, state: LazyState, root_context: Mapping[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        index = int(state.semantic_state["next_dimension"])
        if index >= len(self.domains):
            return ()
        name, values = self.domains[index]
        return tuple(
            {
                "action_key": f"{self.family}:{name}={value!r}",
                "family": self.family,
                "parameter": name,
                "value": value,
                "footprint": {
                    "complete": True,
                    "reads": [f"parameter-domain:{name}"],
                    "writes": [f"parameter-selection:{name}"],
                    "owners": [f"parameter:{name}"],
                    "representations_read": ["partial-candidate"],
                    "representations_written": ["partial-candidate"],
                },
            }
            for value in values
        )

    def apply_action(
        self,
        state: LazyState | None,
        action: Mapping[str, Any],
        root_context: Mapping[str, Any],
    ) -> LazyState | None:
        if state is None:
            return None
        index = int(state.semantic_state["next_dimension"])
        if index >= len(self.domains):
            return None
        name, values = self.domains[index]
        if action.get("parameter") != name or action.get("value") not in values:
            return None
        selected = dict(state.semantic_state.get("parameters", {}))
        return self._state(
            {**selected, name: action["value"]},
            index + 1,
            root_context,
            action,
        )

    def _state(
        self,
        parameters: Mapping[str, Any],
        next_dimension: int,
        root_context: Mapping[str, Any],
        action: Mapping[str, Any],
    ) -> LazyState:
        legal, reason = self.legality(parameters, root_context) if self.legality else (True, "")
        terminal = next_dimension == len(self.domains)
        semantic = {
            "parameters": dict(parameters),
            "next_dimension": next_dimension,
            "remaining_dimensions": [name for name, _ in self.domains[next_dimension:]],
            "root_semantic_hash": str(root_context.get("semantic_hash", "unbound")),
        }
        return LazyState(
            self.family,
            "candidate" if terminal else "partial_candidate",
            semantic,
            action,
            terminal=terminal,
            deterministic_status="possible" if legal else "impossible",
            deterministic_reason=reason,
        )


class LazySearchEngine:
    def run(
        self,
        grammar: LazyGrammar,
        root_context: Mapping[str, Any],
        *,
        policy: ExpansionPolicy | None = None,
        frontier_policy: FrontierScoringPolicy | None = None,
        equivalence_proposer: EquivalenceProposalPolicy | None = None,
        equivalence_verifier: Callable[[LazyState, LazyState, Mapping[str, Any]], bool] | None = None,
        mode: str = "shadow_exhaustive",
        node_budget: int = 100_000,
        work_budget: float | None = None,
        time_budget_seconds: float | None = None,
    ) -> LazySearchResult:
        if mode not in {"shadow_exhaustive", "live", "fast", "guided", "exhaustive"}:
            raise ValueError(f"unsupported lazy-search mode: {mode}")
        if work_budget is not None and work_budget <= 0:
            raise ValueError("work budget must be positive")
        if time_budget_seconds is not None and time_budget_seconds <= 0:
            raise ValueError("time budget must be positive")
        if mode in {"fast", "guided", "exhaustive"}:
            # Anytime modes alter order and budget only. Learned or heuristic deletion is not an
            # authority in this program; legacy live/shadow modes retain the RC24 policy surface.
            policy = ExhaustivePolicy()
        else:
            policy = policy or ExhaustivePolicy()
        frontier_policy = frontier_policy or StableFrontierPolicy()
        structured_exploration = not isinstance(frontier_policy, StableFrontierPolicy)
        queue: list[tuple[float, int, LazyState, str, str | None, int, tuple[dict[str, Any], ...]]] = []
        traces: list[LazyTraceNode] = []
        frontier_traces: list[FrontierDecisionTrace] = []
        terminals: list[LazyState] = []
        canonical_owner: dict[str, str] = {}
        expansions = deferred = policy_pruned = deterministic_pruned = canonicalized = 0
        equivalence_proposals = verified_equivalences = 0
        maximum_frontier_size = 0
        sequence = 0
        work = 0.0
        complete = True
        started = time.monotonic()
        family_enqueue_count: Counter[str] = Counter()

        def search_priority(state: LazyState, score: FrontierScore) -> float:
            priority = score.score + score.uncertainty
            if not structured_exploration:
                return priority
            # Unknown actions and the first few actions from a sparse family are explored early.
            # This changes ordering only; no branch becomes unreachable in exhaustive mode.
            if not score.in_distribution:
                priority += 2.0
            priority += 0.5 / math.sqrt(1.0 + family_enqueue_count[state.family])
            return priority

        def enqueue(
            parent: LazyState | None,
            children: tuple[LazyState, ...],
            parent_id: str | None,
            depth: int,
            history: tuple[dict[str, Any], ...],
        ) -> None:
            nonlocal sequence, canonicalized, deterministic_pruned
            nonlocal equivalence_proposals, verified_equivalences, maximum_frontier_size
            eligible: list[tuple[LazyState, str]] = []
            for state in children:
                node_id = self._node_id(state, parent_id, root_context)
                if state.deterministic_status in {"impossible", "dominated"}:
                    deterministic_pruned += 1
                    context = self._decision_context(state, depth, history, root_context)
                    traces.append(
                        self._trace(
                            state,
                            node_id,
                            parent_id,
                            depth,
                            state.deterministic_status,
                            PolicyDecision(ExpansionDecision.PRUNE, 1.0, state.deterministic_reason, True),
                            decision_context=context,
                        )
                    )
                    continue
                owner = canonical_owner.get(state.identity)
                if owner is not None:
                    canonicalized += 1
                    context = self._decision_context(state, depth, history, root_context)
                    traces.append(
                        self._trace(
                            state,
                            node_id,
                            parent_id,
                            depth,
                            "canonical_duplicate",
                            PolicyDecision(ExpansionDecision.PRUNE, 1.0, "exact semantic state memoized", True),
                            canonical_of=owner,
                            decision_context=context,
                        )
                    )
                    continue
                canonical_owner[state.identity] = node_id
                eligible.append((state, node_id))
            states = tuple(item[0] for item in eligible)
            if equivalence_proposer is not None and equivalence_verifier is not None and len(states) > 1:
                aliases: set[int] = set()
                for left, right in equivalence_proposer.propose(
                    parent, states, history=history, root_context=root_context
                ):
                    equivalence_proposals += 1
                    if left == right or left not in range(len(states)) or right not in range(len(states)):
                        continue
                    if left in aliases or right in aliases:
                        continue
                    if equivalence_verifier(states[left], states[right], root_context):
                        aliases.add(right)
                        verified_equivalences += 1
                        canonicalized += 1
                        state, node_id = eligible[right]
                        context = self._decision_context(state, depth, history, root_context)
                        traces.append(
                            self._trace(
                                state,
                                node_id,
                                parent_id,
                                depth,
                                "verified_equivalent",
                                PolicyDecision(
                                    ExpansionDecision.PRUNE,
                                    1.0,
                                    "formal equivalence verifier accepted proposed alias",
                                    True,
                                ),
                                canonical_of=eligible[left][1],
                                decision_context=context,
                            )
                        )
                eligible = [item for index, item in enumerate(eligible) if index not in aliases]
                states = tuple(item[0] for item in eligible)
            if not eligible:
                return
            child_contexts = tuple(
                self._decision_context(state, depth, history, root_context) for state in states
            )
            parent_context = (
                self._decision_context(parent, max(0, depth - 1), history[:-1], root_context)
                if parent is not None else {
                    "context_version": "composition-root-v1",
                    "quality": "root_only",
                    "graph": dict(root_context.get("semantic_graph", {})),
                    "focus_node_ids": [],
                    "state_features": {"depth": 0, "stage": "root", "terminal": False},
                    "semantic_delta": {},
                    "canonical_state_hash": str(root_context.get("semantic_hash", "root")),
                }
            )
            scoring_started = time.perf_counter()
            scores = frontier_policy.score(
                parent,
                states,
                depth=depth,
                history=history,
                root_context=root_context,
            )
            if len(scores) != len(states):
                raise ValueError("frontier policy must return exactly one score per eligible action")
            scoring_wall_ms = (time.perf_counter() - scoring_started) * 1000.0
            maximum_frontier_size = max(maximum_frontier_size, len(queue) + len(states))
            ranked = sorted(
                zip(eligible, scores, strict=True),
                key=lambda item: -search_priority(item[0][0], item[1]),
            )
            frontier_traces.append(
                FrontierDecisionTrace(
                    decision_id=canonical_hash(
                        {
                            "parent": parent_id,
                            "history": history,
                            "frontier": [state.identity for state in states],
                        }
                    ),
                    parent_node_id=parent_id,
                    parent_state_hash=parent.identity
                    if parent is not None
                    else str(root_context.get("semantic_hash", "root")),
                    depth=depth,
                    history=history,
                    frontier=tuple(
                        {
                            "state_hash": state.identity,
                            "action": dict(state.action),
                            "semantic_state": dict(state.semantic_state),
                            "decision_context": child_context,
                            "state_delta": exact_state_delta(
                                parent_context,
                                child_context,
                                dict(parent.semantic_state) if parent is not None else {},
                                state.semantic_state,
                            ),
                            "score": score.score,
                            "uncertainty": score.uncertainty,
                            "reason": score.reason,
                            "in_distribution": score.in_distribution,
                        }
                        for state, child_context, score in zip(states, child_contexts, scores, strict=True)
                    ),
                    chosen_state_hash=ranked[0][0][0].identity if ranked else None,
                    parent_semantic_state=dict(parent.semantic_state) if parent is not None else {},
                    parent_decision_context=parent_context,
                    interaction_graph=build_interaction_graph(
                        parent_context,
                        history,
                        tuple(
                            {
                                "state_hash": state.identity,
                                "action": dict(state.action),
                                "decision_context": child_context,
                                "state_delta": exact_state_delta(
                                    parent_context,
                                    child_context,
                                    dict(parent.semantic_state) if parent is not None else {},
                                    state.semantic_state,
                                ),
                            }
                            for state, child_context in zip(states, child_contexts, strict=True)
                        ),
                    ),
                    scoring_wall_ms=scoring_wall_ms,
                )
            )
            for (state, node_id), score in zip(eligible, scores, strict=True):
                priority = search_priority(state, score)
                family_enqueue_count[state.family] += 1
                heapq.heappush(queue, (-priority, sequence, state, node_id, parent_id, depth, history))
                sequence += 1

        enqueue(None, tuple(grammar.initial_states(root_context)), None, 0, ())
        while queue:
            if len(traces) >= node_budget:
                complete = False
                break
            if work_budget is not None and work >= work_budget:
                complete = False
                break
            if time_budget_seconds is not None and time.monotonic() - started >= time_budget_seconds:
                complete = False
                break
            _, _, state, node_id, parent_id, depth, ancestor_actions = heapq.heappop(queue)
            work += 1.0
            context = self._decision_context(state, depth, ancestor_actions, root_context)
            decision_context = {
                **dict(root_context),
                "ancestor_action_path": [*ancestor_actions, dict(state.action)],
                "decision_context": context,
            }
            decision = policy.decide(state, depth=depth, root_context=decision_context)
            if decision.decision is ExpansionDecision.PRUNE:
                policy_pruned += 1
                complete = False
                traces.append(
                    self._trace(
                        state,
                        node_id,
                        parent_id,
                        depth,
                        "policy_pruned",
                        decision,
                        decision_context=context,
                    )
                )
                continue
            if decision.decision is ExpansionDecision.DEFER:
                deferred += 1
                complete = False
                traces.append(
                    self._trace(
                        state,
                        node_id,
                        parent_id,
                        depth,
                        "deferred",
                        decision,
                        decision_context=context,
                    )
                )
                continue
            if state.terminal:
                terminals.append(state)
                traces.append(
                    self._trace(
                        state,
                        node_id,
                        parent_id,
                        depth,
                        "terminal",
                        decision,
                        decision_context=context,
                    )
                )
                continue
            expansion_started = time.perf_counter()
            children = tuple(grammar.expand(state, root_context))
            expansion_wall_ms = (time.perf_counter() - expansion_started) * 1000.0
            expansions += 1
            traces.append(
                self._trace(
                    state,
                    node_id,
                    parent_id,
                    depth,
                    "expanded",
                    decision,
                    child_count=len(children),
                    decision_context=context,
                    search_cost={"node_expansions": 1, "expansion_wall_ms": expansion_wall_ms},
                )
            )
            child_ancestors = (*ancestor_actions, dict(state.action))
            enqueue(state, children, node_id, depth + 1, child_ancestors)
        actual_children = Counter(item.parent_id for item in traces if item.parent_id is not None)
        traces = [
            replace(item, child_count=actual_children.get(item.node_id, 0)) if item.disposition == "expanded" else item
            for item in traces
        ]
        return LazySearchResult(
            LAZY_SEARCH_VERSION,
            mode,
            complete,
            tuple(traces),
            tuple(terminals),
            expansions,
            deferred,
            policy_pruned,
            deterministic_pruned,
            canonicalized,
            tuple(frontier_traces),
            equivalence_proposals,
            verified_equivalences,
            maximum_frontier_size,
        )

    @staticmethod
    def _node_id(state: LazyState, parent_id: str | None, root_context: Mapping[str, Any]) -> str:
        return canonical_hash(
            {
                "root": root_context.get("semantic_hash"),
                "parent": parent_id,
                "state": state.identity,
                "action": dict(state.action),
            }
        )

    @staticmethod
    def _trace(
        state: LazyState,
        node_id: str,
        parent_id: str | None,
        depth: int,
        disposition: str,
        decision: PolicyDecision,
        *,
        canonical_of: str | None = None,
        child_count: int = 0,
        decision_context: Mapping[str, Any] | None = None,
        search_cost: Mapping[str, float | int] | None = None,
    ) -> LazyTraceNode:
        return LazyTraceNode(
            node_id,
            parent_id,
            depth,
            state.family,
            state.stage,
            dict(state.action),
            state.identity,
            state.terminal,
            disposition,
            decision.decision.value,
            decision.reason,
            decision.confidence,
            decision.in_distribution,
            canonical_of,
            child_count,
            dict(decision_context or {}),
            dict(state.semantic_state),
            dict(search_cost or {
                "node_expansions": int(disposition in {"expanded", "terminal"}),
            }),
        )

    @staticmethod
    def _decision_context(
        state: LazyState,
        depth: int,
        ancestor_actions: tuple[dict[str, Any], ...],
        root_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        return build_decision_context(
            root_context.get("semantic_graph", {}),
            semantic_state=state.semantic_state,
            action=state.action,
            ancestor_actions=ancestor_actions,
            depth=depth,
            stage=state.stage,
            terminal=state.terminal,
            projection=state.decision_projection,
        )
