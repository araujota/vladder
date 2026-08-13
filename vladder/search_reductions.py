from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import time
import tracemalloc
from typing import Any, Callable, Iterable, Mapping

from .canonical_search import CanonicalSearchResult


REDUCTION_STUDY_VERSION = "canonical-reduction-studies-v1"


@dataclass(frozen=True)
class DescendantQualification:
    mechanism: str
    status: str
    authority: str
    left_terminal_count: int
    right_terminal_count: int
    missing_from_right: tuple[str, ...]
    extra_in_right: tuple[str, ...]
    counterexample: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def qualify_dominance(
    dominated: CanonicalSearchResult,
    proposed_dominator: CanonicalSearchResult,
) -> DescendantQualification:
    """Qualify B dominates A only when descendants(A) are a subset of descendants(B)."""

    left = set(dominated.terminal_canonical_hashes)
    right = set(proposed_dominator.terminal_canonical_hashes)
    missing = tuple(sorted(left - right))
    extra = tuple(sorted(right - left))
    return DescendantQualification(
        "dominance",
        "PASS" if not missing else "REJECTED",
        "descendant_terminal_set_inclusion" if not missing else "none",
        len(left),
        len(right),
        missing,
        extra,
        missing[0] if missing else None,
    )


def qualify_macro(
    expanded: CanonicalSearchResult,
    macro: CanonicalSearchResult,
) -> DescendantQualification:
    """A macro has deletion authority only under descendant terminal-set equality."""

    left = set(expanded.terminal_canonical_hashes)
    right = set(macro.terminal_canonical_hashes)
    missing = tuple(sorted(left - right))
    extra = tuple(sorted(right - left))
    return DescendantQualification(
        "macro_transaction",
        "PASS" if not missing and not extra else "REJECTED",
        "descendant_terminal_set_equality" if not missing and not extra else "none",
        len(left),
        len(right),
        missing,
        extra,
        (missing or extra or (None,))[0],
    )


Expression = Any
Rewrite = Callable[[Expression], Iterable[Expression]]


@dataclass(frozen=True)
class EGraphStudyResult:
    schema_version: str
    status: str
    input_expressions: int
    e_nodes: int
    e_classes: int
    unions: int
    saturation_rounds: int
    saturation_wall_ms: float
    extraction_wall_ms: float
    peak_memory_bytes: int
    extracted_representatives: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalEGraph:
    """Small exact e-class store for bounded pure-expression feasibility studies."""

    def __init__(self) -> None:
        self.parent: list[int] = []
        self.members: dict[int, set[str]] = {}
        self.expression_class: dict[str, int] = {}
        self.unions = 0

    def add(self, expression: Expression) -> int:
        encoded = _expression_key(expression)
        existing = self.expression_class.get(encoded)
        if existing is not None:
            return self.find(existing)
        index = len(self.parent)
        self.parent.append(index)
        self.members[index] = {encoded}
        self.expression_class[encoded] = index
        return index

    def find(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, left: int, right: int) -> int:
        left = self.find(left)
        right = self.find(right)
        if left == right:
            return left
        if len(self.members[left]) < len(self.members[right]):
            left, right = right, left
        self.parent[right] = left
        self.members[left].update(self.members.pop(right))
        for expression in self.members[left]:
            self.expression_class[expression] = left
        self.unions += 1
        return left

    def saturate(
        self,
        expressions: Iterable[Expression],
        rewrites: Iterable[Rewrite],
        *,
        maximum_rounds: int = 8,
        maximum_nodes: int = 10_000,
    ) -> EGraphStudyResult:
        tracemalloc.start()
        started = time.perf_counter()
        queue = [expression for expression in expressions]
        input_count = len(queue)
        for expression in queue:
            self.add(expression)
        rounds = 0
        changed = True
        while changed and rounds < maximum_rounds and len(self.expression_class) < maximum_nodes:
            changed = False
            rounds += 1
            snapshot = list(self.expression_class)
            for encoded in snapshot:
                expression = json.loads(encoded)
                source_class = self.add(expression)
                for rewrite in rewrites:
                    for candidate in rewrite(expression):
                        before = len(self.expression_class)
                        candidate_class = self.add(candidate)
                        self.union(source_class, candidate_class)
                        changed |= len(self.expression_class) != before
        saturation_ms = (time.perf_counter() - started) * 1000.0
        extraction_started = time.perf_counter()
        representatives = tuple(
            min(members, key=lambda item: (len(item), item))
            for _, members in sorted(self.members.items())
        )
        extraction_ms = (time.perf_counter() - extraction_started) * 1000.0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return EGraphStudyResult(
            "vladder-local-egraph-study-v1",
            "PASS" if len(self.expression_class) < maximum_nodes else "RESOURCE_LIMIT",
            input_count,
            len(self.expression_class),
            len(self.members),
            self.unions,
            rounds,
            saturation_ms,
            extraction_ms,
            peak,
            representatives,
        )


def commutative_rewrite(operators: Iterable[str]) -> Rewrite:
    admitted = frozenset(str(item) for item in operators)

    def rewrite(expression: Expression) -> Iterable[Expression]:
        if not isinstance(expression, Mapping):
            return ()
        op = str(expression.get("op", ""))
        args = expression.get("args", ())
        if op not in admitted or not isinstance(args, list) or len(args) != 2:
            return ()
        return ({"op": op, "args": [args[1], args[0]]},)

    return rewrite


def _expression_key(expression: Expression) -> str:
    return json.dumps(expression, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
