#!/usr/bin/env python3
"""Train, evaluate, or serve vLadder's conservative branch-survival oracle.

The model predicts whether a useful descendant may exist below one lazy search state. It never
predicts performance and never supplies legality or proof authority. Training consumes only v3
lineage bundles; serving implements ``vladder-lazy-oracle-protocol-v1`` and fails open.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    import torch
    from torch import nn
    import torch.nn.functional as F
    from torch.utils.data import DataLoader
except ImportError as error:  # pragma: no cover - exercised only without the optional extra
    raise SystemExit("search-pruner requires `pip install 'vladder[ml]'`") from error

from vladder.model_training_data import graph_learning_examples
from vladder.training_privacy import sanitize_decision_context, sanitize_graph, sanitize_training_action


SCHEMA = "vladder-search-pruner-model-v3"
STAGES = ("grammar", "candidate", "composition")
POSITIVE = "KEEP"
NEGATIVE = "PRUNE_HIGH_CONFIDENCE"
FAILURE_CLASSES = (
    "useful",
    "inapplicable",
    "duplicate",
    "compiler_identical",
    "dominated",
    "proof_dead",
    "exhausted",
    "other",
)


@dataclass(frozen=True)
class Example:
    project: str
    root_id: str
    search_id: str
    branch_id: str
    parent_branch_id: str | None
    graph: dict[str, Any]
    stage: str
    depth: int
    baseline: bool
    action: dict[str, Any]
    lineage: tuple[dict[str, Any], ...]
    target: int | None
    policy_surface: bool
    focus_node_indices: tuple[int, ...] = ()
    context_quality: str = "root_only"
    state_features: dict[str, Any] | None = None
    semantic_delta: dict[str, Any] | None = None
    branch_state: str = "unknown"
    children_status: str = "unknown"
    emitted_child_count: int = 0
    expected_child_count: int = 0
    evidence_coverage: str = "none"
    node_expansions: float = 0.0
    proof_calls: float = 0.0
    compiler_invocations: float = 0.0
    positive_descendant_count: int = 0
    direct_utility: dict[str, Any] | None = None
    descendant_utility: dict[str, Any] | None = None
    observations: tuple[dict[str, Any], ...] = ()
    failure_class: str = "other"
    utility_severity: int = 0
    subtree_size: int = 1
    subtree_cost: float = 1.0
    useful_terminal_count: int = 0
    sibling_count: int = 1
    tree_complete: bool = False


@dataclass(frozen=True)
class ModelConfig:
    hidden: int = 384
    categorical: int = 64
    action_width: int = 128
    layers: int = 3
    dropout: float = 0.12
    trunk_width: int = 512
    latent_width: int = 384
    retrieval_width: int = 64


class Vocab:
    FIELDS = ("node_kind", "node_operation", "node_type", "edge_relation", "edge_ordering", "action")

    def __init__(self, values: dict[str, dict[str, int]]) -> None:
        self.values = values
        self.tensor_cache: dict[tuple[str, str, str], dict[str, torch.Tensor]] = {}

    @classmethod
    def build(cls, examples: Iterable[Example]) -> "Vocab":
        raw = {name: set() for name in cls.FIELDS}
        for example in examples:
            for node in example.graph.get("node_features", []):
                raw["node_kind"].add(str(node.get("kind", "Other")))
                raw["node_operation"].add(str(node.get("operation", "other")))
                raw["node_type"].add(str(node.get("type_class", "other")))
            for edge in example.graph.get("edge_features", []):
                raw["edge_relation"].add(str(edge.get("relation", "other")))
                raw["edge_ordering"].add(str(edge.get("ordering", "other")))
            raw["action"].update(action_tokens(example.action, current=True))
            raw["action"].update(context_tokens(example))
            for item in example.lineage:
                raw["action"].update(action_tokens(item, current=False))
        return cls(
            {name: {token: index + 1 for index, token in enumerate(sorted(tokens))} for name, tokens in raw.items()}
        )

    def index(self, field: str, value: str) -> tuple[int, bool]:
        result = self.values[field].get(value, 0)
        return result, result == 0

    def to_dict(self) -> dict[str, dict[str, int]]:
        return self.values


def action_tokens(action: dict[str, Any], *, current: bool) -> tuple[str, ...]:
    prefix = "current" if current else "ancestor"
    result = [
        f"{prefix}.family={action.get('family', 'other')}",
        f"{prefix}.version={action.get('family_version', 'unversioned')}",
    ]
    result.extend(f"{prefix}.primitive={item}" for item in action.get("primitives", []))
    for item in action.get("categorical_parameters", []):
        if item.get("name") == "decision_surface":
            continue
        result.append(f"{prefix}.cat.{item.get('name')}={item.get('value')}")
    for item in action.get("numeric_parameters", []):
        value = float(item.get("value", 0.0))
        bucket = 0 if value == 0 else int(math.copysign(min(16, math.floor(math.log2(abs(value))) + 1), value))
        result.append(f"{prefix}.num.{item.get('name')}={bucket}")
    return tuple(result)


def context_tokens(example: Example) -> tuple[str, ...]:
    result = [f"context.quality={example.context_quality}"]
    for prefix, features in (
        ("state", example.state_features or {}),
        ("delta", example.semantic_delta or {}),
    ):
        for item in features.get("categorical", ()):
            result.append(f"context.{prefix}.{item.get('name')}={item.get('value')}")
    return tuple(result)


def stage_group(value: str) -> str:
    if value == "grammar_family":
        return "grammar"
    if value in {"composition", "cross_tu"}:
        return "composition"
    return "candidate"


def _model_lineage(path: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    # The synthetic baseline is not presented to the live lazy oracle. Grammar-family actions are
    # real lazy decisions in source-family-dispatch traces and must remain in the lineage.
    return tuple(dict(item["action"]) for item in path[:-1] if not item["action"].get("family") == "baseline")


def _categorical_parameter(action: dict[str, Any], name: str) -> str | None:
    return next(
        (str(item.get("value")) for item in action.get("categorical_parameters", ()) if item.get("name") == name),
        None,
    )


def _numeric_cost(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _utility_severity(utility: dict[str, Any]) -> int:
    if utility.get("promoted"):
        return 5
    if utility.get("retained"):
        return 4
    if utility.get("physically_material"):
        return 3
    if utility.get("proof_valid") and utility.get("distinct_realization"):
        return 2
    if utility.get("proof_valid") or utility.get("distinct_realization") or utility.get("useful"):
        return 1
    return 0


def _failure_class(
    *,
    target: int | None,
    state: str,
    children_status: str,
    observations: tuple[dict[str, Any], ...],
) -> str:
    if target == 1:
        return "useful"
    outcomes = {str(item.get("outcome", "")) for item in observations}
    joined = " ".join(sorted(outcomes | {state, children_status})).lower()
    if "proof_failed" in outcomes or "counterexample" in joined or "invalid" in joined:
        return "proof_dead"
    if "compiler_identical" in joined or "assembly_identical" in joined:
        return "compiler_identical"
    if "duplicate" in joined or "canonical" in joined:
        return "duplicate"
    if "dominated" in joined:
        return "dominated"
    if children_status in {"not_applicable", "contract_blocked"} and not observations:
        return "inapplicable"
    if state in {"terminal", "exhausted"} or children_status in {"exhaustive", "not_applicable"}:
        return "exhausted"
    return "other"


def load_examples(progress_path: Path, manifest_path: Path) -> list[Example]:
    progress = json.loads(progress_path.read_text())
    if not progress.get("complete") or progress.get("record_count") != progress.get("expected_record_count"):
        raise ValueError("training campaign is incomplete")
    manifest = json.loads(manifest_path.read_text())
    project_by_identifier = {str(item["id"]): str(item["project_id"]) for item in manifest["roots"]}
    result: list[Example] = []
    for record in progress["records"]:
        project = project_by_identifier[str(record["identifier"])]
        bundle_paths = record.get("bundles") or ([record["bundle"]] if record.get("bundle") else [])
        for bundle_path in bundle_paths:
            # The campaign progress gate admits only complete, previously audited v3 packets. Repeating
            # full JSON Schema validation for every compact search fragment dominates model iteration.
            for item in graph_learning_examples(Path(bundle_path), validate=False):
                branch = item["decision_context"]["branch"]
                context = item["decision_context"].get("context", {})
                supervision = item["supervision"]
                targets = supervision["targets"]
                branch_supervision = supervision["branch"]
                survival_record = targets["survival"]
                survival = survival_record["class"]
                baseline = bool(branch["baseline"])
                decision_surface = _categorical_parameter(branch["action"], "decision_surface")
                model_eligible = (
                    not baseline
                    and decision_surface not in {"deterministic", "canonicalized", "synthetic_wrapper"}
                    and survival != "BLOCKED_BY_CONTRACT"
                )
                target = (
                    (1 if survival == POSITIVE else 0 if survival == NEGATIVE else None) if model_eligible else None
                )
                coverage = branch_supervision.get("coverage", {})
                costs = branch_supervision.get("search_cost", {})
                observations = tuple(dict(value) for value in supervision.get("observations", ()))
                parent_branch_id = item.get("parent_branch_id")
                fragment = supervision.get("search", {}).get("fragment", {})
                if parent_branch_id is None and fragment.get("external_parent_branch_id"):
                    parent_branch_id = str(fragment["external_parent_branch_id"])
                direct_utility = dict(targets.get("direct_utility", {}))
                descendant_utility = dict(targets.get("descendant_utility", {}))
                state = str(branch_supervision.get("state", "unknown"))
                children_status = str(coverage.get("children_status", "unknown"))
                result.append(
                    Example(
                        project=project,
                        root_id=str(item["root_id"]),
                        search_id=str(item["search_id"]),
                        branch_id=str(item["branch_id"]),
                        parent_branch_id=str(parent_branch_id) if parent_branch_id else None,
                        graph=dict(item["decision_context"]["graph"]),
                        stage=stage_group(str(branch["stage"])),
                        depth=int(branch["depth"]),
                        baseline=baseline,
                        action=dict(branch["action"]),
                        lineage=_model_lineage(branch["ancestor_action_path"]),
                        target=target,
                        policy_surface=model_eligible,
                        focus_node_indices=tuple(int(index) for index in context.get("focus_node_indices", ())),
                        context_quality=str(context.get("quality", "root_only")),
                        state_features=dict(context.get("state_features", {})),
                        semantic_delta=dict(context.get("semantic_delta", {})),
                        branch_state=state,
                        children_status=children_status,
                        emitted_child_count=int(coverage.get("emitted_child_count", 0) or 0),
                        expected_child_count=int(coverage.get("expected_child_count", 0) or 0),
                        evidence_coverage=str(branch_supervision.get("evidence_coverage", "none")),
                        node_expansions=_numeric_cost(costs.get("node_expansions")),
                        proof_calls=_numeric_cost(costs.get("proof_calls")),
                        compiler_invocations=_numeric_cost(costs.get("compiler_invocations")),
                        positive_descendant_count=int(survival_record.get("positive_descendant_count", 0) or 0),
                        direct_utility=direct_utility,
                        descendant_utility=descendant_utility,
                        observations=observations,
                        failure_class=_failure_class(
                            target=target,
                            state=state,
                            children_status=children_status,
                            observations=observations,
                        ),
                        utility_severity=max(
                            _utility_severity(direct_utility),
                            _utility_severity(descendant_utility),
                        ),
                    )
                )
    return result


def load_campaign_examples(progress_paths: list[Path], manifest_paths: list[Path]) -> list[Example]:
    if len(progress_paths) != len(manifest_paths):
        raise ValueError("each --progress requires one corresponding --manifest")
    result: list[Example] = []
    seen: dict[tuple[str, str, str], Example] = {}
    positions: dict[tuple[str, str, str], int] = {}
    for progress, manifest in zip(progress_paths, manifest_paths, strict=True):
        for example in load_examples(progress, manifest):
            key = (example.project, example.root_id, example.branch_id)
            previous = seen.get(key)
            if key in seen:
                if previous is not None and previous.target != example.target:
                    raise ValueError(f"conflicting supervision for repeated branch {key}")
                if previous is not None and previous.parent_branch_id is None and example.parent_branch_id:
                    replacement = replace(previous, parent_branch_id=example.parent_branch_id)
                    seen[key] = replacement
                    result[positions[key]] = replacement
                continue
            seen[key] = example
            positions[key] = len(result)
            result.append(example)
    return derive_search_forest(result)


def derive_search_forest(examples: list[Example]) -> list[Example]:
    """Derive post-search supervision without adding any inference-time feature leakage."""
    by_root: dict[tuple[str, str], list[Example]] = defaultdict(list)
    for example in examples:
        by_root[(example.project, example.root_id)].append(example)

    derived: dict[tuple[str, str, str], Example] = {}
    for root_examples in by_root.values():
        by_id = {item.branch_id: item for item in root_examples}
        children: dict[str, list[str]] = defaultdict(list)
        for item in root_examples:
            if item.parent_branch_id in by_id:
                children[item.parent_branch_id].append(item.branch_id)

        visiting: set[str] = set()
        memo: dict[str, tuple[int, float, int, int]] = {}

        def summarize(branch_id: str) -> tuple[int, float, int, int]:
            if branch_id in memo:
                return memo[branch_id]
            if branch_id in visiting:
                return 1, 1.0, 0, 0
            visiting.add(branch_id)
            item = by_id[branch_id]
            size = 1
            own_cost = 1.0 + item.node_expansions + item.proof_calls + item.compiler_invocations
            cost = own_cost
            useful_terminals = int(item.target == 1 and not children.get(branch_id))
            severity = _utility_severity(item.direct_utility or {})
            for child in children.get(branch_id, ()):
                child_size, child_cost, child_useful, child_severity = summarize(child)
                size += child_size
                cost += child_cost
                useful_terminals += child_useful
                severity = max(severity, child_severity)
            visiting.remove(branch_id)
            memo[branch_id] = size, cost, useful_terminals, severity
            return memo[branch_id]

        for item in root_examples:
            size, cost, useful_terminals, severity = summarize(item.branch_id)
            actual_children = len(children.get(item.branch_id, ()))
            tree_complete = item.children_status in {"exhaustive", "not_applicable"} and (
                item.expected_child_count == item.emitted_child_count or item.expected_child_count == actual_children
            )
            value = replace(
                item,
                subtree_size=size,
                subtree_cost=cost,
                useful_terminal_count=max(useful_terminals, item.positive_descendant_count),
                utility_severity=max(item.utility_severity, severity),
                sibling_count=max(1, len(children.get(item.parent_branch_id or "", ()))),
                tree_complete=tree_complete,
            )
            derived[(item.project, item.root_id, item.branch_id)] = value
    return [derived[(item.project, item.root_id, item.branch_id)] for item in examples]


def _feature(items: list[dict[str, Any]], name: str, default: float = 0.0) -> float:
    for item in items:
        if item.get("name") == name:
            try:
                return float(item.get("value", default))
            except (TypeError, ValueError):
                return default
    return default


def _largest_scc(node_count: int, edge_index: list[list[int]]) -> int:
    adjacency = [[] for _ in range(node_count)]
    for source, destination in zip(*edge_index, strict=False):
        if 0 <= source < node_count and 0 <= destination < node_count:
            adjacency[source].append(destination)
    index = 0
    stack: list[int] = []
    on_stack: set[int] = set()
    indices = [-1] * node_count
    low = [0] * node_count
    largest = 0

    def visit(node: int) -> None:
        nonlocal index, largest
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for successor in adjacency[node]:
            if indices[successor] < 0:
                visit(successor)
                low[node] = min(low[node], low[successor])
            elif successor in on_stack:
                low[node] = min(low[node], indices[successor])
        if low[node] == indices[node]:
            size = 0
            while stack:
                member = stack.pop()
                on_stack.remove(member)
                size += 1
                if member == node:
                    break
            largest = max(largest, size)

    for node in range(node_count):
        if indices[node] < 0:
            visit(node)
    return largest


def _graph_summary(example: Example, node_count: int, edge_count: int) -> list[float]:
    nodes = example.graph.get("node_features", [])
    edges = example.graph.get("edge_features", [])
    kinds = Counter(str(node.get("kind", "Other")).lower() for node in nodes)
    operations = Counter(str(node.get("operation", "other")).lower() for node in nodes)
    alias_markers = 0
    lifetime_boundaries = 0
    for edge in edges:
        for feature in edge.get("categorical_features", ()):
            name = str(feature.get("name", "")).lower()
            value = str(feature.get("value", "other")).lower()
            alias_markers += int("alias" in name and value not in {"none", "no", "other"})
            lifetime_boundaries += int(name == "lifetime" and value not in {"other", "expression"})
    largest_scc = _largest_scc(node_count, example.graph.get("edge_index", [[], []]))
    focus_fraction = len(example.focus_node_indices) / max(node_count, 1)
    return [
        math.log1p(node_count),
        math.log1p(edge_count),
        math.log1p(len(example.graph.get("obligations", []))),
        math.log1p(len(example.graph.get("effects", []))),
        math.log1p(len(example.graph.get("protocols", []))),
        math.log1p(len(example.graph.get("claims", []))),
        math.log1p(largest_scc),
        math.log1p(kinds["loop"] + operations["loop"]),
        math.log1p(kinds["call"] + kinds["helpersummary"] + operations["call"]),
        math.log1p(kinds["mutation"] + kinds["statewrite"] + operations["state_write"]),
        math.log1p(kinds["barrier"] + kinds["unsupportedoperation"] + operations["barrier"]),
        math.log1p(operations["load"] + operations["store"]),
        math.log1p(alias_markers),
        math.log1p(lifetime_boundaries),
        focus_fraction,
        math.log1p(sum(len(node.get("numeric_features", ())) for node in nodes)),
    ]


def tensorize(example: Example, vocab: Vocab) -> dict[str, torch.Tensor]:
    unknown_action = False
    node_cat = []
    node_num = []
    for node in example.graph.get("node_features", []):
        values = []
        for field, value in (
            ("node_kind", str(node.get("kind", "Other"))),
            ("node_operation", str(node.get("operation", "other"))),
            ("node_type", str(node.get("type_class", "other"))),
        ):
            index, _ = vocab.index(field, value)
            values.append(index)
        width = float(node.get("bit_width") or 0.0)
        lanes = float(node.get("vector_lanes") or 0.0)
        node_cat.append(values)
        node_num.append(
            [
                math.log1p(width),
                math.log1p(lanes),
                len(node.get("numeric_features", [])),
                len(node.get("categorical_features", [])),
            ]
        )
    if not node_cat:
        node_cat = [[0, 0, 0]]
        node_num = [[0.0, 0.0, 0.0, 0.0]]
        unknown_action = True
    edge_index = example.graph.get("edge_index", [[], []])
    edge_cat = []
    for edge in example.graph.get("edge_features", []):
        relation, _ = vocab.index("edge_relation", str(edge.get("relation", "other")))
        ordering, _ = vocab.index("edge_ordering", str(edge.get("ordering", "other")))
        edge_cat.append([relation, ordering])
    if not edge_cat:
        edge_cat = [[0, 0]]
        edge_index = [[0], [0]]

    current_tokens = (*action_tokens(example.action, current=True), *context_tokens(example))
    lineage_tokens = tuple(token for action in example.lineage for token in action_tokens(action, current=False))
    parent_tokens = action_tokens(example.lineage[-1], current=False) if example.lineage else ()
    current_indices = []
    for token in current_tokens:
        index, missing = vocab.index("action", token)
        current_indices.append(index)
        unknown_action |= missing
    lineage_indices = []
    for token in lineage_tokens:
        index, missing = vocab.index("action", token)
        lineage_indices.append(index)
        unknown_action |= missing
    if not current_indices:
        current_indices = [0]
        unknown_action = True
    if not lineage_indices:
        lineage_indices = [0]
    parent_indices = []
    for token in parent_tokens:
        index, missing = vocab.index("action", token)
        parent_indices.append(index)
        unknown_action |= missing
    if not parent_indices:
        parent_indices = [0]
    graph_num = _graph_summary(example, len(node_cat), len(edge_cat))
    focus = sorted({index for index in example.focus_node_indices if 0 <= index < len(node_cat)})
    if not focus:
        focus = list(range(len(node_cat)))
    state_num = [
        _feature((example.state_features or {}).get("numeric", []), name)
        for name in ("depth", "selected_count", "remaining_count", "action_count", "region_count")
    ] + [_feature((example.semantic_delta or {}).get("numeric", []), name) for name in ("factor", "width", "tile")]
    selected = state_num[1]
    remaining = state_num[2]
    action = example.action
    branch_num = [
        math.log1p(example.depth),
        float(example.baseline),
        math.log1p(len(action.get("primitives", ()))),
        math.log1p(len(action.get("numeric_parameters", ()))),
        math.log1p(len(action.get("categorical_parameters", ()))),
        selected / max(selected + remaining, 1.0),
    ]
    return {
        "node_cat": torch.tensor(node_cat, dtype=torch.long),
        "node_num": torch.tensor(node_num, dtype=torch.float32),
        "edge_index": torch.tensor(edge_index, dtype=torch.long),
        "edge_cat": torch.tensor(edge_cat, dtype=torch.long),
        "action": torch.tensor(current_indices, dtype=torch.long),
        "lineage": torch.tensor(lineage_indices, dtype=torch.long),
        "parent": torch.tensor(parent_indices, dtype=torch.long),
        "focus": torch.tensor(focus, dtype=torch.long),
        "graph_num": torch.tensor(graph_num, dtype=torch.float32),
        "state_num": torch.tensor(state_num, dtype=torch.float32),
        "branch_num": torch.tensor(branch_num, dtype=torch.float32),
        "stage": torch.tensor(STAGES.index(example.stage), dtype=torch.long),
        "target": torch.tensor(float(example.target or 0), dtype=torch.float32),
        "labeled": torch.tensor(example.target is not None, dtype=torch.bool),
        "unknown": torch.tensor(unknown_action, dtype=torch.bool),
        "cost_target": torch.tensor(math.log1p(example.subtree_cost), dtype=torch.float32),
        "severity_target": torch.tensor(example.utility_severity, dtype=torch.long),
        "failure_target": torch.tensor(FAILURE_CLASSES.index(example.failure_class), dtype=torch.long),
    }


def collate(items: list[tuple[Example, dict[str, torch.Tensor]]]) -> tuple[list[Example], dict[str, torch.Tensor]]:
    examples = [item[0] for item in items]
    tensors = [item[1] for item in items]
    node_cat = []
    node_num = []
    edge_index = []
    edge_cat = []
    batch = []
    offset = 0
    action = []
    action_batch = []
    lineage = []
    lineage_batch = []
    parent = []
    parent_batch = []
    focus = []
    focus_batch = []
    for index, item in enumerate(tensors):
        count = item["node_cat"].shape[0]
        node_cat.append(item["node_cat"])
        node_num.append(item["node_num"])
        edge_index.append(item["edge_index"] + offset)
        edge_cat.append(item["edge_cat"])
        batch.append(torch.full((count,), index, dtype=torch.long))
        offset += count
        action.append(item["action"])
        action_batch.append(torch.full((item["action"].numel(),), index, dtype=torch.long))
        lineage.append(item["lineage"])
        lineage_batch.append(torch.full((item["lineage"].numel(),), index, dtype=torch.long))
        parent.append(item["parent"])
        parent_batch.append(torch.full((item["parent"].numel(),), index, dtype=torch.long))
        focus.append(item["focus"] + offset - count)
        focus_batch.append(torch.full((item["focus"].numel(),), index, dtype=torch.long))
    return examples, {
        "node_cat": torch.cat(node_cat),
        "node_num": torch.cat(node_num),
        "edge_index": torch.cat(edge_index, 1),
        "edge_cat": torch.cat(edge_cat),
        "batch": torch.cat(batch),
        "action": torch.cat(action),
        "action_batch": torch.cat(action_batch),
        "lineage": torch.cat(lineage),
        "lineage_batch": torch.cat(lineage_batch),
        "parent": torch.cat(parent),
        "parent_batch": torch.cat(parent_batch),
        "focus": torch.cat(focus),
        "focus_batch": torch.cat(focus_batch),
        "graph_num": torch.stack([x["graph_num"] for x in tensors]),
        "state_num": torch.stack([x["state_num"] for x in tensors]),
        "branch_num": torch.stack([x["branch_num"] for x in tensors]),
        "stage": torch.stack([x["stage"] for x in tensors]),
        "target": torch.stack([x["target"] for x in tensors]),
        "labeled": torch.stack([x["labeled"] for x in tensors]),
        "unknown": torch.stack([x["unknown"] for x in tensors]),
        "cost_target": torch.stack([x["cost_target"] for x in tensors]),
        "severity_target": torch.stack([x["severity_target"] for x in tensors]),
        "failure_target": torch.stack([x["failure_target"] for x in tensors]),
    }


class MessageLayer(nn.Module):
    def __init__(self, hidden: int, dropout: float) -> None:
        super().__init__()
        self.mlp = nn.Sequential(nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(dropout), nn.Linear(hidden, hidden))
        self.norm = nn.LayerNorm(hidden)

    def forward(self, node, edge_index, edge):
        source, destination = edge_index
        aggregate = torch.zeros_like(node)
        aggregate.index_add_(0, destination, node[source] + edge)
        degree = torch.zeros(node.shape[0], device=node.device, dtype=node.dtype)
        degree.index_add_(0, destination, torch.ones(source.shape[0], device=node.device, dtype=node.dtype))
        return self.norm(node + self.mlp(node + aggregate / degree.clamp_min(1).unsqueeze(1)))


class SurvivalModel(nn.Module):
    def __init__(self, vocab: Vocab, config: ModelConfig) -> None:
        super().__init__()
        h = config.hidden
        c = config.categorical
        a = config.action_width
        self.config = config
        self.node_kind = nn.Embedding(len(vocab.values["node_kind"]) + 1, c)
        self.node_operation = nn.Embedding(len(vocab.values["node_operation"]) + 1, c)
        self.node_type = nn.Embedding(len(vocab.values["node_type"]) + 1, c)
        self.node_in = nn.Linear(c * 3 + 4, h)
        self.edge_relation = nn.Embedding(len(vocab.values["edge_relation"]) + 1, c)
        self.edge_ordering = nn.Embedding(len(vocab.values["edge_ordering"]) + 1, c)
        self.edge_in = nn.Linear(c * 2, h)
        self.layers = nn.ModuleList(MessageLayer(h, config.dropout) for _ in range(config.layers))
        self.action_embedding = nn.Embedding(len(vocab.values["action"]) + 1, a)
        self.action_projection = nn.Linear(a, h)
        self.lineage_projection = nn.Linear(a, h)
        self.parent_projection = nn.Linear(a, h)
        self.stage_embedding = nn.Embedding(len(STAGES), 32)
        self.trunk = nn.Sequential(
            nn.Linear(h * 7 + 62, config.trunk_width),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.trunk_width, config.latent_width),
            nn.GELU(),
            nn.Dropout(config.dropout),
        )
        head_width = max(96, config.latent_width // 3)
        self.heads = nn.ModuleList(
            nn.Sequential(nn.Linear(config.latent_width, head_width), nn.GELU(), nn.Linear(head_width, 1))
            for _ in STAGES
        )
        self.cost_head = nn.Sequential(nn.Linear(config.latent_width, head_width), nn.GELU(), nn.Linear(head_width, 1))
        self.severity_head = nn.Sequential(
            nn.Linear(config.latent_width, head_width), nn.GELU(), nn.Linear(head_width, 6)
        )
        self.failure_head = nn.Sequential(
            nn.Linear(config.latent_width, head_width), nn.GELU(), nn.Linear(head_width, len(FAILURE_CLASSES))
        )
        self.retrieval_projection = nn.Linear(config.latent_width, config.retrieval_width)

    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters())

    @staticmethod
    def pool(values, batch, count):
        mean = torch.zeros(count, values.shape[1], device=values.device)
        mean.index_add_(0, batch, values)
        sizes = torch.bincount(batch, minlength=count).clamp_min(1).unsqueeze(1)
        mean = mean / sizes
        maximum = torch.full_like(mean, -torch.inf)
        maximum.scatter_reduce_(0, batch[:, None].expand_as(values), values, reduce="amax", include_self=True)
        return mean, maximum

    def forward(self, b):
        cat = b["node_cat"]
        node = F.gelu(
            self.node_in(
                torch.cat(
                    [
                        self.node_kind(cat[:, 0]),
                        self.node_operation(cat[:, 1]),
                        self.node_type(cat[:, 2]),
                        b["node_num"],
                    ],
                    1,
                )
            )
        )
        edge_cat = b["edge_cat"]
        edge = F.gelu(
            self.edge_in(torch.cat([self.edge_relation(edge_cat[:, 0]), self.edge_ordering(edge_cat[:, 1])], 1))
        )
        for layer in self.layers:
            node = layer(node, b["edge_index"], edge)
        count = b["graph_num"].shape[0]
        mean, maximum = self.pool(node, b["batch"], count)
        focus_mean, focus_maximum = self.pool(node[b["focus"]], b["focus_batch"], count)
        action_mean, _ = self.pool(self.action_embedding(b["action"]), b["action_batch"], count)
        lineage_mean, _ = self.pool(self.action_embedding(b["lineage"]), b["lineage_batch"], count)
        parent_mean, _ = self.pool(self.action_embedding(b["parent"]), b["parent_batch"], count)
        shared = self.trunk(
            torch.cat(
                [
                    mean,
                    maximum,
                    focus_mean,
                    focus_maximum,
                    F.gelu(self.action_projection(action_mean)),
                    F.gelu(self.parent_projection(parent_mean)),
                    F.gelu(self.lineage_projection(lineage_mean)),
                    b["graph_num"],
                    b["state_num"],
                    b["branch_num"],
                    self.stage_embedding(b["stage"]),
                ],
                1,
            )
        )
        logits = torch.cat([head(shared) for head in self.heads], 1)
        return {
            "logit": logits.gather(1, b["stage"][:, None]).squeeze(1),
            "all_logits": logits,
            "cost": self.cost_head(shared).squeeze(1),
            "severity": self.severity_head(shared),
            "failure": self.failure_head(shared),
            "embedding": F.normalize(self.retrieval_projection(shared), dim=1),
        }


def loader(examples: list[Example], vocab: Vocab, batch_size: int, shuffle: bool):
    values = []
    for item in examples:
        key = (item.project, item.root_id, item.branch_id)
        tensors = vocab.tensor_cache.get(key)
        if tensors is None:
            tensors = tensorize(item, vocab)
            vocab.tensor_cache[key] = tensors
        values.append((item, tensors))
    return DataLoader(values, batch_size=batch_size, shuffle=shuffle, collate_fn=collate)


def move(batch, device):
    return {name: value.to(device) for name, value in batch.items()}


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def root_partition(examples: list[Example], *, heldout: str | None = None):
    eligible = [item for item in examples if heldout is None or item.project != heldout]
    roots = sorted({item.root_id for item in eligible})
    calibration = {root for root in roots if int(hashlib.sha256(root.encode()).hexdigest()[:8], 16) % 5 == 0}
    if not calibration and roots:
        calibration = {roots[-1]}
    return [x for x in eligible if x.root_id not in calibration], [x for x in eligible if x.root_id in calibration]


def semantic_root_weights(examples: list[Example]) -> dict[tuple[str, str, str], float]:
    """Give every project equal mass and every semantic root equal mass within its project."""
    labeled = [item for item in examples if item.target is not None]
    roots_by_project = {
        project: {item.root_id for item in labeled if item.project == project}
        for project in {item.project for item in labeled}
    }
    branches_by_root = {
        (project, root): sum(item.project == project and item.root_id == root for item in labeled)
        for project, root in {(item.project, item.root_id) for item in labeled}
    }
    raw = {
        (item.project, item.root_id, item.branch_id): (
            1.0 / max(len(roots_by_project[item.project]), 1) / max(branches_by_root[(item.project, item.root_id)], 1)
        )
        for item in labeled
    }
    mean = sum(raw.values()) / max(len(raw), 1)
    return {branch: value / max(mean, 1e-12) for branch, value in raw.items()}


def cluster_signature(example: Example) -> str:
    """Coarse pre-decision signature used only to cap redundant negative training examples."""
    payload = {
        "stage": example.stage,
        "family": example.action.get("family", "other"),
        "primitives": sorted(example.action.get("primitives", ())),
        "context": context_tokens(example),
        "node_kinds": sorted(
            Counter(str(node.get("kind", "Other")) for node in example.graph.get("node_features", ())).items()
        ),
        "edge_relations": sorted(
            Counter(str(edge.get("relation", "other")) for edge in example.graph.get("edge_features", ())).items()
        ),
        "depth": example.depth,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def decision_signature(example: Example) -> str:
    """Exact pre-decision identity for conservative historical lookup."""
    payload = {
        "stage": example.stage,
        "depth": example.depth,
        "graph": example.graph,
        "action": example.action,
        "lineage": example.lineage,
        "context_quality": example.context_quality,
        "state_features": example.state_features,
        "semantic_delta": example.semantic_delta,
        "focus_node_indices": example.focus_node_indices,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def balanced_stage_examples(examples: list[Example], stage: str, args, seed: int) -> list[Example]:
    rng = random.Random(seed)
    stage_examples = [item for item in examples if item.target is not None and item.stage == stage]
    positives = [item for item in stage_examples if item.target == 1]
    negative_clusters: dict[str, list[Example]] = defaultdict(list)
    for item in stage_examples:
        if item.target == 0:
            negative_clusters[cluster_signature(item)].append(item)
    negatives: list[Example] = []
    for cluster in negative_clusters.values():
        rng.shuffle(cluster)
        negatives.extend(cluster[: args.negative_cluster_cap])
    rng.shuffle(negatives)
    limit = max(len(positives), int(len(positives) * args.negative_positive_ratio))
    negatives = negatives[:limit]
    result = positives + negatives
    rng.shuffle(result)
    return result


def sibling_pairs(examples: list[Example], stage: str, limit: int, seed: int) -> list[tuple[Example, Example]]:
    groups: dict[tuple[str, str, str | None], list[Example]] = defaultdict(list)
    for item in examples:
        if item.target is not None and item.stage == stage:
            groups[(item.project, item.root_id, item.parent_branch_id)].append(item)
    pairs = [
        (positive, negative)
        for siblings in groups.values()
        for positive in siblings
        if positive.target == 1
        for negative in siblings
        if negative.target == 0
    ]
    rng = random.Random(seed)
    rng.shuffle(pairs)
    return pairs[:limit]


def asymmetric_focal_loss(logits, targets, positive_weight: float, gamma: float, margin: float):
    adjusted = logits - margin * targets
    probability = torch.sigmoid(adjusted)
    focal = torch.where(targets > 0, (1.0 - probability).pow(gamma), probability.pow(gamma))
    class_weight = torch.where(targets > 0, torch.full_like(targets, positive_weight), torch.ones_like(targets))
    return F.binary_cross_entropy_with_logits(adjusted, targets, reduction="none") * focal * class_weight


def _calibration_objective(rows: list[dict[str, Any]], recall_target: float) -> dict[str, float]:
    labeled = [row for row in rows if row["example"].target is not None]
    positives = sum(row["example"].target == 1 for row in labeled)
    allowed = math.floor((1.0 - recall_target) * positives + 1e-12)
    ordered = sorted(labeled, key=lambda row: row["probability"])
    misses = 0
    avoided = 0.0
    threshold = -1.0
    for row in ordered:
        target = int(row["example"].target or 0)
        if misses + target > allowed:
            break
        misses += target
        avoided += row["example"].subtree_cost
        threshold = row["probability"]
    total = sum(row["example"].subtree_cost for row in labeled)
    decisions = {
        (row["example"].project, row["example"].root_id, row["example"].branch_id): {
            "prune": row["probability"] <= threshold
        }
        for row in rows
        if row["example"].policy_surface
    }
    replay = online_replay(rows, decisions) if decisions else {"online_work_reduction": 0.0}
    return {
        "score": replay["online_work_reduction"],
        "overlapping_subtree_cost_reduction": avoided / max(total, 1e-12),
        "threshold": threshold,
        "misses": misses,
        "recall": 1.0 - misses / max(positives, 1),
    }


def _train_epoch(model, optimizer, examples, vocab, args, device, sample_weights, stage: str | None):
    model.train()
    losses = []
    positive_weights = {
        "grammar": args.grammar_positive_weight,
        "candidate": args.candidate_positive_weight,
        "composition": args.composition_positive_weight,
    }
    for originals, batch in loader(examples, vocab, args.batch_size, True):
        batch = move(batch, device)
        mask = batch["labeled"]
        if stage is not None:
            mask &= batch["stage"] == STAGES.index(stage)
        if not mask.any():
            continue
        optimizer.zero_grad(set_to_none=True)
        output = model(batch)
        targets = batch["target"][mask]
        root_weight = torch.tensor(
            [sample_weights.get((item.project, item.root_id, item.branch_id), 0.0) for item in originals],
            device=device,
            dtype=targets.dtype,
        )[mask]
        subtree_weight = torch.tensor(
            [1.0 + args.subtree_weight * min(8.0, math.log1p(item.subtree_cost)) for item in originals],
            device=device,
            dtype=targets.dtype,
        )[mask]
        stage_weights = torch.tensor(
            [positive_weights[item.stage] for item in originals],
            device=device,
            dtype=targets.dtype,
        )[mask]
        survival = asymmetric_focal_loss(output["logit"][mask], targets, 1.0, args.focal_gamma, args.positive_margin)
        class_weight = torch.where(targets > 0, stage_weights, torch.ones_like(stage_weights))
        weight = root_weight * class_weight * torch.where(targets > 0, torch.ones_like(subtree_weight), subtree_weight)
        loss = (survival * weight).sum() / weight.sum().clamp_min(1e-12)
        cost_loss = F.smooth_l1_loss(output["cost"][mask], batch["cost_target"][mask])
        severity_loss = F.cross_entropy(output["severity"][mask], batch["severity_target"][mask])
        negative_mask = mask & (batch["target"] == 0)
        failure_loss = (
            F.cross_entropy(output["failure"][negative_mask], batch["failure_target"][negative_mask])
            if negative_mask.any()
            else torch.zeros((), device=device)
        )
        loss = loss + args.auxiliary_weight * (cost_loss + severity_loss + failure_loss)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 2.0)
        optimizer.step()
        losses.append(float(loss.detach()))
    return sum(losses) / max(len(losses), 1)


def _ranking_epoch(model, optimizer, pairs, vocab, args, device):
    if not pairs or args.ranking_weight <= 0:
        return 0.0
    model.train()
    losses = []
    for start in range(0, len(pairs), args.batch_size):
        chunk = pairs[start : start + args.batch_size]
        positives = [item[0] for item in chunk]
        negatives = [item[1] for item in chunk]
        _, positive_batch = next(iter(loader(positives, vocab, len(positives), False)))
        _, negative_batch = next(iter(loader(negatives, vocab, len(negatives), False)))
        optimizer.zero_grad(set_to_none=True)
        positive_logits = model(move(positive_batch, device))["logit"]
        negative_logits = model(move(negative_batch, device))["logit"]
        loss = args.ranking_weight * F.softplus(args.ranking_margin - positive_logits + negative_logits).mean()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 2.0)
        optimizer.step()
        losses.append(float(loss.detach()))
    return sum(losses) / max(len(losses), 1)


def fit(train, calibration, vocab, args, device, seed_offset: int = 0):
    seed_all(args.seed + seed_offset)
    config = ModelConfig(
        hidden=args.hidden,
        categorical=args.categorical,
        action_width=args.action_width,
        layers=args.layers,
        dropout=args.dropout,
        trunk_width=args.trunk_width,
        latent_width=args.latent_width,
        retrieval_width=args.retrieval_width,
    )
    model = SurvivalModel(vocab, config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    sample_weights = semantic_root_weights(train)
    history = []
    epoch_index = 0
    for stage in STAGES:
        for _ in range(args.stage_epochs):
            epoch_index += 1
            staged = balanced_stage_examples(train, stage, args, args.seed + seed_offset + epoch_index)
            loss = _train_epoch(model, optimizer, staged, vocab, args, device, sample_weights, stage)
            pairs = sibling_pairs(staged, stage, args.max_ranking_pairs, args.seed + seed_offset + epoch_index)
            ranking_loss = _ranking_epoch(model, optimizer, pairs, vocab, args, device)
            history.append(
                {"phase": f"pretrain_{stage}", "epoch": epoch_index, "train_loss": loss, "ranking_loss": ranking_loss}
            )

    if args.freeze_encoder_after_pretrain:
        trainable_prefixes = ("heads.", "cost_head.", "severity_head.", "failure_head.")
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(name.startswith(trainable_prefixes))
        optimizer = torch.optim.AdamW(
            (parameter for parameter in model.parameters() if parameter.requires_grad),
            lr=args.learning_rate,
            weight_decay=1e-4,
        )

    best = None
    best_score = -math.inf
    for joint_epoch in range(args.epochs):
        epoch_index += 1
        by_stage = {
            stage: balanced_stage_examples(train, stage, args, args.seed + seed_offset + epoch_index)
            for stage in STAGES
        }
        grammar_limit = max(
            1, int(max(len(by_stage["candidate"]), len(by_stage["composition"])) * args.grammar_joint_fraction)
        )
        joint = by_stage["grammar"][:grammar_limit] + by_stage["candidate"] + by_stage["composition"]
        random.Random(args.seed + seed_offset + epoch_index).shuffle(joint)
        loss = _train_epoch(model, optimizer, joint, vocab, args, device, sample_weights, None)
        pair_pool = []
        for stage in STAGES:
            pair_pool.extend(
                sibling_pairs(
                    by_stage[stage], stage, args.max_ranking_pairs // len(STAGES), args.seed + seed_offset + epoch_index
                )
            )
        ranking_loss = _ranking_epoch(model, optimizer, pair_pool, vocab, args, device)

        class Once:
            batch_size = args.batch_size
            mc_samples = 1

        calibration_rows = predict(model, calibration, vocab, Once(), device)
        objective = _calibration_objective(calibration_rows, args.recall_target)
        history.append(
            {
                "phase": "joint",
                "epoch": epoch_index,
                "train_loss": loss,
                "ranking_loss": ranking_loss,
                "calibration_objective": objective,
            }
        )
        if objective["score"] > best_score:
            best_score = objective["score"]
            best = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    if best is None:
        best = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    model.load_state_dict(best)

    if args.hard_epochs:

        class Once:
            batch_size = args.batch_size
            mc_samples = 1

        rows = predict(model, train, vocab, Once(), device)
        hard_positives = sorted(
            (row for row in rows if row["example"].target == 1), key=lambda row: row["probability"]
        )[: args.hard_examples]
        hard_negatives = sorted(
            (row for row in rows if row["example"].target == 0), key=lambda row: row["probability"], reverse=True
        )[: args.hard_examples]
        hard = [row["example"] for row in hard_positives + hard_negatives]
        for hard_epoch in range(args.hard_epochs):
            epoch_index += 1
            loss = _train_epoch(model, optimizer, hard, vocab, args, device, sample_weights, None)
            history.append(
                {
                    "phase": "hard_mining",
                    "epoch": epoch_index,
                    "train_loss": loss,
                    "hard_positives": len(hard_positives),
                    "hard_negatives": len(hard_negatives),
                }
            )
    return model, history


@torch.no_grad()
def predict(model, examples, vocab, args, device):
    models = list(model) if isinstance(model, (list, tuple)) else [model]
    rows = []
    for member in models:
        member.train()
    for originals, batch in loader(examples, vocab, args.batch_size, False):
        batch = move(batch, device)
        samples = []
        embedding_samples = []
        for member in models:
            for _ in range(args.mc_samples):
                output = member(batch)
                samples.append(torch.sigmoid(output["logit"]).cpu())
                embedding_samples.append(output["embedding"].cpu())
        values = torch.stack(samples)
        embeddings = torch.stack(embedding_samples).mean(0)
        for index, example in enumerate(originals):
            rows.append(
                {
                    "example": example,
                    "probability": float(values[:, index].mean()),
                    "uncertainty": float(values[:, index].std(unbiased=False)),
                    "member_min": float(values[:, index].min()),
                    "member_max": float(values[:, index].max()),
                    "embedding": embeddings[index].numpy(),
                    "unknown": bool(batch["unknown"][index].cpu()),
                    "signature": decision_signature(example),
                }
            )
    for member in models:
        member.eval()
    return rows


def _score(row: dict[str, Any], uncertainty_k: float) -> float:
    return row["probability"] + uncertainty_k * row["uncertainty"]


def _risk_threshold(
    rows: list[dict[str, Any]],
    recall_target: float,
    uncertainty_k: float,
    shrink_quantile: float,
) -> dict[str, Any]:
    labeled = [row for row in rows if row["example"].target is not None and not row["unknown"]]
    positives = sum(row["example"].target == 1 for row in labeled)
    allowed = math.floor((1.0 - recall_target) * positives + 1e-12)
    groups: list[tuple[float, list[dict[str, Any]]]] = []
    for row in sorted(labeled, key=lambda item: _score(item, uncertainty_k)):
        score = _score(row, uncertainty_k)
        if not groups or score != groups[-1][0]:
            groups.append((score, []))
        groups[-1][1].append(row)
    misses = 0
    accepted = []
    for score, group in groups:
        group_misses = sum(row["example"].target == 1 for row in group)
        if misses + group_misses > allowed:
            break
        misses += group_misses
        accepted.extend(group)
    threshold = (
        (groups[0][0] - 1.0) if not accepted and groups else (_score(accepted[-1], uncertainty_k) if accepted else -1.0)
    )
    if accepted and shrink_quantile < 1.0:
        threshold = min(
            threshold,
            float(np.quantile([_score(row, uncertainty_k) for row in accepted], shrink_quantile)),
        )
    return {
        "threshold": float(threshold),
        "positives": positives,
        "allowed_misses": allowed,
        "calibration_misses": misses,
        "calibration_recall": 1.0 - misses / max(positives, 1),
        "calibration_pruned": len(accepted),
        "calibration_avoided_cost": sum(row["example"].subtree_cost for row in accepted),
    }


def _group_key(stage: str, family: str | None = None) -> str:
    return f"{stage}:{family}" if family is not None else stage


def calibrate(rows, reference_rows, args):
    labeled = [
        row for row in rows if row["example"].target is not None and not row["unknown"] and not row["example"].baseline
    ]
    reference = [
        row
        for row in reference_rows
        if row["example"].target is not None and not row["unknown"] and not row["example"].baseline
    ]
    thresholds = {}
    uncertainty_limits = {}
    ood = {}
    known_families = sorted({str(row["example"].action.get("family", "other")) for row in reference})
    for stage in STAGES:
        stage_rows = [row for row in labeled if row["example"].stage == stage]
        recall = 1.0 if stage == "grammar" else args.recall_target
        shrink = {
            "grammar": args.grammar_threshold_shrink_quantile,
            "candidate": getattr(args, "candidate_threshold_shrink_quantile", None) or args.threshold_shrink_quantile,
            "composition": getattr(args, "composition_threshold_shrink_quantile", None)
            or args.threshold_shrink_quantile,
        }[stage]
        thresholds[_group_key(stage)] = _risk_threshold(stage_rows, recall, args.uncertainty_k, shrink)
        uncertainty_limits[stage] = (
            float(np.quantile([row["uncertainty"] for row in stage_rows], args.uncertainty_quantile))
            if stage_rows
            else 0.0
        )
        stage_reference = [row for row in reference if row["example"].stage == stage]
        embeddings = (
            np.stack([row["embedding"] for row in stage_reference])
            if stage_reference
            else np.zeros((1, args.retrieval_width))
        )
        center = embeddings.mean(0)
        scale = np.maximum(embeddings.std(0), 1e-3)
        calibration_embeddings = np.stack([row["embedding"] for row in stage_rows]) if stage_rows else embeddings
        distances = np.mean(np.square((calibration_embeddings - center) / scale), 1)
        ood[stage] = {"center": center, "scale": scale, "limit": float(np.quantile(distances, args.ood_quantile))}
        if getattr(args, "enable_family_thresholds", False):
            families = Counter(str(row["example"].action.get("family", "other")) for row in stage_rows)
            for family, count in families.items():
                family_rows = [row for row in stage_rows if str(row["example"].action.get("family", "other")) == family]
                positive_count = sum(row["example"].target == 1 for row in family_rows)
                if count >= args.min_family_samples and positive_count >= args.min_family_positives:
                    thresholds[_group_key(stage, family)] = _risk_threshold(
                        family_rows, recall, args.uncertainty_k, shrink
                    )
    retrieval = {}
    exact_history: dict[str, list[int]] = defaultdict(list)
    for row in reference:
        exact_history[row["signature"]].append(int(row["example"].target or 0))
    for stage in STAGES:
        families = {
            str(row["example"].action.get("family", "other")) for row in reference if row["example"].stage == stage
        }
        for family in families:
            group = [
                row
                for row in reference
                if row["example"].stage == stage and str(row["example"].action.get("family", "other")) == family
            ]
            group_embeddings = np.stack([row["embedding"] for row in group]).astype(np.float32)
            center = group_embeddings.mean(0)
            scale = np.maximum(group_embeddings.std(0), 1e-3)
            calibration_group = [
                row
                for row in labeled
                if row["example"].stage == stage and str(row["example"].action.get("family", "other")) == family
            ]
            distance_source = (
                np.stack([row["embedding"] for row in calibration_group]) if calibration_group else group_embeddings
            )
            local_distances = np.mean(np.square((distance_source - center) / scale), 1)
            retrieval[_group_key(stage, family)] = {
                "embeddings": group_embeddings,
                "targets": np.asarray([int(row["example"].target or 0) for row in group], dtype=np.int8),
                "center": center,
                "scale": scale,
                "ood_limit": float(np.quantile(local_distances, args.ood_quantile)),
            }
    return {
        "thresholds": thresholds,
        "uncertainty_limits": uncertainty_limits,
        "ood": ood,
        "known_families": known_families,
        "retrieval": retrieval,
        "exact_history": dict(exact_history),
        "uncertainty_k": args.uncertainty_k,
        "exploration_fraction": args.exploration_fraction,
        "retrieval_neighbors": args.retrieval_neighbors,
        "minimum_retrieval_support": args.minimum_retrieval_support,
    }


def _ood_distance(row: dict[str, Any], calibration: dict[str, Any]) -> float:
    stage = row["example"].stage
    record = calibration["ood"][stage]
    return float(np.mean(np.square((row["embedding"] - record["center"]) / record["scale"])))


def policy_decision(row: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    example = row["example"]
    stage = example.stage
    family = str(example.action.get("family", "other"))
    reserve = int(example.branch_id[:12], 16) % 10000 < int(calibration["exploration_fraction"] * 10000)
    distance = _ood_distance(row, calibration)
    if row["unknown"] or family not in calibration["known_families"]:
        return {"prune": False, "uncertain": True, "reason": "unknown_or_new_family", "distance": distance}
    if reserve:
        return {"prune": False, "uncertain": True, "reason": "exploration_reserve", "distance": distance}
    if row["uncertainty"] > calibration["uncertainty_limits"][stage]:
        return {"prune": False, "uncertain": True, "reason": "ensemble_uncertainty", "distance": distance}
    if distance > calibration["ood"][stage]["limit"]:
        return {"prune": False, "uncertain": True, "reason": "decision_ood", "distance": distance}
    family_key = _group_key(stage, family)
    threshold_record = calibration["thresholds"].get(family_key) or calibration["thresholds"].get(stage)
    score = _score(row, calibration["uncertainty_k"])
    if threshold_record is None or score > threshold_record["threshold"]:
        return {
            "prune": False,
            "uncertain": False,
            "reason": "preservation_score",
            "distance": distance,
            "score": score,
        }
    history = calibration["exact_history"].get(row["signature"])
    if history and any(history):
        return {
            "prune": False,
            "uncertain": True,
            "reason": "positive_exact_history",
            "distance": distance,
            "score": score,
        }
    neighborhood = calibration["retrieval"].get(family_key)
    if neighborhood is None or len(neighborhood["targets"]) < calibration["minimum_retrieval_support"]:
        return {
            "prune": False,
            "uncertain": True,
            "reason": "sparse_retrieval_support",
            "distance": distance,
            "score": score,
        }
    local_distance = float(np.mean(np.square((row["embedding"] - neighborhood["center"]) / neighborhood["scale"])))
    if local_distance > neighborhood["ood_limit"]:
        return {
            "prune": False,
            "uncertain": True,
            "reason": "family_decision_ood",
            "distance": distance,
            "family_distance": local_distance,
            "score": score,
        }
    similarity = neighborhood["embeddings"] @ row["embedding"]
    count = min(calibration["retrieval_neighbors"], len(similarity))
    indices = np.argpartition(similarity, -count)[-count:]
    if np.any(neighborhood["targets"][indices] > 0):
        return {
            "prune": False,
            "uncertain": True,
            "reason": "positive_nearest_neighbor",
            "distance": distance,
            "score": score,
        }
    return {
        "prune": True,
        "uncertain": False,
        "reason": "model_and_retrieval_dead_consensus",
        "distance": distance,
        "score": score,
    }


def oracle_frontier(rows, calibration):
    """Report retrospective separability without presenting it as a deployable threshold."""
    policy_rows = [row for row in rows if row["example"].policy_surface]
    positives = sum(row["example"].target == 1 for row in policy_rows)
    scored = []
    for row in policy_rows:
        example = row["example"]
        distance = _ood_distance(row, calibration)
        reserve = int(example.branch_id[:12], 16) % 10000 < int(calibration["exploration_fraction"] * 10000)
        eligible = (
            example.target is not None
            and not row["unknown"]
            and row["uncertainty"] <= calibration["uncertainty_limits"][example.stage]
            and distance <= calibration["ood"][example.stage]["limit"]
            and not reserve
        )
        if eligible:
            scored.append((_score(row, calibration["uncertainty_k"]), int(example.target), example.subtree_cost))
    groups: list[tuple[float, list[int]]] = []
    for score, target, cost in sorted(scored):
        if not groups or score != groups[-1][0]:
            groups.append((score, []))
        groups[-1][1].append((target, cost))
    result = []
    for recall_target in (1.0, 0.999, 0.995, 0.99):
        allowed_misses = math.floor((1.0 - recall_target) * positives + 1e-12)
        misses = pruned = negative_pruned = 0
        avoided_cost = 0.0
        for _, targets in groups:
            group_misses = sum(target for target, _ in targets)
            if misses + group_misses > allowed_misses:
                break
            misses += group_misses
            pruned += len(targets)
            negative_pruned += len(targets) - group_misses
            avoided_cost += sum(cost for _, cost in targets)
        result.append(
            {
                "target_recall": recall_target,
                "achieved_recall": 1.0 - misses / max(positives, 1),
                "misses": misses,
                "search_space_reduction": pruned / max(len(policy_rows), 1),
                "prune_precision": negative_pruned / max(pruned, 1),
                "overlapping_subtree_cost_pruned": avoided_cost,
                "note": "retrospective labeled-holdout frontier; not a deployable calibration",
            }
        )
    return result


def online_replay(rows: list[dict[str, Any]], decisions: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    policy_rows = [row for row in rows if row["example"].policy_surface]
    by_root: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in policy_rows:
        by_root[(row["example"].project, row["example"].root_id)].append(row)
    avoided_nodes = 0
    avoided_work = 0.0
    killed_terminals = 0
    total_terminals = 0
    total_work = 0.0
    for root_rows in by_root.values():
        by_id = {row["example"].branch_id: row for row in root_rows}
        children: dict[str, list[str]] = defaultdict(list)
        for row in root_rows:
            parent = row["example"].parent_branch_id
            if parent in by_id:
                children[parent].append(row["example"].branch_id)
        roots = [branch_id for branch_id, row in by_id.items() if row["example"].parent_branch_id not in by_id]
        own_work = {
            branch_id: 1.0
            + row["example"].node_expansions
            + row["example"].proof_calls
            + row["example"].compiler_invocations
            for branch_id, row in by_id.items()
        }
        total_work += sum(own_work.values())
        terminal_positive = {
            branch_id for branch_id, row in by_id.items() if row["example"].target == 1 and not children.get(branch_id)
        }
        total_terminals += len(terminal_positive)

        def descendants(branch_id: str) -> set[str]:
            result = {branch_id}
            for child in children.get(branch_id, ()):
                result.update(descendants(child))
            return result

        stack = list(roots)
        visited = set()
        while stack:
            branch_id = stack.pop()
            if branch_id in visited:
                continue
            visited.add(branch_id)
            key = (by_id[branch_id]["example"].project, by_id[branch_id]["example"].root_id, branch_id)
            if decisions[key]["prune"]:
                removed = descendants(branch_id)
                avoided_nodes += len(removed)
                avoided_work += sum(own_work[item] for item in removed)
                killed_terminals += len(removed & terminal_positive)
                visited.update(removed)
            else:
                stack.extend(children.get(branch_id, ()))
    return {
        "branches": len(policy_rows),
        "avoided_branch_evaluations": avoided_nodes,
        "online_expansion_reduction": avoided_nodes / max(len(policy_rows), 1),
        "total_work_units": total_work,
        "avoided_work_units": avoided_work,
        "online_work_reduction": avoided_work / max(total_work, 1e-12),
        "useful_terminals": total_terminals,
        "killed_useful_terminals": killed_terminals,
        "useful_terminal_survival": 1.0 - killed_terminals / max(total_terminals, 1),
    }


def evaluate(rows, calibration):
    counts = {name: 0 for name in ("KEEP", "KEEP_UNCERTAIN", "PRUNE_HIGH_CONFIDENCE")}
    positives = misses = negatives = negative_pruned = 0
    stages = {
        name: {"branches": 0, "positives": 0, "misses": 0, "pruned": 0, "subtree_cost_pruned": 0.0} for name in STAGES
    }
    families: dict[str, dict[str, Any]] = defaultdict(lambda: {"branches": 0, "positives": 0, "misses": 0, "pruned": 0})
    decisions = {}
    missed_severity = Counter()
    reasons = Counter()
    for row in rows:
        example = row["example"]
        if not example.policy_surface:
            continue
        stage = stages[example.stage]
        stage["branches"] += 1
        decision = policy_decision(row, calibration)
        prune = decision["prune"]
        uncertain = decision["uncertain"]
        decisions[(example.project, example.root_id, example.branch_id)] = decision
        reasons[decision["reason"]] += 1
        disposition = "PRUNE_HIGH_CONFIDENCE" if prune else "KEEP_UNCERTAIN" if uncertain else "KEEP"
        family_key = _group_key(example.stage, str(example.action.get("family", "other")))
        family = families[family_key]
        counts[disposition] += 1
        stage["pruned"] += int(prune)
        stage["subtree_cost_pruned"] += example.subtree_cost * int(prune)
        family["branches"] += 1
        family["pruned"] += int(prune)
        if example.target == 1:
            positives += 1
            stage["positives"] += 1
            family["positives"] += 1
            misses += int(prune)
            stage["misses"] += int(prune)
            family["misses"] += int(prune)
            if prune:
                missed_severity[str(example.utility_severity)] += 1
        elif example.target == 0:
            negatives += 1
            negative_pruned += int(prune)
    branches = sum(item["branches"] for item in stages.values())
    for value in stages.values():
        value["recall"] = 1 - value["misses"] / max(value["positives"], 1)
        value["reduction"] = value["pruned"] / max(value["branches"], 1)
    for value in families.values():
        value["recall"] = 1 - value["misses"] / max(value["positives"], 1)
        value["reduction"] = value["pruned"] / max(value["branches"], 1)
    replay = online_replay(rows, decisions)
    return {
        "branches": branches,
        "positives": positives,
        "negatives": negatives,
        "misses": misses,
        "useful_descendant_recall": 1 - misses / max(positives, 1),
        "search_space_reduction": counts["PRUNE_HIGH_CONFIDENCE"] / max(branches, 1),
        "prune_precision": negative_pruned / max(counts["PRUNE_HIGH_CONFIDENCE"], 1),
        "policy_counts": counts,
        "decision_reasons": dict(reasons),
        "stage_metrics": stages,
        "family_metrics": dict(families),
        "missed_utility_severity": dict(missed_severity),
        "online_replay": replay,
        "oracle_frontier": oracle_frontier(rows, calibration),
        "zero_miss_rule_of_three_95_lower_bound": max(0.0, 1 - 3 / max(positives, 1)) if misses == 0 else None,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _aggregate_stage_metrics(folds: list[dict[str, Any]]) -> dict[str, Any]:
    result = {stage: {"branches": 0, "positives": 0, "misses": 0, "pruned": 0} for stage in STAGES}
    for fold in folds:
        for stage, metrics in fold["metrics"]["stage_metrics"].items():
            for field in result[stage]:
                result[stage][field] += metrics[field]
    for metrics in result.values():
        metrics["recall"] = 1 - metrics["misses"] / max(metrics["positives"], 1)
        metrics["reduction"] = metrics["pruned"] / max(metrics["branches"], 1)
    return result


def _save_prediction_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    np.savez_compressed(
        path,
        project=np.asarray([row["example"].project for row in rows]),
        root_id=np.asarray([row["example"].root_id for row in rows]),
        branch_id=np.asarray([row["example"].branch_id for row in rows]),
        stage=np.asarray([row["example"].stage for row in rows]),
        family=np.asarray([str(row["example"].action.get("family", "other")) for row in rows]),
        target=np.asarray([row["example"].target if row["example"].target is not None else -1 for row in rows]),
        probability=np.asarray([row["probability"] for row in rows], dtype=np.float32),
        uncertainty=np.asarray([row["uncertainty"] for row in rows], dtype=np.float32),
        embedding=np.stack([row["embedding"] for row in rows]).astype(np.float32),
        unknown=np.asarray([row["unknown"] for row in rows], dtype=np.bool_),
        subtree_size=np.asarray([row["example"].subtree_size for row in rows], dtype=np.int32),
        subtree_cost=np.asarray([row["example"].subtree_cost for row in rows], dtype=np.float32),
        utility_severity=np.asarray([row["example"].utility_severity for row in rows], dtype=np.int8),
    )


def train_command(args):
    seed_all(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    examples = load_campaign_examples(args.progress, args.manifest)
    projects = sorted({x.project for x in examples})
    folds = []
    args.output.mkdir(parents=True, exist_ok=True)
    for heldout in projects:
        train, calibration_examples = root_partition(examples, heldout=heldout)
        test = [x for x in examples if x.project == heldout]
        vocab = Vocab.build(train)
        models = []
        histories = []
        for member in range(args.ensemble_size):
            model, history = fit(train, calibration_examples, vocab, args, device, member * 1009)
            models.append(model)
            histories.append(history)
        calibration_rows = predict(models, calibration_examples, vocab, args, device)
        train_rows = predict(models, train, vocab, args, device)
        test_rows = predict(models, test, vocab, args, device)
        calibration = calibrate(calibration_rows, train_rows, args)
        metrics = evaluate(test_rows, calibration)
        fold_name = heldout.replace("/", "_")
        torch.save(
            {
                "schema_version": SCHEMA,
                "state_dicts": [model.state_dict() for model in models],
                "config": asdict(models[0].config),
                "vocab": vocab.to_dict(),
                "calibration": calibration,
                "heldout_project": heldout,
            },
            args.output / f"fold-{fold_name}.pt",
        )
        _save_prediction_rows(args.output / f"fold-{fold_name}-train.npz", train_rows)
        _save_prediction_rows(args.output / f"fold-{fold_name}-calibration.npz", calibration_rows)
        _save_prediction_rows(args.output / f"fold-{fold_name}-test.npz", test_rows)
        folds.append(
            {
                "heldout_project": heldout,
                "train_roots": len({x.root_id for x in train}),
                "calibration_roots": len({x.root_id for x in calibration_examples}),
                "test_roots": len({x.root_id for x in test}),
                "metrics": metrics,
                "histories": histories,
            }
        )
        del models
        if device.type == "cuda":
            torch.cuda.empty_cache()
    train, calibration_examples = root_partition(examples)
    vocab = Vocab.build(train)
    models = []
    histories = []
    for member in range(args.ensemble_size):
        model, history = fit(train, calibration_examples, vocab, args, device, member * 1009)
        models.append(model)
        histories.append(history)
    calibration = calibrate(
        predict(models, calibration_examples, vocab, args, device),
        predict(models, train, vocab, args, device),
        args,
    )
    state = {
        "schema_version": SCHEMA,
        "state_dicts": [model.state_dict() for model in models],
        "config": asdict(models[0].config),
        "vocab": vocab.to_dict(),
        "calibration": calibration,
        "stages": list(STAGES),
    }
    torch.save(state, args.output / "model.pt")
    positives = sum(f["metrics"]["positives"] for f in folds)
    misses = sum(f["metrics"]["misses"] for f in folds)
    branches = sum(f["metrics"]["branches"] for f in folds)
    pruned = sum(f["metrics"]["policy_counts"]["PRUNE_HIGH_CONFIDENCE"] for f in folds)
    allowed_misses = math.floor((1 - args.recall_target) * positives + 1e-12)
    aggregate_replay = {
        field: sum(f["metrics"]["online_replay"][field] for f in folds)
        for field in (
            "branches",
            "avoided_branch_evaluations",
            "total_work_units",
            "avoided_work_units",
            "useful_terminals",
            "killed_useful_terminals",
        )
    }
    aggregate_replay.update(
        {
            "online_expansion_reduction": aggregate_replay["avoided_branch_evaluations"]
            / max(aggregate_replay["branches"], 1),
            "online_work_reduction": aggregate_replay["avoided_work_units"]
            / max(aggregate_replay["total_work_units"], 1e-12),
            "useful_terminal_survival": 1
            - aggregate_replay["killed_useful_terminals"] / max(aggregate_replay["useful_terminals"], 1),
        }
    )
    aggregate = {
        "branches": branches,
        "positives": positives,
        "misses": misses,
        "allowed_misses_at_target": allowed_misses,
        "useful_descendant_recall": 1 - misses / max(positives, 1),
        "search_space_reduction": pruned / max(branches, 1),
        "stage_metrics": _aggregate_stage_metrics(folds),
        "online_replay": aggregate_replay,
        "operating_point_met": misses <= allowed_misses
        and aggregate_replay["useful_terminal_survival"] >= args.recall_target,
        "zero_miss_rule_of_three_95_lower_bound": max(0.0, 1 - 3 / max(positives, 1)) if misses == 0 else None,
    }
    report = {
        "schema_version": "vladder-search-pruner-evaluation-v2",
        "status": "shadow_only",
        "objective": "maximize avoided subtree expansion subject to useful-descendant survival; no performance prediction",
        "training_policy": {
            "stage_pretraining_epochs": args.stage_epochs,
            "hard_mining_epochs": args.hard_epochs,
            "focal_gamma": args.focal_gamma,
            "positive_margin": args.positive_margin,
            "auxiliary_weight": args.auxiliary_weight,
            "sibling_ranking_weight": args.ranking_weight,
            "independent_seed_ensemble": args.ensemble_size,
            "family_specific_thresholds": args.enable_family_thresholds,
        },
        "campaign_count": len(args.progress),
        "campaigns": [
            {"progress": str(progress.resolve()), "manifest": str(manifest.resolve())}
            for progress, manifest in zip(args.progress, args.manifest, strict=True)
        ],
        "model_parameters_per_member": models[0].parameter_count(),
        "ensemble_size": len(models),
        "device": str(device),
        "examples": len(examples),
        "roots": len({(x.project, x.root_id) for x in examples}),
        "projects": projects,
        "folds": folds,
        "aggregate": aggregate,
        "live_eligibility": {
            "eligible": False,
            "requirements": {
                "held_project_recall_at_least_target": misses <= allowed_misses,
                "useful_terminal_survival_at_least_target": aggregate_replay["useful_terminal_survival"]
                >= args.recall_target,
                "at_least_3000_heldout_positives": positives >= 3000,
                "at_least_100_positives_per_project": all(f["metrics"]["positives"] >= 100 for f in folds),
            },
            "claim": "Frozen-corpus ablations remain shadow-only until independent live-search validation.",
        },
        "final": {
            "model": str((args.output / "model.pt").resolve()),
            "training_roots": len({(x.project, x.root_id) for x in train}),
            "calibration_roots": len({(x.project, x.root_id) for x in calibration_examples}),
            "histories": histories,
        },
    }
    (args.output / "evaluation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["aggregate"], indent=2))


def _raw_action(raw, root):
    parameters = {
        key: value
        for key, value in raw.items()
        if key not in {"family", "family_version", "rule", "op", "parameter", "value"}
    }
    if isinstance(raw.get("parameter"), str) and "value" in raw:
        parameters[raw["parameter"]] = raw["value"]
    return sanitize_training_action(
        {
            "family": raw.get("family", "other"),
            "family_version": raw.get("family_version") or root.get("grammar_version", "unversioned"),
            "primitives": [raw.get("rule") or raw.get("parameter") or raw.get("op") or "expand"],
            "parameters": parameters,
        }
    )


def _learning_graph(graph):
    return {
        "node_features": [{key: value for key, value in node.items() if key != "index"} for node in graph["nodes"]],
        "edge_index": [
            [edge["source"] for edge in graph["edges"]],
            [edge["destination"] for edge in graph["edges"]],
        ],
        "edge_features": [
            {key: value for key, value in edge.items() if key not in {"source", "destination"}}
            for edge in graph["edges"]
        ],
        "obligations": graph["obligations"],
        "effects": graph["effects"],
        "protocols": graph["protocols"],
        "claims": graph["claims"],
    }


def _restore_calibration(raw: dict[str, Any]) -> dict[str, Any]:
    result = dict(raw)
    result["ood"] = {
        stage: {
            **record,
            "center": np.asarray(record["center"], dtype=np.float32),
            "scale": np.asarray(record["scale"], dtype=np.float32),
        }
        for stage, record in raw["ood"].items()
    }
    retrieval = {}
    for key, record in raw["retrieval"].items():
        embeddings = np.asarray(record["embeddings"], dtype=np.float32)
        center = np.asarray(record.get("center", embeddings.mean(0)), dtype=np.float32)
        scale = np.asarray(record.get("scale", np.maximum(embeddings.std(0), 1e-3)), dtype=np.float32)
        retrieval[key] = {
            **record,
            "embeddings": embeddings,
            "targets": np.asarray(record["targets"], dtype=np.int8),
            "center": center,
            "scale": scale,
            "ood_limit": float(record.get("ood_limit", math.inf)),
        }
    result["retrieval"] = retrieval
    return result


def serve_command(args):
    artifact = torch.load(args.model, map_location="cpu", weights_only=True)
    vocab = Vocab(artifact["vocab"])
    config = ModelConfig(**artifact["config"])
    state_dicts = artifact.get("state_dicts") or [artifact["state_dict"]]
    models = []
    for state_dict in state_dicts:
        model = SurvivalModel(vocab, config)
        model.load_state_dict(state_dict)
        models.append(model)
    calibration = _restore_calibration(artifact["calibration"])
    roots = {}
    for line in sys.stdin:
        try:
            request = json.loads(line)
            kind = request.get("kind")
            if kind == "register_root":
                raw = request["root"]
                graph = sanitize_graph(raw["semantic_graph"])
                roots[request["root_id"]] = {
                    "raw_graph": raw["semantic_graph"],
                    "graph": _learning_graph(graph),
                    "grammar_version": raw.get("grammar_version", "unversioned"),
                }
                response = {"status": "ready"}
            elif kind == "decide":
                root = roots[request["root_id"]]
                state = request["state"]
                action = _raw_action(state["action"], root)
                lineage = tuple(_raw_action(x, root) for x in request.get("ancestor_action_path", [])[:-1])
                context = sanitize_decision_context(state.get("decision_context"), fallback_graph=root["raw_graph"])
                example = Example(
                    project="live",
                    root_id=request["root_id"],
                    search_id=str(request.get("search_id", "live")),
                    branch_id=state["identity"],
                    parent_branch_id=state.get("parent_identity"),
                    graph=_learning_graph(context["graph"]),
                    stage=stage_group(state["stage"]),
                    depth=int(request["depth"]),
                    baseline=False,
                    action=action,
                    lineage=lineage,
                    target=None,
                    policy_surface=True,
                    focus_node_indices=tuple(context["focus_node_indices"]),
                    context_quality=str(context["quality"]),
                    state_features=dict(context["state_features"]),
                    semantic_delta=dict(context["semantic_delta"]),
                )

                class A:
                    batch_size = 1
                    mc_samples = args.mc_samples

                row = predict(models, [example], vocab, A(), torch.device("cpu"))[0]
                decision = policy_decision(row, calibration)
                prune = decision["prune"]
                response = {
                    "decision": "PRUNE_HIGH_CONFIDENCE"
                    if prune
                    else "KEEP_UNCERTAIN"
                    if decision["uncertain"]
                    else "KEEP",
                    "confidence": 1 - row["probability"] if prune else row["probability"],
                    "in_distribution": not decision["uncertain"],
                    "reason": decision["reason"],
                }
            else:
                response = {
                    "decision": "KEEP_UNCERTAIN",
                    "confidence": 0.0,
                    "in_distribution": False,
                    "reason": "unknown protocol message",
                }
        except Exception as error:
            response = {
                "decision": "KEEP_UNCERTAIN",
                "confidence": 0.0,
                "in_distribution": False,
                "reason": f"fail-open oracle error: {error}",
            }
        print(json.dumps(response, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--progress", type=Path, action="append", required=True)
    train.add_argument("--manifest", type=Path, action="append", required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--epochs", type=int, default=6)
    train.add_argument("--stage-epochs", type=int, default=0)
    train.add_argument("--hard-epochs", type=int, default=0)
    train.add_argument("--hard-examples", type=int, default=1024)
    train.add_argument("--batch-size", type=int, default=96)
    train.add_argument("--learning-rate", type=float, default=2e-4)
    train.add_argument("--dropout", type=float, default=0.12)
    train.add_argument("--hidden", type=int, default=384)
    train.add_argument("--categorical", type=int, default=64)
    train.add_argument("--action-width", type=int, default=128)
    train.add_argument("--layers", type=int, default=3)
    train.add_argument("--trunk-width", type=int, default=512)
    train.add_argument("--latent-width", type=int, default=384)
    train.add_argument("--retrieval-width", type=int, default=64)
    train.add_argument("--grammar-positive-weight", type=float, default=5.0)
    train.add_argument("--candidate-positive-weight", type=float, default=5.0)
    train.add_argument("--composition-positive-weight", type=float, default=5.0)
    train.add_argument("--focal-gamma", type=float, default=0.0)
    train.add_argument("--positive-margin", type=float, default=0.0)
    train.add_argument("--subtree-weight", type=float, default=0.0)
    train.add_argument("--auxiliary-weight", type=float, default=0.0)
    train.add_argument("--ranking-weight", type=float, default=0.0)
    train.add_argument("--ranking-margin", type=float, default=1.0)
    train.add_argument("--max-ranking-pairs", type=int, default=1536)
    train.add_argument("--negative-positive-ratio", type=float, default=50.0)
    train.add_argument("--negative-cluster-cap", type=int, default=1000)
    train.add_argument("--grammar-joint-fraction", type=float, default=0.15)
    train.add_argument("--recall-target", type=float, default=0.999)
    train.add_argument("--uncertainty-k", type=float, default=3.0)
    train.add_argument("--uncertainty-quantile", type=float, default=0.995)
    train.add_argument("--threshold-shrink-quantile", type=float, default=0.075)
    train.add_argument("--grammar-threshold-shrink-quantile", type=float, default=0.15)
    train.add_argument("--candidate-threshold-shrink-quantile", type=float, default=0.075)
    train.add_argument("--composition-threshold-shrink-quantile", type=float, default=0.075)
    train.add_argument("--ood-quantile", type=float, default=0.9975)
    train.add_argument("--min-family-samples", type=int, default=80)
    train.add_argument("--min-family-positives", type=int, default=12)
    train.add_argument("--enable-family-thresholds", action="store_true")
    train.add_argument("--retrieval-neighbors", type=int, default=5)
    train.add_argument("--minimum-retrieval-support", type=int, default=12)
    train.add_argument("--exploration-fraction", type=float, default=0.01)
    train.add_argument("--ensemble-size", type=int, default=3)
    train.add_argument("--mc-samples", type=int, default=2)
    train.add_argument("--seed", type=int, default=20260810)
    train.add_argument("--cpu", action="store_true")
    train.add_argument("--freeze-encoder-after-pretrain", action="store_true")
    train.set_defaults(func=train_command)
    serve = sub.add_parser("serve")
    serve.add_argument("--model", type=Path, required=True)
    serve.add_argument("--mc-samples", type=int, default=8)
    serve.set_defaults(func=serve_command)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
