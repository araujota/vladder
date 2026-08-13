#!/usr/bin/env python3
"""Train and evaluate vLadder's composition-native best-first search policy.

ML assigns priority only. Exact canonicalization, deterministic closure, and formal verification
remain the only authorities that can remove a state.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
import tempfile
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    import torch
    from torch import nn
    import torch.nn.functional as F
    from torch.utils.data import DataLoader
except ImportError as error:  # pragma: no cover
    raise SystemExit("composition-native-policy requires `pip install 'vladder[ml]'`") from error

from vladder.composition_native import COMPOSITION_TRACE_VERSION, inference_view


SCHEMA = "vladder-composition-native-policy-v1"
CHECKPOINTS = (0.01, 0.05, 0.10, 0.20, 0.30, 0.50, 1.0)
REDUNDANCY = (
    "unique", "canonical-equivalent", "compiler-identical", "dominated",
    "commutative-equivalent", "exhausted-dead", "other",
)


@dataclass(frozen=True)
class Option:
    action_id: str
    child_state_id: str | None
    action: dict[str, Any]
    delta: dict[str, Any]
    tier: int
    distance: float
    cost: float
    redundancy: int
    rank: int


@dataclass(frozen=True)
class Decision:
    project: str
    root_id: str
    root_topology_hash: str
    frontier_id: str
    state_id: str | None
    semantic_graph: dict[str, Any]
    interaction_graph: dict[str, Any]
    history: tuple[dict[str, Any], ...]
    options: tuple[Option, ...]
    depth: int
    composition: bool


@dataclass(frozen=True)
class TraceTree:
    project: str
    root_id: str
    canonical_root_hash: str
    states: dict[str, dict[str, Any]]
    frontiers: dict[str | None, Decision]
    terminals: dict[str, dict[str, Any]]
    transpositions: tuple[dict[str, Any], ...]


def load_native_corpus(directory: Path) -> tuple[tuple[Decision, ...], tuple[TraceTree, ...], list[dict[str, Any]]]:
    paths = sorted(directory.glob("roots/*/composition-native-search-trace.json"))
    paths += sorted(directory.glob("roots/*/composition-native-search-trace.json.gz"))
    if not paths:
        paths = sorted(directory.rglob("composition-native-search-trace.json"))
        paths += sorted(directory.rglob("composition-native-search-trace.json.gz"))
    decisions = []
    trees = []
    traces = []
    seen = set()
    seen_roots = set()
    for path in paths:
        trace = _read_json(path)
        if trace.get("schema_version") != COMPOSITION_TRACE_VERSION or trace.get("trace_hash") in seen:
            continue
        seen.add(trace["trace_hash"])
        if not trace.get("complete"):
            continue
        root_key = (
            str(trace["root"]["project_id"]),
            str(trace["root"]["canonical_root_hash"]),
        )
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)
        local_frontiers = _trace_decisions(trace)
        if not local_frontiers:
            continue
        project = str(trace["root"]["project_id"])
        root_id = str(trace["root"]["root_id"])
        states = {str(item["state_id"]): dict(item) for item in trace["states"]}
        terminals = {str(item["state_id"]): dict(item) for item in trace["terminals"]}
        invalid_terminal_owners = [
            state_id for state_id in terminals
            if states.get(state_id, {}).get("canonical_of")
            or states.get(state_id, {}).get("disposition") in {
                "canonical_duplicate", "verified_equivalent",
            }
        ]
        if invalid_terminal_owners:
            raise ValueError(
                f"composition trace attaches terminals to transposed duplicates: {path}; "
                "run scripts/normalize_composition_native_corpus.py"
            )
        frontier_map = {item.state_id: item for item in local_frontiers}
        if None not in frontier_map:
            referenced = {
                option.child_state_id for item in local_frontiers for option in item.options
                if option.child_state_id is not None
            }
            roots = sorted(
                (item for item in local_frontiers if item.state_id not in referenced),
                key=lambda item: (item.depth, item.frontier_id),
            )
            if roots:
                frontier_map[None] = roots[0]
        trees.append(TraceTree(
            project,
            root_id,
            str(trace["root"]["canonical_root_hash"]),
            states,
            frontier_map,
            terminals,
            tuple(dict(item) for item in trace["transpositions"]),
        ))
        decisions.extend(item for item in local_frontiers if len(item.options) >= 2)
        traces.append(trace)
    return tuple(decisions), tuple(trees), traces


def _trace_decisions(trace: Mapping[str, Any]) -> list[Decision]:
    labels = {str(item["frontier_id"]): item for item in trace.get("labels", ())}
    project = str(trace["root"]["project_id"])
    root_id = str(trace["root"]["root_id"])
    root_topology_hash = _normalized_topology_hash(trace["root"]["semantic_graph"])
    result = []
    for frontier in trace.get("frontiers", ()):
        label = labels.get(str(frontier["frontier_id"]))
        if label is None or not frontier.get("available_actions"):
            continue
        outcomes = {str(item["action_id"]): item for item in label["action_outcomes"]}
        options = []
        for action in frontier["available_actions"]:
            outcome = outcomes[str(action["action_id"])]
            tier = int(str(outcome["best_descendant_tier"])[1:])
            distances = outcome.get("distance_to_tiers", {})
            distance = distances.get(f"U{tier}") if tier else None
            options.append(Option(
                str(action["action_id"]),
                outcome.get("child_state_id"),
                dict(action.get("action", {})),
                dict(action.get("local_graph_delta", {})),
                tier,
                float(distance if distance is not None else 32.0),
                max(1e-6, float(outcome.get("cost_to_best_descendant", 1.0))),
                REDUNDANCY.index(outcome["redundancy_class"])
                if outcome.get("redundancy_class") in REDUNDANCY else len(REDUNDANCY) - 1,
                int(outcome.get("advantage_rank", len(options))),
            ))
        history = tuple(dict(item) for item in frontier.get("search_history", ()))
        parent = frontier.get("parent_state", {}).get("decision_context", {})
        composition = len(history) >= 2 or any(_composition_action(item.action) for item in options)
        result.append(Decision(
            project,
            root_id,
            root_topology_hash,
            str(frontier["frontier_id"]),
            str(frontier["state_id"]) if frontier.get("state_id") is not None else None,
            dict(parent.get("graph", trace["root"]["semantic_graph"])),
            dict(frontier.get("interaction_graph", {})),
            history,
            tuple(options),
            len(history),
            composition,
        ))
    return result


class Vocab:
    FIELDS = ("node_kind", "node_operation", "node_type", "edge_relation", "action")

    def __init__(self, values: dict[str, dict[str, int]]) -> None:
        self.values = values

    @classmethod
    def build(cls, decisions: Iterable[Decision], historical: Iterable[Any] = ()) -> "Vocab":
        raw = {name: set() for name in cls.FIELDS}
        for decision in decisions:
            for graph in (decision.semantic_graph, decision.interaction_graph):
                for node in _nodes(graph):
                    raw["node_kind"].add(str(node.get("kind", "Other")))
                    raw["node_operation"].add(str(node.get("operation", node.get("kind", "other"))))
                    raw["node_type"].add(str(node.get("output_type", node.get("attributes", {}).get("relation", "other"))))
                for edge in _edges(graph):
                    raw["edge_relation"].add(str(edge.get("relation", "other")))
            for option in decision.options:
                raw["action"].update(_action_tokens(option.action, "current"))
                raw["action"].update(_delta_tokens(option.delta))
            for action in decision.history:
                raw["action"].update(_action_tokens(action, "history"))
        for example in historical:
            for node in _nodes(example.graph):
                raw["node_kind"].add(str(node.get("kind", "Other")))
                raw["node_operation"].add(str(node.get("operation", node.get("kind", "other"))))
                raw["node_type"].add(str(node.get("output_type", node.get("type_class", "other"))))
            for edge in _edges(example.graph):
                raw["edge_relation"].add(str(edge.get("relation", "other")))
            raw["action"].update(_action_tokens(example.action, "current"))
        return cls({name: {token: index + 1 for index, token in enumerate(sorted(values))} for name, values in raw.items()})

    def index(self, field: str, value: str) -> int:
        return self.values[field].get(value, 0)


def _nodes(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = graph.get("nodes", graph.get("node_features", ()))
    return [dict(item) for item in values if isinstance(item, Mapping)]


def _edges(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = graph.get("edges", graph.get("edge_features", ()))
    return [dict(item) for item in values if isinstance(item, Mapping)]


def tensorize_graph(graph: Mapping[str, Any], vocab: Vocab) -> dict[str, torch.Tensor]:
    nodes = _nodes(graph)
    if not nodes:
        nodes = [{"id": "empty", "kind": "Empty", "operation": "empty", "output_type": "none"}]
    node_ids = {str(node.get("id", index)): index for index, node in enumerate(nodes)}
    node_cat = []
    node_num = []
    for node in nodes:
        attrs = node.get("attributes") if isinstance(node.get("attributes"), Mapping) else {}
        node_cat.append([
            vocab.index("node_kind", str(node.get("kind", "Other"))),
            vocab.index("node_operation", str(node.get("operation", node.get("kind", "other")))),
            vocab.index("node_type", str(node.get("output_type", attrs.get("relation", "other")))),
        ])
        node_num.append([
            math.log1p(float(attrs.get("count", 0) or 0)),
            math.log1p(float(attrs.get("size", 0) or 0)),
            float("lifetime" in attrs),
            float(node.get("kind") == "interaction_factor"),
        ])
    edges = _edges(graph)
    edge_index = [[], []]
    edge_cat = []
    for index, edge in enumerate(edges):
        source = edge.get("source")
        destination = edge.get("destination")
        if isinstance(source, int) and isinstance(destination, int):
            left, right = source, destination
        else:
            left = node_ids.get(str(source), 0)
            right = node_ids.get(str(destination), 0)
        if not (0 <= left < len(nodes) and 0 <= right < len(nodes)):
            continue
        edge_index[0].append(left)
        edge_index[1].append(right)
        edge_cat.append(vocab.index("edge_relation", str(edge.get("relation", "other"))))
    if not edge_cat:
        edge_index = [[0], [0]]
        edge_cat = [0]
    return {
        "node_cat": torch.tensor(node_cat, dtype=torch.long),
        "node_num": torch.tensor(node_num, dtype=torch.float32),
        "edge_index": torch.tensor(edge_index, dtype=torch.long),
        "edge_cat": torch.tensor(edge_cat, dtype=torch.long),
    }


def collate_graphs(graphs: Iterable[Mapping[str, Any]], vocab: Vocab) -> dict[str, torch.Tensor]:
    tensors = [tensorize_graph(graph, vocab) for graph in graphs]
    node_cat, node_num, edge_cat, edge_index, batch = [], [], [], [], []
    offset = 0
    for graph_index, item in enumerate(tensors):
        node_cat.append(item["node_cat"])
        node_num.append(item["node_num"])
        edge_cat.append(item["edge_cat"])
        edge_index.append(item["edge_index"] + offset)
        batch.append(torch.full((item["node_cat"].shape[0],), graph_index, dtype=torch.long))
        offset += item["node_cat"].shape[0]
    return {
        "node_cat": torch.cat(node_cat), "node_num": torch.cat(node_num),
        "edge_cat": torch.cat(edge_cat), "edge_index": torch.cat(edge_index, 1),
        "batch": torch.cat(batch), "count": torch.tensor(len(tensors)),
    }


class MessageLayer(nn.Module):
    def __init__(self, hidden: int, dropout: float) -> None:
        super().__init__()
        self.message = nn.Sequential(nn.Linear(hidden * 2, hidden), nn.GELU(), nn.Linear(hidden, hidden))
        self.update = nn.Sequential(nn.Linear(hidden * 2, hidden), nn.GELU(), nn.Linear(hidden, hidden))
        self.norm = nn.LayerNorm(hidden)
        self.dropout = nn.Dropout(dropout)

    def forward(self, node, edge_index, edge):
        source, destination = edge_index
        message = self.message(torch.cat([node[source], edge], 1))
        aggregate = torch.zeros_like(node)
        aggregate.index_add_(0, destination, message)
        return self.norm(node + self.dropout(self.update(torch.cat([node, aggregate], 1))))


class GraphEncoder(nn.Module):
    def __init__(self, vocab: Vocab, hidden: int, categorical: int, layers: int, dropout: float, *, global_attention: bool) -> None:
        super().__init__()
        self.kind = nn.Embedding(len(vocab.values["node_kind"]) + 1, categorical)
        self.operation = nn.Embedding(len(vocab.values["node_operation"]) + 1, categorical)
        self.output_type = nn.Embedding(len(vocab.values["node_type"]) + 1, categorical)
        self.edge_relation = nn.Embedding(len(vocab.values["edge_relation"]) + 1, hidden)
        self.node_in = nn.Linear(categorical * 3 + 4, hidden)
        self.layers = nn.ModuleList(MessageLayer(hidden, dropout) for _ in range(layers))
        self.attention = nn.MultiheadAttention(hidden, 4, dropout=dropout, batch_first=True) if global_attention else None
        self.norm = nn.LayerNorm(hidden)
        self.out = nn.Sequential(nn.Linear(hidden * 2, hidden), nn.GELU(), nn.Linear(hidden, hidden))

    def forward(self, batch):
        cat = batch["node_cat"]
        node = F.gelu(self.node_in(torch.cat([
            self.kind(cat[:, 0]), self.operation(cat[:, 1]), self.output_type(cat[:, 2]), batch["node_num"],
        ], 1)))
        edge = self.edge_relation(batch["edge_cat"])
        for layer in self.layers:
            node = layer(node, batch["edge_index"], edge)
            if self.attention is not None:
                node = self._global(node, batch["batch"])
        count = int(batch["count"])
        mean = torch.zeros((count, node.shape[1]), device=node.device)
        mean.index_add_(0, batch["batch"], node)
        sizes = torch.bincount(batch["batch"], minlength=count).clamp_min(1)[:, None]
        mean = mean / sizes
        maximum = torch.full_like(mean, -torch.inf)
        maximum.scatter_reduce_(0, batch["batch"][:, None].expand_as(node), node, reduce="amax", include_self=True)
        return self.out(torch.cat([mean, maximum], 1))

    def _global(self, node, batch):
        groups = [node[batch == index] for index in range(int(batch.max()) + 1)]
        padded = nn.utils.rnn.pad_sequence(groups, batch_first=True)
        lengths = torch.tensor([len(group) for group in groups], device=node.device)
        mask = torch.arange(padded.shape[1], device=node.device)[None, :] >= lengths[:, None]
        attended, _ = self.attention(padded, padded, padded, key_padding_mask=mask, need_weights=False)
        return torch.cat([self.norm(group + attended[index, : len(group)]) for index, group in enumerate(groups)])


class CompositionPolicy(nn.Module):
    def __init__(self, vocab: Vocab, configuration: Mapping[str, Any]) -> None:
        super().__init__()
        hidden = int(configuration["hidden"])
        categorical = int(configuration["categorical"])
        layers = int(configuration["layers"])
        dropout = float(configuration["dropout"])
        self.configuration = dict(configuration)
        global_attention = configuration["architecture"] in {"dual-gps", "hetero-transformer", "factor-transformer"}
        self.semantic = GraphEncoder(vocab, hidden, categorical, layers, dropout, global_attention=global_attention)
        self.interaction = (
            self.semantic
            if configuration["architecture"] == "hetero-transformer"
            else GraphEncoder(vocab, hidden, categorical, layers, dropout, global_attention=True)
        )
        self.factor_gate = nn.Sequential(nn.Linear(hidden, hidden), nn.Sigmoid())
        self.action = nn.Embedding(len(vocab.values["action"]) + 1, hidden)
        history_layer = nn.TransformerEncoderLayer(hidden, 4, hidden * 2, dropout=dropout, batch_first=True, norm_first=True, activation="gelu")
        self.history = nn.TransformerEncoder(history_layer, 1)
        self.delta = nn.Sequential(nn.Linear(24, hidden), nn.GELU(), nn.Linear(hidden, hidden))
        self.combine = nn.Sequential(nn.Linear(hidden * 5 + 3, hidden * 2), nn.GELU(), nn.Linear(hidden * 2, hidden))
        self.frontier = nn.MultiheadAttention(hidden, 4, dropout=dropout, batch_first=True)
        self.frontier_norm = nn.LayerNorm(hidden)
        self.score = nn.Linear(hidden, 1)
        self.tier = nn.Linear(hidden, 5)
        self.distance = nn.Linear(hidden, 1)
        self.cost = nn.Linear(hidden, 1)
        self.redundancy = nn.Linear(hidden, len(REDUNDANCY))

    def forward(self, batch):
        if self.configuration["architecture"] == "hetero-transformer":
            joint = self.semantic(batch["heterogeneous"])
            semantic = joint
            interaction = joint
        else:
            semantic = self.semantic(batch["semantic"])
            interaction = self.interaction(batch["interaction"])
        if self.configuration["architecture"] == "factor-transformer":
            interaction = interaction * (1.0 + self.factor_gate(interaction))
        history = self._sequence(batch["history"], batch["history_lengths"])
        action = self._action_pool(batch["action"], batch["action_group"], sum(batch["lengths"]))
        delta = self.delta(batch["delta"])
        repeats = torch.tensor(batch["lengths"], device=semantic.device)
        semantic = torch.repeat_interleave(semantic, repeats, 0)
        interaction = torch.repeat_interleave(interaction, repeats, 0)
        history = torch.repeat_interleave(history, repeats, 0)
        if not self.configuration.get("use_interaction", True):
            interaction = torch.zeros_like(interaction)
        if not self.configuration.get("use_history", True):
            history = torch.zeros_like(history)
        if not self.configuration.get("use_delta", True):
            delta = torch.zeros_like(delta)
        state = self.combine(torch.cat([
            semantic, interaction, history, action, delta,
            batch["option_numeric"],
        ], 1))
        if self.configuration.get("use_siblings", True):
            groups = torch.split(state, batch["lengths"])
            padded = nn.utils.rnn.pad_sequence(groups, batch_first=True)
            lengths = torch.tensor(batch["lengths"], device=state.device)
            mask = torch.arange(padded.shape[1], device=state.device)[None, :] >= lengths[:, None]
            attended, _ = self.frontier(padded, padded, padded, key_padding_mask=mask, need_weights=False)
            state = torch.cat([self.frontier_norm(group + attended[index, : len(group)]) for index, group in enumerate(groups)])
        return {
            "score": self.score(state).squeeze(1), "tier": self.tier(state),
            "distance": self.distance(state).squeeze(1), "cost": self.cost(state).squeeze(1),
            "redundancy": self.redundancy(state), "embedding": state,
        }

    def _sequence(self, tokens, lengths):
        groups = torch.split(self.action(tokens), lengths)
        padded = nn.utils.rnn.pad_sequence(groups, batch_first=True)
        size = torch.tensor(lengths, device=tokens.device)
        mask = torch.arange(padded.shape[1], device=tokens.device)[None, :] >= size[:, None]
        encoded = self.history(padded, src_key_padding_mask=mask)
        return encoded.masked_fill(mask[:, :, None], 0).sum(1) / size.clamp_min(1)[:, None]

    def _action_pool(self, tokens, groups, count):
        embedded = self.action(tokens)
        result = torch.zeros((count, embedded.shape[1]), device=tokens.device)
        result.index_add_(0, groups, embedded)
        sizes = torch.bincount(groups, minlength=count).clamp_min(1)[:, None]
        return result / sizes


def collate_decisions(decisions: list[Decision], vocab: Vocab) -> dict[str, Any]:
    action_tokens, action_groups, delta, numeric = [], [], [], []
    group = 0
    history_tokens, history_lengths = [], []
    for decision in decisions:
        tokens = [vocab.index("action", token) for action in decision.history for token in _action_tokens(action, "history")]
        tokens = tokens or [0]
        history_tokens.extend(tokens)
        history_lengths.append(len(tokens))
        for option in decision.options:
            tokens = [vocab.index("action", token) for token in (*_action_tokens(option.action, "current"), *_delta_tokens(option.delta))] or [0]
            action_tokens.extend(tokens)
            action_groups.extend([group] * len(tokens))
            delta.append(_delta_vector(option.delta))
            numeric.append([math.log1p(decision.depth), math.log1p(len(decision.options)), math.log1p(_action_arity(option.action))])
            group += 1
    return {
        "semantic": collate_graphs((item.semantic_graph for item in decisions), vocab),
        "interaction": collate_graphs((item.interaction_graph for item in decisions), vocab),
        "heterogeneous": collate_graphs(
            (_merge_graphs(item.semantic_graph, item.interaction_graph) for item in decisions), vocab,
        ),
        "history": torch.tensor(history_tokens, dtype=torch.long),
        "history_lengths": history_lengths,
        "action": torch.tensor(action_tokens, dtype=torch.long),
        "action_group": torch.tensor(action_groups, dtype=torch.long),
        "delta": torch.tensor(delta, dtype=torch.float32),
        "option_numeric": torch.tensor(numeric, dtype=torch.float32),
        "lengths": [len(item.options) for item in decisions],
    }


def _merge_graphs(
    semantic: Mapping[str, Any], interaction: Mapping[str, Any],
) -> dict[str, Any]:
    nodes = []
    edges = []
    roots = {}
    for namespace, graph in (("semantic", semantic), ("interaction", interaction)):
        local_ids = {}
        for index, raw in enumerate(_nodes(graph)):
            old = str(raw.get("id", index))
            new = f"{namespace}.{old}"
            local_ids[old] = new
            node = dict(raw)
            node["id"] = new
            attrs = dict(node.get("attributes", {}))
            attrs["graph_namespace"] = namespace
            node["attributes"] = attrs
            nodes.append(node)
            roots.setdefault(namespace, new)
        for raw in _edges(graph):
            source = raw.get("source")
            destination = raw.get("destination")
            if isinstance(source, int) and 0 <= source < len(_nodes(graph)):
                source = str(_nodes(graph)[source].get("id", source))
            if isinstance(destination, int) and 0 <= destination < len(_nodes(graph)):
                destination = str(_nodes(graph)[destination].get("id", destination))
            if str(source) not in local_ids or str(destination) not in local_ids:
                continue
            edge = dict(raw)
            edge["source"] = local_ids[str(source)]
            edge["destination"] = local_ids[str(destination)]
            edges.append(edge)
    if "semantic" in roots and "interaction" in roots:
        edges.append({
            "source": roots["semantic"],
            "destination": roots["interaction"],
            "relation": "PRODUCES_FOR",
            "ordering": "context",
        })
    return {"nodes": nodes, "edges": edges}


def _move(batch, device):
    return {key: (_move(value, device) if isinstance(value, dict) else value.to(device) if torch.is_tensor(value) else value) for key, value in batch.items()}


def train_model(
    train, validation, vocab, configuration, args, device, seed,
    pretraining_examples=(), pretrained_semantic_state=None, shared_pretraining=(),
):
    _seed(seed)
    model = CompositionPolicy(vocab, configuration).to(device)
    if pretrained_semantic_state is not None:
        model.semantic.load_state_dict(pretrained_semantic_state)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    pretraining = (
        list(shared_pretraining)
        if pretrained_semantic_state is not None
        else pretrain_semantic_encoder(model, pretraining_examples, vocab, args, device)
    )
    best = None
    history = []
    for epoch in range(args.epochs):
        model.train()
        shuffled = list(train)
        random.shuffle(shuffled)
        losses = []
        for start in range(0, len(shuffled), args.batch_size):
            decisions = shuffled[start : start + args.batch_size]
            batch = _move(collate_decisions(decisions, vocab), device)
            output = model(batch)
            tiers = torch.tensor([option.tier for item in decisions for option in item.options], device=device)
            distances = torch.tensor([math.log1p(option.distance) for item in decisions for option in item.options], device=device)
            costs = torch.tensor([math.log1p(option.cost) for item in decisions for option in item.options], device=device)
            redundancy = torch.tensor([option.redundancy for item in decisions for option in item.options], device=device)
            listwise, pairwise = [], []
            offset = 0
            for decision, length in zip(decisions, batch["lengths"], strict=True):
                scores = output["score"][offset : offset + length]
                target_values = torch.tensor([
                    8.0 * option.tier - 0.35 * option.distance - 0.05 * math.log1p(option.cost)
                    for option in decision.options
                ], device=device)
                target = F.softmax(target_values / args.oracle_temperature, 0)
                listwise.append(-(target * F.log_softmax(scores, 0)).sum())
                for left in range(length):
                    for right in range(length):
                        if decision.options[left].rank < decision.options[right].rank:
                            pairwise.append(F.softplus(args.pairwise_margin - (scores[left] - scores[right])))
                offset += length
            cost_aware = epoch == args.epochs - 1
            cost_weight = (
                0.0 if configuration.get("no_cost_labels") or not cost_aware else args.cost_weight
            )
            tier_targets = tiers.clamp_max(2) if configuration.get("no_retained_labels") else tiers
            loss = (
                args.listwise_weight * torch.stack(listwise).mean()
                + args.pairwise_weight * torch.stack(pairwise).mean()
                + args.tier_weight * F.cross_entropy(output["tier"], tier_targets)
                + args.distance_weight * F.smooth_l1_loss(output["distance"], distances)
                + cost_weight * F.smooth_l1_loss(output["cost"], costs)
                + args.redundancy_weight * F.cross_entropy(output["redundancy"], redundancy)
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            optimizer.step()
            losses.append(float(loss.detach()))
        scores = predict(model, validation, vocab, args.batch_size, device)
        validation_replay = replay_decisions(validation, scores)
        validation_recovery = validation_replay["recovery"]["0.3"]["useful"]
        objective = frontier_ndcg(validation, scores)
        history.append({
            "epoch": epoch + 1,
            "phase": "cost_aware_fine_tuning" if epoch == args.epochs - 1 else "composition_native_imitation",
            "loss": float(np.mean(losses)),
            "validation_frontier_ndcg": objective,
            "validation_useful_30": validation_recovery,
        })
        if best is None or objective > best[0]:
            best = (objective, {key: value.detach().cpu().clone() for key, value in model.state_dict().items()})
    if best is None:
        raise ValueError("no composition decisions were available for training")
    model.load_state_dict(best[1])
    return model, pretraining, history


def pretrain_semantic_encoder(model, examples, vocab, args, device):
    values = [item for item in examples if item.target in {0, 1}]
    if not values or args.pretrain_epochs <= 0:
        return []
    head = nn.Linear(args.hidden, 1).to(device)
    optimizer = torch.optim.AdamW(
        [*model.semantic.parameters(), *head.parameters()], lr=args.learning_rate, weight_decay=1e-4
    )
    history = []
    for epoch in range(args.pretrain_epochs):
        random.shuffle(values)
        losses = []
        model.train()
        for start in range(0, len(values), args.pretrain_batch_size):
            batch_examples = values[start : start + args.pretrain_batch_size]
            graph_batch = _move(collate_graphs((item.graph for item in batch_examples), vocab), device)
            labels = torch.tensor([item.target for item in batch_examples], dtype=torch.float32, device=device)
            logits = head(model.semantic(graph_batch)).squeeze(1)
            positives = max(float((labels > 0.5).sum()), 1.0)
            weight = torch.tensor(min(20.0, max(1.0, float((labels <= 0.5).sum()) / positives)), device=device)
            loss = F.binary_cross_entropy_with_logits(logits, labels, pos_weight=weight)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_([*model.semantic.parameters(), *head.parameters()], 2.0)
            optimizer.step()
            losses.append(float(loss.detach()))
        history.append({"epoch": epoch + 1, "examples": len(values), "loss": float(np.mean(losses))})
    return history


@torch.no_grad()
def predict(model, decisions, vocab, batch_size, device):
    model.eval()
    result = {}
    for start in range(0, len(decisions), batch_size):
        values = list(decisions[start : start + batch_size])
        output = model(_move(collate_decisions(values, vocab), device))
        offset = 0
        for decision in values:
            length = len(decision.options)
            score = output["score"][offset : offset + length]
            for option, value in zip(decision.options, score.cpu().tolist(), strict=True):
                result[option.action_id] = float(value)
            offset += length
    return result


def replay_decisions(decisions: Iterable[Decision], scores: Mapping[str, float]) -> dict[str, Any]:
    values = tuple(decisions)
    useful = sum(option.tier > 0 for item in values for option in item.options)
    composition = sum(option.tier > 0 for item in values if item.composition for option in item.options)
    ordered = sorted(
        (option for item in values for option in item.options),
        key=lambda option: (-float(scores.get(option.action_id, 0.0)), option.action_id),
    )
    total_cost = sum(option.cost for option in ordered)
    found_useful = found_composition = 0
    consumed = 0.0
    trajectory = [(0.0, 0, 0)]
    option_to_composition = {option.action_id: item.composition for item in values for option in item.options}
    for option in ordered:
        consumed += option.cost
        found_useful += int(option.tier > 0)
        found_composition += int(option.tier > 0 and option_to_composition[option.action_id])
        trajectory.append((consumed, found_useful, found_composition))
    curve = {}
    for checkpoint in CHECKPOINTS:
        budget = total_cost * checkpoint + 1e-9
        cost, found_u, found_c = max(
            (item for item in trajectory if item[0] <= budget), key=lambda item: item[0],
        )
        curve[str(checkpoint)] = {
            "useful": found_u / max(useful, 1),
            "composition": found_c / max(composition, 1),
            "cost": cost,
        }
    return {"useful": useful, "composition_useful": composition, "recovery": curve}


def frontier_ndcg(decisions: Iterable[Decision], scores: Mapping[str, float]) -> float:
    """Measure relative sibling ordering without post-search fields entering model inputs."""
    values = []
    for decision in decisions:
        if len(decision.options) < 2:
            continue
        ordered = sorted(
            decision.options,
            key=lambda option: (-float(scores.get(option.action_id, 0.0)), option.action_id),
        )
        ideal = sorted(decision.options, key=lambda option: option.rank)

        def gain(option: Option) -> float:
            return (2.0 ** option.tier - 1.0) + 1.0 / (1.0 + option.rank)

        def dcg(options: Iterable[Option]) -> float:
            return sum(gain(option) / math.log2(index + 2.0) for index, option in enumerate(options))

        denominator = dcg(ideal)
        values.append(dcg(ordered) / denominator if denominator > 0 else 1.0)
    return float(np.mean(values)) if values else 0.0


def relation_proposals(decisions: Iterable[Decision], scores: Mapping[str, float]) -> list[dict[str, Any]]:
    """Propose likely dominated/equivalent action pairs for an exact checker.

    This function intentionally returns evidence requests, not merged states.
    """
    proposals = []
    for decision in decisions:
        for left in range(len(decision.options)):
            for right in range(left + 1, len(decision.options)):
                a, b = decision.options[left], decision.options[right]
                same_delta = a.delta.get("delta_hash") == b.delta.get("delta_hash")
                near_score = abs(float(scores.get(a.action_id, 0.0)) - float(scores.get(b.action_id, 0.0))) < 0.05
                same_family = str(a.action.get("family")) == str(b.action.get("family"))
                same_operation = str(a.action.get("op")) == str(b.action.get("op"))
                if same_delta or (same_family and same_operation and near_score):
                    proposals.append({
                        "frontier_id": decision.frontier_id,
                        "left_action_id": a.action_id,
                        "right_action_id": b.action_id,
                        "proposed_relation": "semantic_equivalence" if same_delta else "dominance_or_commutativity",
                        "authority": "proposal_only",
                        "required_checker": "canonical_graph_then_z3_or_alive2",
                    })
    return proposals


def replay_trees(trees: Iterable[TraceTree], scores: Mapping[str, float]) -> dict[str, Any]:
    projects = []
    for tree in trees:
        total_cost = sum(_state_cost(item) for item in tree.states.values()) + sum(_terminal_cost(item) for item in tree.terminals.values())
        useful = {state for state, item in tree.terminals.items() if int(item["utility_tier"][1:]) >= 1}
        proof = {state for state, item in tree.terminals.items() if int(item["utility_tier"][1:]) >= 2}
        material = {state for state, item in tree.terminals.items() if int(item["utility_tier"][1:]) >= 3}
        retained = {state for state, item in tree.terminals.items() if int(item["utility_tier"][1:]) >= 4}
        composition = {
            state for state in useful
            if _terminal_is_composition(tree.states.get(state, {}))
        }
        queue = []
        sequence = 0
        root = tree.frontiers.get(None)
        if root is None:
            continue
        import heapq
        for option in root.options:
            heapq.heappush(queue, (-float(scores.get(option.action_id, 0.0)), sequence, option))
            sequence += 1
        discovered = {
            "useful": set(), "proof": set(), "material": set(), "retained": set(),
            "composition": set(),
        }
        calls = {"proof": 0, "compiler": 0, "benchmark": 0, "candidates": 0}
        trajectory = [
            (0.0, _curve_point(
                discovered, useful, proof, material, retained, composition, 0.0, calls,
            ))
        ]
        consumed = 0.0
        visited: set[str] = set()
        maximum_frontier = len(queue)
        while queue:
            negative_priority, _, option = heapq.heappop(queue)
            inherited_priority = -negative_priority
            state_id = option.child_state_id
            if state_id is None or state_id in visited:
                continue
            visited.add(state_id)
            state = tree.states.get(state_id or "", {})
            consumed += _state_cost(state)
            calls["candidates"] += 1
            terminal = tree.terminals.get(state_id or "")
            if terminal:
                consumed += _terminal_cost(terminal)
                cost = terminal.get("search_cost", {})
                calls["proof"] += int(cost.get("proof_calls", 0) or 0)
                calls["compiler"] += int(cost.get("compiler_invocation_count", 0) or 0)
                calls["benchmark"] += int(cost.get("benchmark_invocation_count", 0) or 0)
                for name, terminal_set in (("useful", useful), ("proof", proof), ("material", material), ("retained", retained)):
                    if state_id in terminal_set:
                        discovered[name].add(state_id)
                if state_id in composition:
                    discovered["composition"].add(state_id)
            child_frontier = tree.frontiers.get(state_id)
            if child_frontier:
                for child in child_frontier.options:
                    child_priority = (
                        float(scores[child.action_id])
                        if child.action_id in scores
                        else inherited_priority
                        if len(child_frontier.options) == 1
                        else 0.0
                    )
                    heapq.heappush(queue, (-child_priority, sequence, child))
                    sequence += 1
            maximum_frontier = max(maximum_frontier, len(queue))
            trajectory.append((
                consumed,
                _curve_point(
                    discovered, useful, proof, material, retained, composition, consumed, calls,
                ),
            ))
        curve = {}
        for checkpoint in CHECKPOINTS:
            budget = total_cost * checkpoint + 1e-9
            _, point = max(
                (item for item in trajectory if item[0] <= budget), key=lambda item: item[0],
            )
            curve[str(checkpoint)] = point
        first_discovery = {}
        for metric in ("useful", "proof_valid_distinct", "material", "retained", "composition"):
            first_cost = next(
                (cost for cost, point in trajectory if point[metric] not in {None, 0.0}),
                None,
            )
            first_discovery[metric] = {
                "cost": first_cost,
                "cost_fraction": first_cost / total_cost if first_cost is not None and total_cost else None,
            }
        projects.append({
            "project": tree.project, "root_id": tree.root_id, "total_cost": total_cost,
            "useful": len(useful), "proof": len(proof), "material": len(material),
            "retained": len(retained), "composition": len(composition),
            "recovery": curve, "maximum_frontier_size": maximum_frontier,
            "transposition_count": len(tree.transpositions),
            "first_discovery": first_discovery,
        })
    return _aggregate_tree_replays(projects)


def _curve_point(discovered, useful, proof, material, retained, composition, cost, calls):
    return {
        "useful": len(discovered["useful"]) / max(len(useful), 1),
        "proof_valid_distinct": len(discovered["proof"]) / max(len(proof), 1),
        "material": len(discovered["material"]) / len(material) if material else None,
        "retained": len(discovered["retained"]) / len(retained) if retained else None,
        "composition": len(discovered["composition"]) / len(composition) if composition else None,
        "cost": cost,
        **calls,
    }


def _aggregate_tree_replays(rows):
    totals = {
        key: sum(item[key] for item in rows)
        for key in ("useful", "proof", "material", "retained", "composition")
    }
    recovery = {}
    for checkpoint in CHECKPOINTS:
        key = str(checkpoint)
        recovery[key] = {
            metric: sum((item["recovery"][key][metric] or 0) * item[count] for item in rows) / totals[count] if totals[count] else None
            for metric, count in (("useful", "useful"), ("proof_valid_distinct", "proof"), ("material", "material"), ("retained", "retained"))
        }
        recovery[key]["composition"] = (
            sum((item["recovery"][key]["composition"] or 0) * item["composition"] for item in rows)
            / totals["composition"] if totals["composition"] else None
        )
        recovery[key].update({
            field: sum(item["recovery"][key][field] for item in rows)
            for field in ("cost", "proof", "compiler", "benchmark", "candidates")
        })
    return {
        "roots": len(rows), "terminal_counts": totals, "recovery": recovery,
        "maximum_frontier_size": max((item["maximum_frontier_size"] for item in rows), default=0),
        "exact_transposition_reductions": sum(item["transposition_count"] for item in rows),
        "first_discovery": {
            metric: _aggregate_first_discovery(rows, metric)
            for metric in ("useful", "proof_valid_distinct", "material", "retained", "composition")
        },
    }


def _aggregate_first_discovery(rows, metric):
    observed = [
        item["first_discovery"][metric]
        for item in rows
        if item["first_discovery"][metric]["cost"] is not None
    ]
    return {
        "roots_evaluable": len(observed),
        "mean_cost": sum(item["cost"] for item in observed) / len(observed) if observed else None,
        "mean_cost_fraction": (
            sum(item["cost_fraction"] for item in observed) / len(observed) if observed else None
        ),
        "maximum_cost_fraction": max(
            (item["cost_fraction"] for item in observed), default=None,
        ),
    }


def baseline_scores(decisions, kind, historical=None):
    result = {}
    for decision in decisions:
        for index, option in enumerate(decision.options):
            if kind == "fifo":
                value = -index
            elif kind == "random":
                value = int(hashlib.sha256(option.action_id.encode()).hexdigest()[:12], 16) / 2**48
            elif kind == "handwritten":
                text = json.dumps(option.action).lower()
                value = 1.5 * int("fuse" in text or "retain" in text) - 0.2 * len(option.delta) - 0.05 * decision.depth
            elif kind == "rc24":
                tokens = _action_tokens(option.action, "current")
                values = [historical.get(token, 0.5) for token in tokens] if historical else [0.5]
                value = sum(values) / len(values)
            elif kind == "oracle":
                value = 100 * option.tier - option.distance - 0.01 * option.cost
            else:
                raise ValueError(kind)
            result[option.action_id] = value
    return result


def load_phase_a_scores(
    decisions: Iterable[Decision], checkpoint_directory: Path, device: torch.device,
) -> dict[str, float]:
    """Run the frozen Phase-A GPS policy on a source-free compatibility projection.

    The projection intentionally contains only parent graph, ordered history, action, and
    pre-expansion state-delta information. Completed-search utility and cost labels are absent.
    """
    spec = importlib.util.spec_from_file_location(
        "vladder_contextual_phase_a_frozen", ROOT / "scripts" / "contextual_search_policy.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result: dict[str, float] = {}
    values = tuple(decisions)
    for project in sorted({item.project for item in values}):
        checkpoint_project = "llama_cpp" if project == "llama.cpp" else project
        path = checkpoint_directory / f"fold-{checkpoint_project}-gps-frontier.pt"
        if not path.is_file():
            raise FileNotFoundError(f"missing frozen Phase-A GPS checkpoint: {path}")
        checkpoint = torch.load(path, map_location=device, weights_only=True)
        vocab = module.SP.Vocab(dict(checkpoint["vocab"]))
        configuration = checkpoint["configuration"]
        model = module.ContextualPolicy(
            vocab,
            architecture=str(configuration["architecture"]),
            hidden=int(configuration["hidden"]),
            categorical=int(configuration["categorical"]),
            layers=int(configuration["layers"]),
            dropout=0.0,
            use_history=bool(configuration["use_history"]),
            use_siblings=bool(configuration["use_siblings"]),
        ).to(device)
        model.load_state_dict(checkpoint["state_dict"])
        projected = tuple(
            _phase_a_decision(item, module)
            for item in values if item.project == project
        )
        result.update(module.predict_scores(model, projected, vocab, 32, device))
        del model
    return result


def _phase_a_decision(decision: Decision, module: Any) -> Any:
    parent_id = f"phase-a-parent:{decision.frontier_id}"
    parent_action = decision.history[-1] if decision.history else {"family": "root", "op": "enter"}
    parent = _phase_a_example(
        module, decision, parent_id, None, parent_action, decision.semantic_graph,
        decision.history[:-1], target=None,
    )
    options = tuple(
        _phase_a_example(
            module, decision, option.action_id, parent_id, option.action,
            decision.semantic_graph, decision.history, target=int(option.tier > 0), delta=option.delta,
        )
        for option in decision.options
    )
    return module.Decision(
        project=decision.project,
        root_id=decision.root_id,
        search_id=decision.frontier_id,
        parent=parent,
        options=options,
        distance=tuple(int(option.distance) if option.distance < 32 else None for option in decision.options),
        useful=tuple(int(option.tier > 0) for option in decision.options),
        retained=tuple(int(option.tier >= 4) for option in decision.options),
        costs=tuple(option.cost for option in decision.options),
        redundancy=tuple(min(option.redundancy, len(module.REDUNDANCY) - 1) for option in decision.options),
        oracle_index=min(range(len(decision.options)), key=lambda index: decision.options[index].rank),
    )


def _phase_a_example(
    module: Any,
    decision: Decision,
    branch_id: str,
    parent_id: str | None,
    action: Mapping[str, Any],
    graph: Mapping[str, Any],
    history: Iterable[Mapping[str, Any]],
    *,
    target: int | None,
    delta: Mapping[str, Any] | None = None,
) -> Any:
    return module.SP.Example(
        project=decision.project,
        root_id=decision.root_id,
        search_id=decision.frontier_id,
        branch_id=branch_id,
        parent_branch_id=parent_id,
        graph=_phase_a_graph(graph),
        stage="composition",
        depth=decision.depth,
        baseline=str(action.get("choice")) == "baseline",
        action=_phase_a_action(action),
        lineage=tuple(_phase_a_action(item) for item in history),
        target=target,
        policy_surface=True,
        context_quality="partial_state",
        state_features={
            "numeric": [
                {"name": "depth", "value": decision.depth},
                {"name": "selected_count", "value": decision.depth},
                {"name": "remaining_count", "value": max(0, len(decision.options) - 1)},
                {"name": "action_count", "value": len(tuple(history))},
                {"name": "region_count", "value": len(decision.options)},
            ]
        },
        semantic_delta={
            "numeric": [
                {"name": "width", "value": len((delta or {}).get("nodes_added", ()))},
                {"name": "tile", "value": len((delta or {}).get("edges_added", ()))},
            ]
        },
        children_status="exhaustive",
        emitted_child_count=0,
        expected_child_count=0,
        tree_complete=True,
    )


def _phase_a_action(action: Mapping[str, Any]) -> dict[str, Any]:
    categorical = []
    numeric = []
    for key, value in sorted(action.items()):
        if key in {"family", "family_version", "primitives"}:
            continue
        if isinstance(value, bool):
            categorical.append({"name": str(key), "value": str(value).lower()})
        elif isinstance(value, (int, float)):
            numeric.append({"name": str(key), "value": float(value)})
        elif isinstance(value, str):
            categorical.append({"name": str(key), "value": value})
    primitive = str(action.get("op") or action.get("rule") or "unknown")
    return {
        "family": str(action.get("family") or "unknown"),
        "family_version": str(action.get("family_version") or "unversioned"),
        "primitives": list(action.get("primitives", ())) or [primitive],
        "numeric_parameters": numeric,
        "categorical_parameters": categorical,
    }


def _phase_a_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    nodes = [dict(item) for item in graph.get("nodes", ()) if isinstance(item, Mapping)]
    if not nodes:
        nodes = [{"id": "empty", "kind": "Empty", "operation": "empty", "output_type": "none"}]
    identities = {str(item.get("id", index)): index for index, item in enumerate(nodes)}
    node_features = []
    for item in nodes:
        attrs = item.get("attributes") if isinstance(item.get("attributes"), Mapping) else {}
        node_features.append({
            "kind": str(item.get("kind", "Other")),
            "operation": str(item.get("operation", item.get("kind", "other"))),
            "type_class": str(item.get("output_type", "other")),
            "bit_width": int(attrs.get("bit_width", 0) or 0),
            "vector_lanes": int(attrs.get("vector_lanes", 0) or 0),
            "numeric_features": [],
            "categorical_features": [],
        })
    edge_index = [[], []]
    edge_features = []
    for edge in graph.get("edges", ()):
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("source")
        destination = edge.get("destination")
        left = source if isinstance(source, int) else identities.get(str(source))
        right = destination if isinstance(destination, int) else identities.get(str(destination))
        if left is None or right is None or not (0 <= left < len(nodes) and 0 <= right < len(nodes)):
            continue
        edge_index[0].append(left)
        edge_index[1].append(right)
        edge_features.append({
            "relation": str(edge.get("relation", "other")),
            "ordering": str(edge.get("ordering", "other")),
        })
    return {
        "node_features": node_features,
        "edge_index": edge_index,
        "edge_features": edge_features,
        "obligations": list(graph.get("obligations", ())),
        "effects": list(graph.get("effects", ())),
        "protocols": list(graph.get("protocols", ())),
        "claims": list(graph.get("claims", ())),
    }


def _normalized_topology_hash(graph: Mapping[str, Any]) -> str:
    nodes = [dict(item) for item in graph.get("nodes", ()) if isinstance(item, Mapping)]
    identities = {str(item.get("id", index)): index for index, item in enumerate(nodes)}
    labels = [
        hashlib.sha256(json.dumps((
            str(item.get("kind", "Other")),
            str(item.get("operation", item.get("kind", "other"))),
            str(item.get("output_type", "other")),
        ), separators=(",", ":")).encode()).hexdigest()
        for item in nodes
    ]
    normalized_edges: list[tuple[int, int, str, str]] = []
    for edge in graph.get("edges", ()):
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("source")
        destination = edge.get("destination")
        left = source if isinstance(source, int) else identities.get(str(source), -1)
        right = destination if isinstance(destination, int) else identities.get(str(destination), -1)
        normalized_edges.append((
            int(left), int(right), str(edge.get("relation", "other")),
            str(edge.get("ordering", "other")),
        ))
    # Source identifiers and source order are excluded. Iterative neighborhood labels make
    # equivalent normalized topologies collide even when frontends enumerate nodes differently.
    for _ in range(max(1, min(8, len(nodes)))):
        refined = []
        for index, label in enumerate(labels):
            incoming = sorted(
                (relation, ordering, labels[left])
                for left, right, relation, ordering in normalized_edges if right == index and left >= 0
            )
            outgoing = sorted(
                (relation, ordering, labels[right])
                for left, right, relation, ordering in normalized_edges if left == index and right >= 0
            )
            refined.append(hashlib.sha256(json.dumps(
                {"self": label, "incoming": incoming, "outgoing": outgoing},
                sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest())
        if refined == labels:
            break
        labels = refined
    edge_signatures = sorted(
        (labels[left], labels[right], relation, ordering)
        for left, right, relation, ordering in normalized_edges if left >= 0 and right >= 0
    )
    semantic_signatures = {
        "obligations": sorted(
            (
                str(item.get("category", "other")), str(item.get("scope", "other")),
                str(item.get("proof_method", "other")),
            )
            for item in graph.get("obligations", ()) if isinstance(item, Mapping)
        ),
        "effects": sorted(
            (str(item.get("kind", "other")), str(item.get("authority", "other")))
            for item in graph.get("effects", ()) if isinstance(item, Mapping)
        ),
        "protocols": sorted(
            (str(item.get("kind", "other")), str(item.get("consistency", "other")))
            for item in graph.get("protocols", ()) if isinstance(item, Mapping)
        ),
    }
    return hashlib.sha256(json.dumps(
        {"nodes": sorted(labels), "edges": edge_signatures, **semantic_signatures},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def _topology_projects(decisions: Iterable[Decision]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for decision in decisions:
        result[decision.root_topology_hash].add(decision.project)
    return result


def _normalize_project_id(value: str) -> str:
    return "llama.cpp" if value in {"llama", "llama_cpp", "llama.cpp"} else value


def load_historical_examples(progress_paths, manifest_paths):
    if not progress_paths or not manifest_paths:
        return [], None
    spec = importlib.util.spec_from_file_location("vladder_search_pruner_native", ROOT / "scripts" / "search_pruner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    examples = module.load_campaign_examples(progress_paths, manifest_paths)
    return examples, module


def historical_action_prior(examples, module):
    if not examples or module is None:
        return {}
    counts: dict[str, list[int]] = defaultdict(lambda: [1, 2])
    for example in examples:
        if example.target not in {0, 1}:
            continue
        for token in _action_tokens(example.action, "current"):
            counts[token][0] += int(example.target)
            counts[token][1] += 1
    return {token: useful / total for token, (useful, total) in counts.items()}


def configurations(requested: str):
    all_values = {
        "semantic-only": dict(architecture="dual-gps", use_interaction=False, use_history=False, use_siblings=False, use_delta=False),
        "semantic-history": dict(architecture="dual-gps", use_interaction=False, use_history=True, use_siblings=False, use_delta=False),
        "semantic-history-siblings": dict(architecture="dual-gps", use_interaction=False, use_history=True, use_siblings=True, use_delta=False),
        "interaction-frontier": dict(architecture="dual-gps", use_interaction=True, use_history=True, use_siblings=True, use_delta=True),
        "hetero-transformer": dict(architecture="hetero-transformer", use_interaction=True, use_history=True, use_siblings=True, use_delta=True),
        "factor-transformer": dict(architecture="factor-transformer", use_interaction=True, use_history=True, use_siblings=True, use_delta=True),
        "no-interaction": dict(architecture="factor-transformer", use_interaction=False, use_history=True, use_siblings=True, use_delta=True),
        "no-history": dict(architecture="factor-transformer", use_interaction=True, use_history=False, use_siblings=True, use_delta=True),
        "no-siblings": dict(architecture="factor-transformer", use_interaction=True, use_history=True, use_siblings=False, use_delta=True),
        "no-delta": dict(architecture="factor-transformer", use_interaction=True, use_history=True, use_siblings=True, use_delta=False),
        "no-cost-labels": dict(architecture="factor-transformer", use_interaction=True, use_history=True, use_siblings=True, use_delta=True, no_cost_labels=True),
        "no-retained-labels": dict(architecture="factor-transformer", use_interaction=True, use_history=True, use_siblings=True, use_delta=True, no_retained_labels=True),
    }
    return all_values if requested == "all" else {name: all_values[name] for name in requested.split(",")}


def split(decisions, heldout):
    heldout_topologies = {
        item.root_topology_hash for item in decisions if item.project == heldout
    }
    train = [
        item for item in decisions
        if item.project != heldout and item.root_topology_hash not in heldout_topologies
    ]
    roots = sorted({item.root_id for item in train})
    validation_roots = {root for root in roots if int(hashlib.sha256(root.encode()).hexdigest()[:8], 16) % 5 == 0}
    if not validation_roots and roots:
        validation_roots = {roots[-1]}
    return [item for item in train if item.root_id not in validation_roots], [item for item in train if item.root_id in validation_roots]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rc24-progress", type=Path, action="append", default=[])
    parser.add_argument("--rc24-manifest", type=Path, action="append", default=[])
    parser.add_argument(
        "--phase-a-run", type=Path,
        default=Path(tempfile.gettempdir()) / "vladder-contextual-phase-a-v4",
    )
    parser.add_argument("--variants", default="all")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--pretrain-epochs", type=int, default=1)
    parser.add_argument("--pretrain-batch-size", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--hidden", type=int, default=192)
    parser.add_argument("--categorical", type=int, default=48)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--dropout", type=float, default=0.10)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--oracle-temperature", type=float, default=0.7)
    parser.add_argument("--listwise-weight", type=float, default=1.0)
    parser.add_argument("--pairwise-weight", type=float, default=0.6)
    parser.add_argument("--pairwise-margin", type=float, default=0.75)
    parser.add_argument("--tier-weight", type=float, default=0.25)
    parser.add_argument("--distance-weight", type=float, default=0.08)
    parser.add_argument("--cost-weight", type=float, default=0.08)
    parser.add_argument("--redundancy-weight", type=float, default=0.06)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    decisions, trees, traces = load_native_corpus(args.corpus)
    if not decisions:
        raise SystemExit("no complete composition-native decisions found")
    projects = sorted({item.project for item in decisions})
    historical_examples, historical_module = load_historical_examples(args.rc24_progress, args.rc24_manifest)
    args.output.mkdir(parents=True, exist_ok=True)
    baselines = {
        name: replay_trees(trees, baseline_scores(decisions, name))
        for name in ("fifo", "random", "handwritten", "oracle")
    }
    rc24_scores = {}
    for project in projects:
        prior = historical_action_prior(
            [
                item for item in historical_examples
                if _normalize_project_id(str(item.project)) != project
            ],
            historical_module,
        )
        rc24_scores.update(baseline_scores(
            tuple(item for item in decisions if item.project == project), "rc24", prior,
        ))
    baselines["rc24"] = replay_trees(trees, rc24_scores)
    baselines["phase-a-gps"] = replay_trees(
        trees, load_phase_a_scores(decisions, args.phase_a_run, device),
    )
    folds = []
    variants = configurations(args.variants)
    for heldout in projects:
        train, validation = split(decisions, heldout)
        test = tuple(item for item in decisions if item.project == heldout)
        raw_training_count = sum(item.project != heldout for item in decisions)
        topology_excluded_count = raw_training_count - len(train) - len(validation)
        test_trees = tuple(item for item in trees if item.project == heldout)
        fold_pretraining = [
            item for item in historical_examples
            if _normalize_project_id(str(item.project)) != heldout
        ]
        vocab = Vocab.build(train, fold_pretraining)
        pretraining_configuration = {
            "architecture": "dual-gps", "use_interaction": False,
            "use_history": False, "use_siblings": False, "use_delta": False,
            "hidden": args.hidden, "categorical": args.categorical,
            "layers": args.layers, "dropout": args.dropout,
        }
        _seed(args.seed + int(hashlib.sha256(heldout.encode()).hexdigest()[:8], 16))
        pretraining_model = CompositionPolicy(vocab, pretraining_configuration).to(device)
        shared_pretraining = pretrain_semantic_encoder(
            pretraining_model, fold_pretraining, vocab, args, device,
        )
        pretrained_semantic_state = {
            key: value.detach().cpu().clone()
            for key, value in pretraining_model.semantic.state_dict().items()
        }
        del pretraining_model
        for offset, (name, specific) in enumerate(variants.items()):
            configuration = {
                **specific, "hidden": args.hidden, "categorical": args.categorical,
                "layers": args.layers, "dropout": args.dropout,
            }
            model, pretraining, history = train_model(
                train, validation, vocab, configuration, args, device,
                args.seed + offset * 1009, (), pretrained_semantic_state, shared_pretraining,
            )
            scores = predict(model, test, vocab, args.batch_size, device)
            replay = replay_trees(test_trees, scores)
            proposals = relation_proposals(test, scores)
            checkpoint = args.output / f"fold-{heldout}-{name}.pt"
            torch.save({
                "schema_version": SCHEMA, "state_dict": model.state_dict(),
                "vocab": vocab.values, "configuration": configuration,
                "authority": "priority-only; no semantic deletion",
            }, checkpoint)
            folds.append({
                "heldout_project": heldout, "variant": name,
                "topology_leakage_excluded_decisions": topology_excluded_count,
                "parameters": sum(parameter.numel() for parameter in model.parameters()),
                "encoder_pretraining": pretraining, "history": history,
                "replay": replay, "equivalence_dominance_proposals": len(proposals),
                "checkpoint": str(checkpoint),
            })
            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()
    aggregate = {}
    for name in variants:
        selected = [item for item in folds if item["variant"] == name]
        useful_total = sum(item["replay"]["terminal_counts"]["useful"] for item in selected)
        aggregate[name] = {
            "parameters": selected[0]["parameters"] if selected else 0,
            "maximum_frontier_size": max(
                (item["replay"]["maximum_frontier_size"] for item in selected), default=0,
            ),
            "recovery": {
                str(checkpoint): {
                    **{
                        metric: sum(
                            (item["replay"]["recovery"][str(checkpoint)][metric] or 0)
                            * item["replay"]["terminal_counts"][count]
                            for item in selected
                        ) / max(sum(item["replay"]["terminal_counts"][count] for item in selected), 1)
                        for metric, count in (
                            ("useful", "useful"),
                            ("proof_valid_distinct", "proof"),
                            ("material", "material"),
                            ("retained", "retained"),
                            ("composition", "composition"),
                        )
                    },
                    **{
                        field: sum(
                            item["replay"]["recovery"][str(checkpoint)][field]
                            for item in selected
                        )
                        for field in ("cost", "proof", "compiler", "benchmark", "candidates")
                    },
                }
                for checkpoint in CHECKPOINTS
            },
        }
    full_variants = tuple(
        name for name in ("interaction-frontier", "hetero-transformer", "factor-transformer")
        if name in aggregate
    )
    if not full_variants:
        raise SystemExit("evaluation requires at least one full interaction-aware model")
    best = max(
        full_variants,
        key=lambda name: (
            aggregate[name]["recovery"]["0.3"]["composition"] or 0.0,
            aggregate[name]["recovery"]["0.3"]["useful"],
            aggregate[name]["recovery"]["0.3"]["proof_valid_distinct"],
        ),
    )
    best30 = aggregate[best]["recovery"]["0.3"]
    composition30 = best30["composition"] or 0.0
    retained_count = sum(len(item.terminals) and sum(int(value["utility_tier"][1:]) >= 4 for value in item.terminals.values()) for item in trees)
    phase_a_30 = baselines["phase-a-gps"]["recovery"]["0.3"]
    phase_a_composition30 = phase_a_30["composition"] or 0.0
    gate_a = composition30 >= 0.80 and composition30 > phase_a_composition30 + 0.01
    gate_b = best30["useful"] >= 0.95
    gate_c = retained_count == 0 or best30["retained"] == 1.0
    material_count = sum(sum(int(value["utility_tier"][1:]) >= 3 for value in item.terminals.values()) for item in trees)
    gate_c = gate_c and (material_count == 0 or best30["material"] == 1.0)
    semantic30 = aggregate.get(
        "semantic-only", {"recovery": {"0.3": {"useful": -1, "composition": -1}}}
    )["recovery"]["0.3"]
    representation_minimum_delta = 0.01
    full_beats_semantic = (
        best30["useful"] >= semantic30["useful"] + representation_minimum_delta
        and composition30 >= (semantic30.get("composition") or 0.0) + representation_minimum_delta
    )
    gate_d = gate_a and gate_b and gate_c and full_beats_semantic
    if gate_d:
        recommendation = "SCALE_CAMPAIGN"
    elif best30["useful"] < 0.90 or composition30 < 0.80 or not full_beats_semantic:
        recommendation = "ABANDON_LEARNED_SEARCH_AS_PRIMARY_REDUCTION"
    else:
        recommendation = "ITERATE_REPRESENTATION"
    report = {
        "schema_version": "vladder-composition-native-evaluation-v1",
        "authority": "learned ordering only; exact/formal systems control elimination",
        "device": str(device), "roots": len(trees), "decisions": len(decisions),
        "composition_decisions": sum(item.composition for item in decisions),
        "frontier_actions": sum(len(item.options) for item in decisions),
        "projects": projects, "native_trace_count": len(traces),
        "split_integrity": {
            "normalized_topology_hash_count": len({item.root_topology_hash for item in decisions}),
            "cross_project_topology_hash_count": sum(
                len(projects_for_hash) > 1
                for projects_for_hash in _topology_projects(decisions).values()
            ),
            "policy": "matching normalized held-out topologies are excluded from training",
        },
        "rc24_pretraining_examples": len(historical_examples),
        "retained_terminal_count": retained_count, "material_terminal_count": material_count,
        "exact_reductions": {
            "transpositions": sum(len(item.transpositions) for item in trees),
            "state_dispositions": dict(sorted(Counter(
                str(state.get("disposition", "unknown"))
                for trace in traces for state in trace.get("states", ())
            ).items())),
            "terminal_classes": dict(sorted(Counter(
                str(terminal.get("terminal_class", "unknown"))
                for trace in traces for terminal in trace.get("terminals", ())
            ).items())),
            "learned_reduction_count": 0,
        },
        "baselines": baselines, "variants": aggregate, "best_variant": best,
        "gates": {
            "A_composition_80_and_phase_a_gain_at_30": {
                "observed": composition30,
                "phase_a_gps": phase_a_composition30,
                "minimum_material_delta": 0.01,
                "passed": gate_a,
            },
            "B_useful_95_at_30": {"observed": best30["useful"], "passed": gate_b},
            "C_material_retained_100_at_30": {"observed_material": best30["material"], "observed_retained": best30["retained"], "evaluable": bool(material_count or retained_count), "passed": gate_c},
            "D_scale_authorization": {
                "interaction_beats_semantic": full_beats_semantic,
                "minimum_material_delta": representation_minimum_delta,
                "passed": gate_d,
            },
        },
        "recommendation": recommendation, "folds": folds,
    }
    (args.output / "evaluation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    with (args.output / "recovery-curves.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "policy", "kind", "cost_fraction", "useful", "composition",
            "proof_valid_distinct", "material", "retained",
        ))
        writer.writeheader()
        for kind, policies in (("baseline", baselines), ("model", aggregate)):
            for name, value in sorted(policies.items()):
                for checkpoint in CHECKPOINTS:
                    point = value["recovery"][str(checkpoint)]
                    writer.writerow({
                        "policy": name, "kind": kind, "cost_fraction": checkpoint,
                        **{field: point.get(field) for field in (
                            "useful", "composition", "proof_valid_distinct", "material", "retained",
                        )},
                    })
    (args.output / "transposition-report.json").write_text(json.dumps({
        "schema_version": "vladder-composition-transposition-report-v1",
        "exact_transpositions": report["exact_reductions"]["transpositions"],
        "verified_equivalence_reductions": 0,
        "learned_reductions": 0,
        "authority": "exact canonicalization only; learned policy changes ordering",
    }, indent=2, sort_keys=True) + "\n")
    (args.output / "recommendation.json").write_text(json.dumps({
        "schema_version": "vladder-composition-scale-recommendation-v1",
        "recommendation": recommendation,
        "gates": report["gates"],
        "best_variant": best,
    }, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"best_variant": best, "recovery_30": best30, "composition_30": composition30, "recommendation": recommendation}, indent=2))
    return 0


def _read_json(path: Path):
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as source:
        return json.load(source)


def _action_tokens(action: Mapping[str, Any], prefix: str) -> tuple[str, ...]:
    result = []
    for key, value in sorted(action.items()):
        if isinstance(value, (str, int, float, bool)):
            result.append(f"{prefix}.{key}={value}")
        elif isinstance(value, (list, tuple)):
            result.extend(f"{prefix}.{key}={item}" for item in value[:16])
    return tuple(result or (f"{prefix}.unknown",))


def _delta_tokens(delta: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(f"delta.{key}={len(value) if isinstance(value, (list, dict)) else bool(value)}" for key, value in sorted(delta.items()) if key != "delta_hash")


def _delta_vector(delta: Mapping[str, Any]) -> list[float]:
    fields = (
        "nodes_added", "nodes_removed", "nodes_changed", "edges_added", "edges_removed", "edges_changed",
        "lifetime_changes", "representation_changes", "owner_changes", "contracts_created", "contracts_invalidated",
        "materializations_added", "materializations_removed", "cross_tu_boundaries_affected", "semantic_changes",
    )
    result = [math.log1p(len(delta.get(field, ()))) for field in fields]
    result += [
        float(bool(delta.get("lifetime_changes"))), float(bool(delta.get("owner_changes"))),
        float(bool(delta.get("materializations_added"))), float(bool(delta.get("materializations_removed"))),
        float(bool(delta.get("contracts_created"))), float(bool(delta.get("contracts_invalidated"))),
        float(bool(delta.get("cross_tu_boundaries_affected"))), math.log1p(sum(len(value) for value in delta.values() if isinstance(value, (list, dict)))),
        1.0,
    ]
    return result[:24]


def _action_arity(action: Mapping[str, Any]) -> int:
    return max(1, sum(len(value) if isinstance(value, (list, tuple)) else 1 for value in action.values()))


def _composition_action(action: Mapping[str, Any]) -> bool:
    text = json.dumps(action, sort_keys=True).lower()
    return any(token in text for token in ("compose", "fuse", "fusion", "retain", "lifetime", "interleave", "schedule", "selected"))


def _terminal_is_composition(state: Mapping[str, Any]) -> bool:
    if str(state.get("stage")) == "composition":
        return True
    history = state.get("ordered_action_history", ())
    return len(history) >= 2 or any(
        _composition_action(item) for item in history if isinstance(item, Mapping)
    )


def _state_cost(state: Mapping[str, Any]) -> float:
    if state.get("disposition") in {"canonical_duplicate", "verified_equivalent", "impossible", "dominated"}:
        return 0.0
    cost = state.get("search_cost", {})
    return max(1e-6, float(cost.get("expansion_wall_ms") or cost.get("node_expansions") or 1.0))


def _terminal_cost(terminal: Mapping[str, Any]) -> float:
    cost = terminal.get("search_cost", {})
    return max(0.0, float(cost.get("evaluation_wall_ms") or 0.0))


def _seed(value: int) -> None:
    random.seed(value)
    np.random.seed(value)
    torch.manual_seed(value)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(value)


if __name__ == "__main__":
    raise SystemExit(main())
