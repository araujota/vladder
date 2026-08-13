#!/usr/bin/env python3
"""Train and replay vLadder's contextual best-first search policy.

The model orders legal sibling actions. It never supplies deletion, legality, equivalence, or
performance authority. Phase-A training reconstructs complete frontiers from RC24 v3 traces.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Iterable

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
    raise SystemExit("contextual-search-policy requires `pip install 'vladder[ml]'`") from error

SPEC = importlib.util.spec_from_file_location("vladder_search_pruner_context", ROOT / "scripts" / "search_pruner.py")
assert SPEC and SPEC.loader
SP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SP
SPEC.loader.exec_module(SP)


SCHEMA = "vladder-contextual-search-policy-v1"
CHECKPOINTS = (0.01, 0.05, 0.10, 0.20, 0.30, 0.50, 1.0)
REDUNDANCY = ("unique", "canonical-equivalent", "compiler-identical", "dominated", "exhausted-dead", "other")


@dataclass(frozen=True)
class Decision:
    project: str
    root_id: str
    search_id: str
    parent: object
    options: tuple[object, ...]
    distance: tuple[int | None, ...]
    useful: tuple[int, ...]
    retained: tuple[int, ...]
    costs: tuple[float, ...]
    redundancy: tuple[int, ...]
    oracle_index: int


def load_decisions(examples: list[object]) -> tuple[Decision, ...]:
    by_scope: dict[tuple[str, str], list[object]] = defaultdict(list)
    by_id = {(item.project, item.root_id, item.branch_id): item for item in examples}
    children: dict[tuple[str, str, str], list[object]] = defaultdict(list)
    for item in examples:
        by_scope[(item.project, item.root_id)].append(item)
        if item.parent_branch_id is not None:
            children[(item.project, item.root_id, item.parent_branch_id)].append(item)

    distances: dict[tuple[str, str, str], int | None] = {}
    for scope, values in by_scope.items():
        local_children = {item.branch_id: children.get((scope[0], scope[1], item.branch_id), ()) for item in values}
        visiting: set[str] = set()

        def distance(branch_id: str) -> int | None:
            key = (*scope, branch_id)
            if key in distances:
                return distances[key]
            if branch_id in visiting:
                return None
            visiting.add(branch_id)
            item = by_id[key]
            descendants = local_children[branch_id]
            direct = _direct_useful(item) and not descendants
            child_values = [distance(child.branch_id) for child in descendants]
            known = [value for value in child_values if value is not None]
            result = 0 if direct else 1 + min(known) if known else None
            visiting.remove(branch_id)
            distances[key] = result
            return result

        for item in values:
            distance(item.branch_id)

    decisions = []
    for (project, root_id, parent_id), raw_options in children.items():
        parent = by_id.get((project, root_id, parent_id))
        options = tuple(item for item in raw_options if item.policy_surface)
        if parent is None or len(options) < 2:
            continue
        if not (
            parent.children_status == "exhaustive"
            and parent.emitted_child_count == len(raw_options)
            and parent.expected_child_count == len(raw_options)
        ):
            continue
        option_distances = tuple(distances[(project, root_id, item.branch_id)] for item in options)
        useful = tuple(int(item.target == 1) for item in options)
        retained = tuple(int(bool((item.descendant_utility or {}).get("retained"))) for item in options)
        costs = tuple(float(item.subtree_cost) for item in options)
        redundancy = tuple(REDUNDANCY.index(_redundancy(item)) for item in options)
        ordering = sorted(
            range(len(options)),
            key=lambda index: (
                -retained[index],
                -useful[index],
                option_distances[index] if option_distances[index] is not None else 10**9,
                costs[index],
                options[index].branch_id,
            ),
        )
        decisions.append(
            Decision(
                project=project,
                root_id=root_id,
                search_id=parent.search_id,
                parent=parent,
                options=options,
                distance=option_distances,
                useful=useful,
                retained=retained,
                costs=costs,
                redundancy=redundancy,
                oracle_index=ordering[0],
            )
        )
    return tuple(sorted(decisions, key=lambda item: (item.project, item.root_id, item.parent.branch_id)))


def _direct_useful(item) -> bool:
    utility = item.direct_utility or {}
    return bool(
        utility.get("physically_material")
        or utility.get("retained")
        or utility.get("promoted")
        or (utility.get("proof_valid") and utility.get("distinct_realization"))
    )


def _redundancy(item) -> str:
    if item.failure_class == "duplicate":
        return "canonical-equivalent"
    if item.failure_class == "compiler_identical":
        return "compiler-identical"
    if item.failure_class == "dominated":
        return "dominated"
    if item.target == 0:
        return "exhausted-dead"
    return "unique"


def _utility_value(decision: Decision, index: int) -> float:
    distance = decision.distance[index]
    return (
        8.0 * decision.retained[index]
        + 4.0 * decision.useful[index]
        - 0.2 * (distance if distance is not None else 20)
        - 0.03 * math.log1p(decision.costs[index])
    )


class GATLayer(nn.Module):
    def __init__(self, hidden: int, dropout: float) -> None:
        super().__init__()
        self.query = nn.Linear(hidden, hidden)
        self.key = nn.Linear(hidden, hidden)
        self.value = nn.Linear(hidden, hidden)
        self.edge = nn.Linear(hidden, hidden)
        self.output = nn.Linear(hidden, hidden)
        self.norm = nn.LayerNorm(hidden)
        self.dropout = nn.Dropout(dropout)

    def forward(self, node, edge_index, edge):
        source, destination = edge_index
        query = self.query(node)[destination]
        key = self.key(node)[source] + self.edge(edge)
        logits = (query * key).sum(1) / math.sqrt(node.shape[1])
        maximum = torch.full((node.shape[0],), -torch.inf, device=node.device)
        maximum.scatter_reduce_(0, destination, logits, reduce="amax", include_self=True)
        weights = torch.exp(logits - maximum[destination])
        denominator = torch.zeros(node.shape[0], device=node.device)
        denominator.index_add_(0, destination, weights)
        weights = weights / denominator[destination].clamp_min(1e-9)
        aggregate = torch.zeros_like(node)
        aggregate.index_add_(0, destination, self.value(node)[source] * weights[:, None])
        return self.norm(node + self.dropout(self.output(aggregate)))


class GraphActionEncoder(nn.Module):
    def __init__(self, vocab, *, architecture: str, hidden: int, categorical: int, layers: int, dropout: float):
        super().__init__()
        self.architecture = architecture
        self.hidden = hidden
        self.node_kind = nn.Embedding(len(vocab.values["node_kind"]) + 1, categorical)
        self.node_operation = nn.Embedding(len(vocab.values["node_operation"]) + 1, categorical)
        self.node_type = nn.Embedding(len(vocab.values["node_type"]) + 1, categorical)
        self.node_in = nn.Linear(categorical * 3 + 4, hidden)
        self.edge_relation = nn.Embedding(len(vocab.values["edge_relation"]) + 1, categorical)
        self.edge_ordering = nn.Embedding(len(vocab.values["edge_ordering"]) + 1, categorical)
        self.edge_in = nn.Linear(categorical * 2, hidden)
        layer_types = []
        for index in range(layers):
            if architecture == "gin":
                layer_types.append(SP.MessageLayer(hidden, dropout))
            elif architecture == "gin-gat":
                layer_types.append(SP.MessageLayer(hidden, dropout) if index % 2 == 0 else GATLayer(hidden, dropout))
            elif architecture == "gps":
                layer_types.append(SP.MessageLayer(hidden, dropout))
            else:
                raise ValueError(f"unknown architecture: {architecture}")
        self.layers = nn.ModuleList(layer_types)
        self.global_attention = (
            nn.MultiheadAttention(hidden, 4, dropout=dropout, batch_first=True) if architecture == "gps" else None
        )
        self.global_norm = nn.LayerNorm(hidden)
        self.action_embedding = nn.Embedding(len(vocab.values["action"]) + 1, hidden)
        history_layer = nn.TransformerEncoderLayer(
            hidden, 4, hidden * 2, dropout=dropout, batch_first=True, activation="gelu", norm_first=True
        )
        self.history_encoder = nn.TransformerEncoder(history_layer, num_layers=1)
        # Canonical graph summaries (16), state (8), branch (6), and stage one-hot (3).
        self.output = nn.Sequential(nn.Linear(hidden * 6 + 33, hidden * 2), nn.GELU(), nn.Linear(hidden * 2, hidden))

    def forward(self, batch, *, use_history: bool):
        cat = batch["node_cat"]
        node = F.gelu(
            self.node_in(
                torch.cat(
                    [
                        self.node_kind(cat[:, 0]),
                        self.node_operation(cat[:, 1]),
                        self.node_type(cat[:, 2]),
                        batch["node_num"],
                    ],
                    1,
                )
            )
        )
        edge_cat = batch["edge_cat"]
        edge = F.gelu(
            self.edge_in(torch.cat([self.edge_relation(edge_cat[:, 0]), self.edge_ordering(edge_cat[:, 1])], 1))
        )
        for layer in self.layers:
            node = layer(node, batch["edge_index"], edge)
            if self.global_attention is not None:
                node = self._global(node, batch["batch"])
        count = batch["graph_num"].shape[0]
        mean, maximum = SP.SurvivalModel.pool(node, batch["batch"], count)
        focus_mean, focus_maximum = SP.SurvivalModel.pool(node[batch["focus"]], batch["focus_batch"], count)
        action_mean, _ = SP.SurvivalModel.pool(self.action_embedding(batch["action"]), batch["action_batch"], count)
        history = self._history(batch, count) if use_history else torch.zeros_like(action_mean)
        return self.output(
            torch.cat(
                [
                    mean,
                    maximum,
                    focus_mean,
                    focus_maximum,
                    action_mean,
                    history,
                    batch["graph_num"],
                    batch["state_num"],
                    batch["branch_num"],
                    F.one_hot(batch["stage"], len(SP.STAGES)).float(),
                ],
                1,
            )
        )

    def _global(self, node, batch):
        groups = [node[batch == index] for index in range(int(batch.max()) + 1)]
        padded = nn.utils.rnn.pad_sequence(groups, batch_first=True)
        lengths = torch.tensor([len(group) for group in groups], device=node.device)
        mask = torch.arange(padded.shape[1], device=node.device)[None, :] >= lengths[:, None]
        attended, _ = self.global_attention(padded, padded, padded, key_padding_mask=mask, need_weights=False)
        return torch.cat(
            [self.global_norm(group + attended[index, : len(group)]) for index, group in enumerate(groups)]
        )

    def _history(self, batch, count):
        embedded = self.action_embedding(batch["lineage"])
        groups = [embedded[batch["lineage_batch"] == index] for index in range(count)]
        padded = nn.utils.rnn.pad_sequence(groups, batch_first=True)
        lengths = torch.tensor([len(group) for group in groups], device=embedded.device)
        mask = torch.arange(padded.shape[1], device=embedded.device)[None, :] >= lengths[:, None]
        encoded = self.history_encoder(padded, src_key_padding_mask=mask)
        return encoded.masked_fill(mask[:, :, None], 0).sum(1) / lengths.clamp_min(1)[:, None]


class ContextualPolicy(nn.Module):
    def __init__(
        self,
        vocab,
        *,
        architecture: str,
        hidden: int,
        categorical: int,
        layers: int,
        dropout: float,
        use_history: bool,
        use_siblings: bool,
    ) -> None:
        super().__init__()
        self.use_history = use_history
        self.use_siblings = use_siblings
        self.encoder = GraphActionEncoder(
            vocab,
            architecture=architecture,
            hidden=hidden,
            categorical=categorical,
            layers=layers,
            dropout=dropout,
        )
        self.combine = nn.Sequential(nn.Linear(hidden * 2, hidden), nn.GELU(), nn.Linear(hidden, hidden))
        self.frontier_attention = nn.MultiheadAttention(hidden, 4, dropout=dropout, batch_first=True)
        self.frontier_norm = nn.LayerNorm(hidden)
        self.score = nn.Linear(hidden, 1)
        self.cost = nn.Linear(hidden, 1)
        self.utility = nn.Linear(hidden, 1)
        self.redundancy = nn.Linear(hidden, len(REDUNDANCY))

    def forward(self, parent_batch, option_batch, lengths):
        parent = self.encoder(parent_batch, use_history=self.use_history)
        option = self.encoder(option_batch, use_history=self.use_history)
        parent_repeated = torch.repeat_interleave(parent, torch.tensor(lengths, device=parent.device), dim=0)
        state = self.combine(torch.cat([parent_repeated, option], 1))
        if self.use_siblings:
            groups = torch.split(state, lengths)
            padded = nn.utils.rnn.pad_sequence(groups, batch_first=True)
            size = torch.tensor(lengths, device=state.device)
            mask = torch.arange(padded.shape[1], device=state.device)[None, :] >= size[:, None]
            attended, _ = self.frontier_attention(padded, padded, padded, key_padding_mask=mask, need_weights=False)
            state = torch.cat(
                [self.frontier_norm(group + attended[index, : len(group)]) for index, group in enumerate(groups)]
            )
        return {
            "score": self.score(state).squeeze(1),
            "cost": self.cost(state).squeeze(1),
            "utility": self.utility(state).squeeze(1),
            "redundancy": self.redundancy(state),
            "state_embedding": state,
        }


def equivalence_proposals(output, lengths, *, probability_threshold=0.90, similarity_threshold=0.98):
    """Return candidate sibling pairs for exact verification; this never authorizes merging."""
    probabilities = F.softmax(output["redundancy"], dim=1)
    redundant = probabilities[:, 1:4].sum(1)
    embedding = F.normalize(output["state_embedding"], dim=1)
    result = []
    offset = 0
    for length in lengths:
        local = []
        for left in range(length):
            for right in range(left + 1, length):
                indices = (offset + left, offset + right)
                similarity = float((embedding[indices[0]] * embedding[indices[1]]).sum().detach())
                confidence = float(min(redundant[indices[0]], redundant[indices[1]]).detach())
                if confidence >= probability_threshold and similarity >= similarity_threshold:
                    local.append((left, right, confidence, similarity))
        result.append(local)
        offset += length
    return result


class DecisionDataset:
    def __init__(self, decisions: Iterable[Decision], vocab) -> None:
        self.decisions = tuple(decisions)
        self.vocab = vocab

    def __len__(self):
        return len(self.decisions)

    def __getitem__(self, index):
        return self.decisions[index]


def collate_decisions(decisions: list[Decision], vocab):
    parents = [(item.parent, SP.tensorize(item.parent, vocab)) for item in decisions]
    options = [option for item in decisions for option in item.options]
    option_tensors = [(item, SP.tensorize(item, vocab)) for item in options]
    _, parent_batch = SP.collate(parents)
    _, option_batch = SP.collate(option_tensors)
    lengths = [len(item.options) for item in decisions]
    utility = torch.tensor([_utility_value(item, index) for item in decisions for index in range(len(item.options))])
    useful = torch.tensor([value for item in decisions for value in item.useful], dtype=torch.float32)
    cost = torch.tensor([math.log1p(value) for item in decisions for value in item.costs], dtype=torch.float32)
    redundancy = torch.tensor([value for item in decisions for value in item.redundancy], dtype=torch.long)
    return decisions, parent_batch, option_batch, lengths, utility, useful, cost, redundancy


def _move(batch, device):
    return {key: value.to(device) for key, value in batch.items()}


def train_model(
    train,
    validation,
    pretraining_examples,
    vocab,
    args,
    architecture,
    use_history,
    use_siblings,
    device,
    seed,
):
    SP.seed_all(seed)
    model = ContextualPolicy(
        vocab,
        architecture=architecture,
        hidden=args.hidden,
        categorical=args.categorical,
        layers=args.layers,
        dropout=args.dropout,
        use_history=use_history,
        use_siblings=use_siblings,
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    pretraining = pretrain_encoder(model, pretraining_examples, vocab, args, device)
    loader = DataLoader(
        DecisionDataset(train, vocab),
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=lambda values: collate_decisions(values, vocab),
    )
    best = None
    history = []
    for epoch in range(args.epochs):
        model.train()
        losses = []
        for batch_decisions, parent_batch, option_batch, lengths, utility, useful, cost, redundancy in loader:
            parent_batch = _move(parent_batch, device)
            option_batch = _move(option_batch, device)
            utility, useful, cost, redundancy = (
                utility.to(device),
                useful.to(device),
                cost.to(device),
                redundancy.to(device),
            )
            output = model(parent_batch, option_batch, lengths)
            ranking = []
            pairwise = []
            offset = 0
            for decision, length in zip(batch_decisions, lengths, strict=True):
                predicted = output["score"][offset : offset + length]
                target = F.softmax(utility[offset : offset + length] / args.oracle_temperature, dim=0)
                ranking.append(-(target * F.log_softmax(predicted, dim=0)).sum())
                local_useful = useful[offset : offset + length]
                positive = torch.where(local_useful > 0.5)[0]
                negative = torch.where(local_useful <= 0.5)[0]
                if len(positive) and len(negative):
                    differences = predicted[positive][:, None] - predicted[negative][None, :]
                    pairwise.append(F.softplus(args.pairwise_margin - differences).mean())
                # Among useful siblings, shorter paths should be explored first.
                useful_indices = [index for index, value in enumerate(decision.useful) if value]
                for left in useful_indices:
                    for right in useful_indices:
                        left_distance = decision.distance[left]
                        right_distance = decision.distance[right]
                        if left_distance is not None and right_distance is not None and left_distance < right_distance:
                            pairwise.append(F.softplus(args.distance_margin - (predicted[left] - predicted[right])))
                offset += length
            positive_weight = torch.tensor(
                min(args.maximum_positive_weight, max(1.0, float((useful <= 0.5).sum()) / max(float((useful > 0.5).sum()), 1.0))),
                device=device,
            )
            loss = (
                args.listwise_weight * torch.stack(ranking).mean()
                + args.pairwise_weight * (torch.stack(pairwise).mean() if pairwise else 0.0)
                + args.utility_weight
                * F.binary_cross_entropy_with_logits(output["utility"], useful, pos_weight=positive_weight)
                + args.cost_weight * F.smooth_l1_loss(output["cost"], cost)
                + args.redundancy_weight * F.cross_entropy(output["redundancy"], redundancy)
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            optimizer.step()
            losses.append(float(loss.detach()))
        scores = predict_scores(model, validation, vocab, args.batch_size, device)
        validation_replay = replay(validation, scores)
        objective = validation_replay["aggregate"]["recovery"]["0.3"]["useful_terminal_recovery"]
        history.append({"epoch": epoch + 1, "loss": float(np.mean(losses)), "validation_recovery_30": objective})
        if best is None or objective > best[0]:
            best = (objective, {key: value.detach().cpu().clone() for key, value in model.state_dict().items()})
    assert best is not None
    model.load_state_dict(best[1])
    return model, pretraining, history


def pretrain_encoder(model, examples, vocab, args, device):
    """Use all historical RC24 branches for encoder pretraining, not only sibling frontiers."""
    eligible = [item for item in examples if item.target in {0, 1}]
    if not eligible or args.pretrain_epochs <= 0:
        return []
    head = nn.Linear(args.hidden, 1).to(device)
    optimizer = torch.optim.AdamW(
        [*model.encoder.parameters(), *head.parameters()],
        lr=args.learning_rate,
        weight_decay=1e-4,
    )
    loader = SP.loader(eligible, vocab, args.pretrain_batch_size, True)
    positives = sum(item.target == 1 for item in eligible)
    positive_weight = torch.tensor(
        min(args.maximum_positive_weight, max(1.0, (len(eligible) - positives) / max(positives, 1))),
        device=device,
    )
    history = []
    for epoch in range(args.pretrain_epochs):
        model.train()
        losses = []
        for batch_examples, batch in loader:
            batch = _move(batch, device)
            labels = torch.tensor([item.target for item in batch_examples], dtype=torch.float32, device=device)
            embedding = model.encoder(batch, use_history=model.use_history)
            loss = F.binary_cross_entropy_with_logits(head(embedding).squeeze(1), labels, pos_weight=positive_weight)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_([*model.encoder.parameters(), *head.parameters()], 2.0)
            optimizer.step()
            losses.append(float(loss.detach()))
        history.append({"epoch": epoch + 1, "loss": float(np.mean(losses)), "examples": len(eligible)})
    # The contextual state is transformed further, but this gives both ordering heads a useful
    # initial preservation direction instead of discarding the RC24 supervision after encoding.
    model.utility.load_state_dict(head.state_dict())
    model.score.load_state_dict(head.state_dict())
    return history


@torch.no_grad()
def predict_scores(model, decisions, vocab, batch_size, device, combination="hybrid"):
    model.eval()
    loader = DataLoader(
        DecisionDataset(decisions, vocab),
        batch_size=batch_size,
        shuffle=False,
        collate_fn=lambda values: collate_decisions(values, vocab),
    )
    result = {}
    for batch_decisions, parent_batch, option_batch, lengths, *_ in loader:
        output = model(_move(parent_batch, device), _move(option_batch, device), lengths)
        offset = 0
        for decision, length in zip(batch_decisions, lengths, strict=True):
            ranking = output["score"][offset : offset + length]
            absolute = torch.sigmoid(output["utility"][offset : offset + length])
            order = torch.argsort(torch.argsort(ranking)).float()
            relative = order / max(length - 1, 1)
            if combination == "raw":
                selected = ranking
            elif combination == "ranking":
                selected = relative
            elif combination == "utility":
                selected = absolute
            elif combination == "hybrid":
                selected = 0.75 * absolute + 0.25 * relative
            else:
                raise ValueError(f"unknown score combination: {combination}")
            values = selected.cpu().tolist()
            result.update({option.branch_id: score for option, score in zip(decision.options, values, strict=True)})
            offset += length
    return result


def replay(decisions: Iterable[Decision], score_map: dict[str, float]):
    decisions = tuple(decisions)
    by_scope: dict[str, list[Decision]] = defaultdict(list)
    for item in decisions:
        by_scope[item.project].append(item)
    project_reports = []
    for project, project_decisions in by_scope.items():
        values = {}
        children = defaultdict(list)
        branch_scores = {}
        semantic_roots = set()
        for decision in project_decisions:
            semantic_roots.add(decision.root_id)
            values[decision.parent.branch_id] = decision.parent
            for option in decision.options:
                values[option.branch_id] = option
                children[decision.parent.branch_id].append(option.branch_id)
                branch_scores[option.branch_id] = score_map.get(option.branch_id, 0.0)
        referenced = {child for group in children.values() for child in group}
        roots = [branch_id for branch_id in values if branch_id not in referenced]
        queue = []
        sequence = 0
        for branch_id in roots:
            queue.append((-branch_scores.get(branch_id, 0.0), sequence, branch_id))
            sequence += 1
        import heapq

        heapq.heapify(queue)
        total_work = sum(_direct_work(item) for item in values.values())
        useful_terminals = {
            branch_id for branch_id, item in values.items() if _direct_useful(item) and not children.get(branch_id)
        }
        useful_by_stage = {
            stage: {branch_id for branch_id in useful_terminals if values[branch_id].stage == stage}
            for stage in SP.STAGES
        }
        useful_branches_by_stage = {
            stage: {branch_id for branch_id, item in values.items() if item.target == 1 and item.stage == stage}
            for stage in SP.STAGES
        }
        retained_terminals = {
            branch_id
            for branch_id, item in values.items()
            if bool((item.direct_utility or {}).get("retained")) and not children.get(branch_id)
        }
        discovered = set()
        discovered_useful_branches = set()
        retained_discovered = set()
        work = 0.0
        proof_calls = 0
        compiler_invocations = 0
        candidate_constructions = 0
        maximum_frontier = len(queue)
        first_useful = first_retained = None
        curve = {}
        while queue:
            _, _, branch_id = heapq.heappop(queue)
            current = values[branch_id]
            work += _direct_work(current)
            proof_calls += current.proof_calls
            compiler_invocations += current.compiler_invocations
            candidate_constructions += 1
            if current.target == 1:
                discovered_useful_branches.add(branch_id)
            if branch_id in useful_terminals:
                discovered.add(branch_id)
                first_useful = first_useful if first_useful is not None else work / max(total_work, 1)
            if branch_id in retained_terminals:
                retained_discovered.add(branch_id)
                first_retained = first_retained if first_retained is not None else work / max(total_work, 1)
            for child in children.get(branch_id, ()):
                heapq.heappush(queue, (-branch_scores.get(child, 0.0), sequence, child))
                sequence += 1
            maximum_frontier = max(maximum_frontier, len(queue))
            fraction = work / max(total_work, 1)
            for checkpoint in CHECKPOINTS:
                key = str(checkpoint)
                if key not in curve and fraction >= checkpoint:
                    curve[key] = {
                        "useful_recovery": len(discovered) / max(len(useful_terminals), 1),
                        "retained_recovery": (
                            len(retained_discovered) / len(retained_terminals) if retained_terminals else None
                        ),
                        "executed_work": work,
                        "proof_calls": proof_calls,
                        "compiler_invocations": compiler_invocations,
                        "candidate_constructions": candidate_constructions,
                        "stage_recovery": {
                            stage: len(discovered & branch_ids) / max(len(branch_ids), 1)
                            for stage, branch_ids in useful_by_stage.items()
                        },
                        "decision_stage_recovery": {
                            stage: len(discovered_useful_branches & branch_ids) / max(len(branch_ids), 1)
                            for stage, branch_ids in useful_branches_by_stage.items()
                        },
                    }
        for checkpoint in CHECKPOINTS:
            curve.setdefault(
                str(checkpoint),
                {
                    "useful_recovery": len(discovered) / max(len(useful_terminals), 1),
                    "retained_recovery": len(retained_discovered) / len(retained_terminals)
                    if retained_terminals
                    else None,
                    "executed_work": work,
                    "proof_calls": proof_calls,
                    "compiler_invocations": compiler_invocations,
                    "candidate_constructions": candidate_constructions,
                    "stage_recovery": {
                        stage: len(discovered & branch_ids) / max(len(branch_ids), 1)
                        for stage, branch_ids in useful_by_stage.items()
                    },
                    "decision_stage_recovery": {
                        stage: len(discovered_useful_branches & branch_ids) / max(len(branch_ids), 1)
                        for stage, branch_ids in useful_branches_by_stage.items()
                    },
                },
            )
        project_reports.append(
            {
                "project": project,
                "roots": len(semantic_roots),
                "total_work": total_work,
                "useful_terminals": len(useful_terminals),
                "useful_terminals_by_stage": {
                    stage: len(branch_ids) for stage, branch_ids in useful_by_stage.items()
                },
                "useful_branches_by_stage": {
                    stage: len(branch_ids) for stage, branch_ids in useful_branches_by_stage.items()
                },
                "retained_terminals": len(retained_terminals),
                "first_useful_work_fraction": first_useful,
                "first_retained_work_fraction": first_retained,
                "maximum_frontier_size": maximum_frontier,
                "total_proof_calls": sum(item.proof_calls for item in values.values()),
                "total_compiler_invocations": sum(item.compiler_invocations for item in values.values()),
                "total_candidate_constructions": len(values),
                "recovery": curve,
            }
        )
    return _aggregate_replays(project_reports)


def _direct_work(item) -> float:
    return 1.0 + item.node_expansions + item.proof_calls + item.compiler_invocations


def _aggregate_replays(projects):
    useful_total = sum(item["useful_terminals"] for item in projects)
    retained_total = sum(item["retained_terminals"] for item in projects)
    recovery = {}
    for checkpoint in CHECKPOINTS:
        key = str(checkpoint)
        useful = sum(item["recovery"][key]["useful_recovery"] * item["useful_terminals"] for item in projects)
        retained = sum(
            (item["recovery"][key]["retained_recovery"] or 0) * item["retained_terminals"] for item in projects
        )
        recovery[key] = {
            "useful_terminal_recovery": useful / max(useful_total, 1),
            "retained_terminal_recovery": retained / retained_total if retained_total else None,
            "executed_work": sum(item["recovery"][key]["executed_work"] for item in projects),
            "proof_calls": sum(item["recovery"][key]["proof_calls"] for item in projects),
            "compiler_invocations": sum(item["recovery"][key]["compiler_invocations"] for item in projects),
            "candidate_constructions": sum(
                item["recovery"][key]["candidate_constructions"] for item in projects
            ),
            "stage_recovery": {
                stage: sum(
                    item["recovery"][key]["stage_recovery"][stage]
                    * item["useful_terminals_by_stage"][stage]
                    for item in projects
                )
                / max(sum(item["useful_terminals_by_stage"][stage] for item in projects), 1)
                for stage in SP.STAGES
            },
            "decision_stage_recovery": {
                stage: sum(
                    item["recovery"][key]["decision_stage_recovery"][stage]
                    * item["useful_branches_by_stage"][stage]
                    for item in projects
                )
                / max(sum(item["useful_branches_by_stage"][stage] for item in projects), 1)
                for stage in SP.STAGES
            },
        }
    return {
        "aggregate": {
            "projects": len(projects),
            "roots": sum(item["roots"] for item in projects),
            "useful_terminals": useful_total,
            "retained_terminals": retained_total,
            "useful_terminals_by_stage": {
                stage: sum(item["useful_terminals_by_stage"][stage] for item in projects)
                for stage in SP.STAGES
            },
            "useful_branches_by_stage": {
                stage: sum(item["useful_branches_by_stage"][stage] for item in projects)
                for stage in SP.STAGES
            },
            "recovery": recovery,
            "median_first_useful_work_fraction": _median(
                [
                    item["first_useful_work_fraction"]
                    for item in projects
                    if item["first_useful_work_fraction"] is not None
                ]
            ),
            "median_first_retained_work_fraction": _median(
                [
                    item["first_retained_work_fraction"]
                    for item in projects
                    if item["first_retained_work_fraction"] is not None
                ]
            ),
            "maximum_frontier_size": max((item["maximum_frontier_size"] for item in projects), default=0),
            "total_proof_calls": sum(item["total_proof_calls"] for item in projects),
            "total_compiler_invocations": sum(item["total_compiler_invocations"] for item in projects),
            "total_candidate_constructions": sum(item["total_candidate_constructions"] for item in projects),
            "canonical_transposition_reductions": None,
            "canonical_transposition_limitation": "RC24 did not retain canonical semantic state hashes",
        },
        "projects": projects,
    }


def _median(values):
    return float(np.median(values)) if values else None


def baseline_scores(decisions, kind, rc24_scores=None):
    result = {}
    for decision in decisions:
        for index, item in enumerate(decision.options):
            if kind == "fifo":
                result[item.branch_id] = 0.0
            elif kind == "random":
                result[item.branch_id] = int(hashlib.sha256(item.branch_id.encode()).hexdigest()[:8], 16) / 2**32
            elif kind == "handwritten":
                remaining = SP._feature((item.state_features or {}).get("numeric", []), "remaining_count")
                result[item.branch_id] = 4.0 * float(item.branch_state == "terminal") - remaining - 0.1 * item.depth
            elif kind == "rc24":
                result[item.branch_id] = (rc24_scores or {}).get(item.branch_id, 0.0)
            elif kind == "oracle":
                result[item.branch_id] = _utility_value(decision, index)
            else:
                raise ValueError(kind)
    return result


def load_rc24_scores(run: Path, projects: Iterable[str]):
    result = {}
    for project in projects:
        path = run / f"fold-{project}-test.npz"
        if not path.exists():
            continue
        data = np.load(path, allow_pickle=False)
        result.update(
            {str(branch): float(score) for branch, score in zip(data["branch_id"], data["probability"], strict=True)}
        )
    return result


def root_split(decisions, heldout=None):
    eligible = [item for item in decisions if heldout is None or item.project != heldout]
    roots = sorted({(item.project, item.root_id) for item in eligible})
    validation_roots = {
        root for root in roots if int(hashlib.sha256(f"{root[0]}:{root[1]}".encode()).hexdigest()[:8], 16) % 5 == 0
    }
    if not validation_roots and roots:
        validation_roots = {roots[-1]}
    return (
        [item for item in eligible if (item.project, item.root_id) not in validation_roots],
        [item for item in eligible if (item.project, item.root_id) in validation_roots],
    )


def model_variants(requested: str):
    values = {
        "graph": ("gin", False, False),
        "graph-history": ("gin", True, False),
        "graph-history-frontier": ("gin", True, True),
        "gin-gat-frontier": ("gin-gat", True, True),
        "gps-frontier": ("gps", True, True),
    }
    return values if requested == "all" else {name: values[name] for name in requested.split(",")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, action="append", required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--rc24-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--evaluate-only-from",
        type=Path,
        help="reuse compatible fold checkpoints and regenerate online replay metrics without training",
    )
    parser.add_argument("--variants", default="all")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--pretrain-epochs", type=int, default=1)
    parser.add_argument("--pretrain-batch-size", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--hidden", type=int, default=160)
    parser.add_argument("--categorical", type=int, default=40)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--oracle-temperature", type=float, default=0.8)
    parser.add_argument("--listwise-weight", type=float, default=0.5)
    parser.add_argument("--pairwise-weight", type=float, default=1.0)
    parser.add_argument("--pairwise-margin", type=float, default=1.0)
    parser.add_argument("--distance-margin", type=float, default=0.25)
    parser.add_argument("--maximum-positive-weight", type=float, default=20.0)
    parser.add_argument("--utility-weight", type=float, default=0.2)
    parser.add_argument("--cost-weight", type=float, default=0.08)
    parser.add_argument("--redundancy-weight", type=float, default=0.08)
    parser.add_argument("--score-combination", choices=("raw", "ranking", "utility", "hybrid"), default="raw")
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    examples = SP.load_campaign_examples(args.progress, args.manifest)
    decisions = load_decisions(examples)
    projects = sorted({item.project for item in decisions})
    rc24 = load_rc24_scores(args.rc24_run, projects)
    args.output.mkdir(parents=True, exist_ok=True)
    baselines = {}
    for name in ("fifo", "random", "handwritten", "rc24", "oracle"):
        baselines[name] = replay(decisions, baseline_scores(decisions, name, rc24))["aggregate"]

    folds = []
    variants = model_variants(args.variants)
    for heldout in projects:
        train, validation = root_split(decisions, heldout)
        test = [item for item in decisions if item.project == heldout]
        pretraining_examples = [item for item in examples if item.project != heldout]
        vocab = SP.Vocab.build(pretraining_examples)
        for offset, (name, (architecture, use_history, use_siblings)) in enumerate(variants.items()):
            fold_name = f"{heldout}-{name}".replace("/", "_")
            checkpoint_path = (
                args.evaluate_only_from / f"fold-{fold_name}.pt" if args.evaluate_only_from else None
            )
            if checkpoint_path is not None:
                payload = torch.load(checkpoint_path, map_location=device, weights_only=True)
                configuration = payload["configuration"]
                vocab = SP.Vocab(payload["vocab"])
                model = ContextualPolicy(
                    vocab,
                    architecture=configuration["architecture"],
                    hidden=configuration["hidden"],
                    categorical=configuration["categorical"],
                    layers=configuration["layers"],
                    dropout=args.dropout,
                    use_history=configuration["use_history"],
                    use_siblings=configuration["use_siblings"],
                ).to(device)
                model.load_state_dict(payload["state_dict"])
                pretraining, history = [], []
            else:
                model, pretraining, history = train_model(
                    train,
                    validation,
                    pretraining_examples,
                    vocab,
                    args,
                    architecture,
                    use_history,
                    use_siblings,
                    device,
                    args.seed + offset * 1009,
                )
            scores = predict_scores(model, test, vocab, args.batch_size, device, args.score_combination)
            result = replay(test, scores)
            torch.save(
                {
                    "schema_version": SCHEMA,
                    "state_dict": model.state_dict(),
                    "vocab": vocab.to_dict(),
                    "configuration": {
                        "architecture": architecture,
                        "use_history": use_history,
                        "use_siblings": use_siblings,
                        "hidden": args.hidden,
                        "categorical": args.categorical,
                        "layers": args.layers,
                    },
                    "authority": "priority-only; never semantic deletion",
                },
                args.output / f"fold-{fold_name}.pt",
            )
            folds.append(
                {
                    "heldout_project": heldout,
                    "variant": name,
                    "architecture": architecture,
                    "use_history": use_history,
                    "use_siblings": use_siblings,
                    "parameters": sum(parameter.numel() for parameter in model.parameters()),
                    "history": history,
                    "encoder_pretraining": pretraining,
                    "replay": result["aggregate"],
                }
            )
            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()
    aggregate_variants = {}
    for name in variants:
        selected = [item for item in folds if item["variant"] == name]
        totals = sum(item["replay"]["useful_terminals"] for item in selected)
        aggregate_variants[name] = {
            "useful_terminals": totals,
            "recovery": {
                str(checkpoint): sum(
                    item["replay"]["recovery"][str(checkpoint)]["useful_terminal_recovery"]
                    * item["replay"]["useful_terminals"]
                    for item in selected
                )
                / max(totals, 1)
                for checkpoint in CHECKPOINTS
            },
            "stage_recovery": {
                stage: {
                    str(checkpoint): sum(
                        item["replay"]["recovery"][str(checkpoint)]["stage_recovery"][stage]
                        * item["replay"]["useful_terminals_by_stage"][stage]
                        for item in selected
                    )
                    / max(
                        sum(item["replay"]["useful_terminals_by_stage"][stage] for item in selected),
                        1,
                    )
                    for checkpoint in CHECKPOINTS
                }
                for stage in SP.STAGES
            },
            "decision_stage_recovery": {
                stage: {
                    str(checkpoint): sum(
                        item["replay"]["recovery"][str(checkpoint)]["decision_stage_recovery"][stage]
                        * item["replay"]["useful_branches_by_stage"][stage]
                        for item in selected
                    )
                    / max(
                        sum(item["replay"]["useful_branches_by_stage"][stage] for item in selected),
                        1,
                    )
                    for checkpoint in CHECKPOINTS
                }
                for stage in SP.STAGES
            },
            "parameters": selected[0]["parameters"] if selected else 0,
        }
    best_name = max(
        aggregate_variants,
        key=lambda name: (
            aggregate_variants[name]["recovery"]["0.3"],
            aggregate_variants[name]["recovery"]["0.2"],
        ),
    )
    observed = aggregate_variants[best_name]["recovery"]["0.3"]
    report = {
        "schema_version": "vladder-contextual-search-evaluation-v1",
        "status": "phase_a_pass" if observed >= 0.99 else "phase_a_failed",
        "authority": "learned ordering only; deterministic/formal systems retain deletion authority",
        "device": str(device),
        "examples": len(examples),
        "decisions": len(decisions),
        "frontier_actions": sum(len(item.options) for item in decisions),
        "projects": projects,
        "retained_evidence_available": False,
        "canonical_state_hash_available": False,
        "score_combination": args.score_combination,
        "baselines": baselines,
        "variants": aggregate_variants,
        "best_variant": best_name,
        "acceptance": {
            "required_useful_recovery_at_30_percent": 0.99,
            "observed": observed,
            "passed": observed >= 0.99,
        },
        "folds": folds,
    }
    (args.output / "evaluation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "best_variant": best_name,
                "recovery": aggregate_variants[best_name]["recovery"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
