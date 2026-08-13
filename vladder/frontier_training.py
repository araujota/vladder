from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable, Mapping

from .language_adapter import canonical_hash


FRONTIER_TRAINING_VERSION = "vladder-search-decision-bundle-v1"
REDUNDANCY_CLASSES = (
    "unique",
    "canonical-equivalent",
    "compiler-identical",
    "dominated",
    "commutative-equivalent",
    "exhausted-dead",
)


@dataclass(frozen=True)
class FrontierOutcome:
    distance_to_useful: int | None
    contains_useful_descendant: bool | None
    contains_retained_descendant: bool | None
    useful_terminal_count: int | None
    subtree_cost: dict[str, float | int | None]
    redundancy_class: str


@dataclass(frozen=True)
class FrontierActionRecord:
    branch_id: str
    action: dict[str, Any]
    local_graph_delta: dict[str, Any]
    affected_semantic_owners: tuple[str, ...]
    candidate_arity: int
    composition_width: int
    contract_requirements: tuple[dict[str, Any], ...]
    estimated_expansion_cost: float | None
    canonical_state_hash: str | None
    canonical_relationship: str | None
    outcome: FrontierOutcome


@dataclass(frozen=True)
class SearchDecision:
    decision_id: str
    project: str
    root_id: str
    search_id: str
    parent_branch_id: str
    parent_state: dict[str, Any]
    search_history: tuple[dict[str, Any], ...]
    grammar_state: dict[str, Any]
    depth: int
    canonical_state_hash: str | None
    frontier: tuple[FrontierActionRecord, ...]
    oracle_chosen_branch_id: str
    evidence_limitations: tuple[str, ...]

    def inference_view(self) -> dict[str, Any]:
        """Return only values available before a frontier action is selected."""
        return {
            "decision_id": self.decision_id,
            "project": self.project,
            "root_id": self.root_id,
            "search_id": self.search_id,
            "parent_branch_id": self.parent_branch_id,
            "parent_state": self.parent_state,
            "search_history": list(self.search_history),
            "grammar_state": self.grammar_state,
            "depth": self.depth,
            "canonical_state_hash": self.canonical_state_hash,
            "frontier": [
                {key: value for key, value in asdict(item).items() if key != "outcome"} for item in self.frontier
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.inference_view(),
            "oracle_chosen_branch_id": self.oracle_chosen_branch_id,
            "descendant_outcomes": [{"branch_id": item.branch_id, **asdict(item.outcome)} for item in self.frontier],
            "evidence_limitations": list(self.evidence_limitations),
        }


def reconstruct_search_decisions(examples: Iterable[Mapping[str, Any]]) -> tuple[SearchDecision, ...]:
    """Reconstruct complete sibling decisions from lineage-aware v3 learning examples.

    RC24 did not retain exact canonical semantic-state hashes or retained outcomes. The migration
    marks those facts unavailable; it does not derive them from branch IDs or traversal order.
    """
    values = [dict(item) for item in examples]
    has_retained_terminal = any(
        bool(item.get("supervision", {}).get("targets", {}).get("direct_utility", {}).get("retained"))
        for item in values
    )
    by_id = {str(item["branch_id"]): item for item in values}
    children: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in values:
        parent = item.get("parent_branch_id")
        if parent is not None:
            children[(str(item["search_id"]), str(parent))].append(item)

    metrics: dict[str, dict[str, Any]] = {}

    def visit(branch_id: str) -> dict[str, Any]:
        if branch_id in metrics:
            return metrics[branch_id]
        item = by_id[branch_id]
        child_items = children.get((str(item["search_id"]), branch_id), ())
        child_metrics = [visit(str(child["branch_id"])) for child in child_items]
        direct = item["supervision"]["targets"]["direct_utility"]
        direct_useful = bool(
            direct.get("physically_material")
            or direct.get("retained")
            or direct.get("promoted")
            or (direct.get("proof_valid") and direct.get("distinct_realization"))
        )
        terminal_useful = direct_useful and not child_items
        distances = [child["distance"] for child in child_metrics if child["distance"] is not None]
        distance = 0 if terminal_useful else 1 + min(distances) if distances else None
        direct_cost = _direct_cost(item)
        subtree_cost = {
            key: _sum_known([direct_cost[key], *(child["subtree_cost"][key] for child in child_metrics)])
            for key in direct_cost
        }
        result = {
            "distance": distance,
            "useful_count": int(terminal_useful) + sum(child["useful_count"] for child in child_metrics),
            "retained": bool(direct.get("retained") or any(child["retained"] for child in child_metrics)),
            "subtree_cost": subtree_cost,
            "redundancy": _redundancy_class(item),
        }
        metrics[branch_id] = result
        return result

    for branch_id in by_id:
        visit(branch_id)

    decisions: list[SearchDecision] = []
    for (search_id, parent_id), siblings in children.items():
        parent = by_id.get(parent_id)
        if parent is None or len(siblings) < 2 or not _complete_frontier(parent, siblings):
            continue
        options = []
        for sibling in sorted(siblings, key=lambda item: str(item["branch_id"])):
            branch_id = str(sibling["branch_id"])
            metric = metrics[branch_id]
            context = sibling["decision_context"]
            graph = context["graph"]
            action = context["branch"]["action"]
            state = context.get("context", {})
            descendant = sibling["supervision"]["targets"]["descendant_utility"]
            canonical_state_hash = state.get("canonical_state_hash")
            options.append(
                FrontierActionRecord(
                    branch_id=branch_id,
                    action=dict(action),
                    local_graph_delta=dict(state.get("semantic_delta", {})),
                    affected_semantic_owners=tuple(str(index) for index in state.get("focus_node_indices", ())),
                    candidate_arity=_action_arity(action),
                    composition_width=max(1, len(context["branch"].get("ancestor_action_path", ()))),
                    contract_requirements=tuple(dict(item) for item in graph.get("obligations", ())),
                    estimated_expansion_cost=None,
                    canonical_state_hash=(str(canonical_state_hash) if canonical_state_hash is not None else None),
                    canonical_relationship=None,
                    outcome=FrontierOutcome(
                        distance_to_useful=metric["distance"],
                        contains_useful_descendant=descendant.get("useful"),
                        contains_retained_descendant=(
                            True if metric["retained"] else False if descendant.get("useful") is not None else None
                        ),
                        useful_terminal_count=metric["useful_count"],
                        subtree_cost=metric["subtree_cost"],
                        redundancy_class=metric["redundancy"],
                    ),
                )
            )
        oracle = min(options, key=_oracle_order_key)
        parent_context = parent["decision_context"]
        history = tuple(dict(item["action"]) for item in parent_context["branch"].get("ancestor_action_path", ()))
        decision_id = canonical_hash(
            {
                "search": search_id,
                "parent": parent_id,
                "frontier": [item.branch_id for item in options],
            }
        )
        parent_state_hash = parent_context.get("context", {}).get("canonical_state_hash")
        has_canonical_hashes = parent_state_hash is not None and all(
            item.canonical_state_hash is not None for item in options
        )
        decisions.append(
            SearchDecision(
                decision_id=decision_id,
                project=str(parent.get("project", "unknown")),
                root_id=str(parent["root_id"]),
                search_id=search_id,
                parent_branch_id=parent_id,
                parent_state={
                    "graph": parent_context["graph"],
                    "context": parent_context.get("context", {}),
                    "stage": parent_context["branch"]["stage"],
                    "open_contracts": list(parent_context["graph"].get("obligations", ())),
                    "lifetime_authority": {
                        "effects": list(parent_context["graph"].get("effects", ())),
                        "protocols": list(parent_context["graph"].get("protocols", ())),
                    },
                },
                search_history=history,
                grammar_state=dict(parent_context.get("grammar", {})),
                depth=int(parent_context["branch"]["depth"]),
                canonical_state_hash=str(parent_state_hash) if parent_state_hash is not None else None,
                frontier=tuple(options),
                oracle_chosen_branch_id=oracle.branch_id,
                evidence_limitations=tuple(
                    [
                        *(("rc24_missing_canonical_state_hash",) if not has_canonical_hashes else ()),
                        *(("no_retained_terminal_examples_in_source",) if not has_retained_terminal else ()),
                        "oracle_choice_derived_post_search_not_historical_bfs_choice",
                        "estimated_expansion_cost_unavailable",
                    ]
                ),
            )
        )
    return tuple(sorted(decisions, key=lambda item: (item.project, item.root_id, item.search_id, item.decision_id)))


def decision_bundle(decisions: Iterable[SearchDecision], *, source_schema: str) -> dict[str, Any]:
    values = tuple(decisions)
    payload = {
        "schema_version": FRONTIER_TRAINING_VERSION,
        "source_schema": source_schema,
        "decisions": [item.to_dict() for item in values],
    }
    return {**payload, "bundle_hash": canonical_hash(payload)}


def _complete_frontier(parent: Mapping[str, Any], siblings: list[Mapping[str, Any]]) -> bool:
    coverage = parent["supervision"]["branch"]["coverage"]
    return bool(
        coverage.get("children_status") == "exhaustive"
        and coverage.get("emitted_child_count") == len(siblings)
        and coverage.get("expected_child_count") == len(siblings)
    )


def _direct_cost(item: Mapping[str, Any]) -> dict[str, float | int | None]:
    raw = item["supervision"]["branch"]["search_cost"]
    return {
        "node_expansions": _number(raw.get("node_expansions"), default=1),
        "proof_calls": _number(raw.get("proof_calls"), default=0),
        "compiler_invocations": _number(raw.get("compiler_invocations"), default=0),
        "benchmark_runs": _number(raw.get("benchmark_runs"), default=0),
        "elapsed_ms": _number(raw.get("elapsed_ms"), default=None),
    }


def _number(value: Any, *, default: int | None) -> float | int | None:
    return default if value is None else value if isinstance(value, (int, float)) and math.isfinite(value) else default


def _sum_known(values: Iterable[float | int | None]) -> float | int | None:
    selected = [value for value in values if value is not None]
    return sum(selected) if selected else None


def _action_arity(action: Mapping[str, Any]) -> int:
    return max(
        1,
        len(action.get("primitives", ()))
        + len(action.get("numeric_parameters", ()))
        + len(action.get("categorical_parameters", ())),
    )


def _redundancy_class(item: Mapping[str, Any]) -> str:
    outcomes = {str(value.get("outcome")) for value in item["supervision"].get("observations", ())}
    state = str(item["supervision"]["branch"].get("state"))
    if state == "duplicate" or "duplicate" in outcomes:
        return "canonical-equivalent"
    if state == "compiler_identical" or "compiler_identical" in outcomes:
        return "compiler-identical"
    if "dominated_sound" in outcomes:
        return "dominated"
    if item["supervision"]["targets"]["descendant_utility"].get("useful") is False:
        return "exhausted-dead"
    return "unique"


def _oracle_order_key(item: FrontierActionRecord) -> tuple[Any, ...]:
    outcome = item.outcome
    distance = outcome.distance_to_useful if outcome.distance_to_useful is not None else 10**9
    work = outcome.subtree_cost.get("node_expansions")
    return (
        -int(outcome.contains_retained_descendant is True),
        -int(outcome.contains_useful_descendant is True),
        distance,
        work if isinstance(work, (int, float)) else 10**9,
        item.branch_id,
    )
