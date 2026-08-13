#!/usr/bin/env python3
"""Serve a composition-native checkpoint over vLadder's frontier JSONL protocol."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import torch
    import torch.nn.functional as F
except ImportError as error:  # pragma: no cover
    raise SystemExit("composition-policy-oracle requires `pip install 'vladder[ml]'`") from error

from vladder.composition_native import build_interaction_graph, exact_state_delta
from vladder.search_decision_context import build_decision_context

SPEC = importlib.util.spec_from_file_location("vladder_composition_native_runtime", ROOT / "scripts" / "composition_native_policy.py")
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)


class Oracle:
    def __init__(self, checkpoint: Path, device: torch.device) -> None:
        payload = torch.load(checkpoint, map_location=device, weights_only=True)
        self.vocab = POLICY.Vocab(payload["vocab"])
        self.model = POLICY.CompositionPolicy(self.vocab, payload["configuration"]).to(device)
        self.model.load_state_dict(payload["state_dict"])
        self.model.eval()
        self.device = device
        self.roots: dict[str, dict[str, Any]] = {}

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(request.get("kind", ""))
        if kind == "register_root":
            root_id = str(request["root_id"])
            self.roots[root_id] = dict(request.get("root", {}))
            return {"status": "ready", "authority": "priority-only"}
        if kind == "rank_frontier":
            decision = self._decision(request)
            root_in_distribution = self._known_graph(decision.semantic_graph)
            batch = POLICY._move(POLICY.collate_decisions([decision], self.vocab), self.device)
            with torch.no_grad():
                output = self.model(batch)
                probability = F.softmax(output["tier"], 1)
                entropy = -(probability * probability.clamp_min(1e-9).log()).sum(1)
            scores = output["score"].cpu().tolist()
            uncertainties = entropy.cpu().tolist()
            return {
                "scores": [
                    {
                        "score": float(score),
                        "uncertainty": float(uncertainty),
                        "reason": "composition-native contextual best-first priority",
                        "in_distribution": root_in_distribution and self._known_action(option.action),
                    }
                    for option, score, uncertainty in zip(decision.options, scores, uncertainties, strict=True)
                ]
            }
        if kind == "propose_equivalence":
            decision = self._decision(request)
            batch = POLICY._move(POLICY.collate_decisions([decision], self.vocab), self.device)
            with torch.no_grad():
                output = self.model(batch)
                redundant = F.softmax(output["redundancy"], 1)[:, 1:5].sum(1)
                embedding = F.normalize(output["embedding"], dim=1)
            pairs = []
            for left in range(len(decision.options)):
                for right in range(left + 1, len(decision.options)):
                    confidence = float(min(redundant[left], redundant[right]))
                    similarity = float((embedding[left] * embedding[right]).sum())
                    if confidence >= 0.90 and similarity >= 0.98:
                        pairs.append([left, right])
            return {
                "pairs": pairs,
                "authority": "proposal-only; exact verifier required before collapse",
            }
        return {"status": "error", "error": f"unsupported request kind: {kind}"}

    def _decision(self, request: Mapping[str, Any]):
        root_id = str(request["root_id"])
        root = self.roots[root_id]
        graph = dict(root.get("semantic_graph", {}))
        depth = int(request.get("depth", 0))
        history = tuple(dict(item) for item in request.get("history", ()))
        parent = request.get("parent")
        parent_context = self._context(graph, parent, max(0, depth - 1), history[:-1]) if parent else {
            "graph": graph, "focus_node_ids": [], "canonical_state_hash": root_id,
            "state_features": {"depth": 0}, "semantic_delta": {},
        }
        raw_frontier = tuple(dict(item) for item in request.get("frontier", ()))
        previews = []
        for item in raw_frontier:
            context = self._context(graph, item, depth, history)
            previews.append({
                "state_hash": str(item.get("identity", "")),
                "action": dict(item.get("action", {})),
                "decision_context": context,
                "state_delta": exact_state_delta(
                    parent_context,
                    context,
                    dict(parent.get("semantic_state", {})) if isinstance(parent, Mapping) else {},
                    dict(item.get("semantic_state", {})),
                ),
            })
        interaction = build_interaction_graph(parent_context, history, previews)
        options = tuple(
            POLICY.Option(
                f"runtime-{index}", None, dict(item["action"]), dict(item["state_delta"]),
                0, 32.0, 1.0, 0, index,
            )
            for index, item in enumerate(previews)
        )
        return POLICY.Decision(
            "runtime", root_id, POLICY._normalized_topology_hash(graph), "runtime-frontier", None,
            graph, interaction, history, options, depth,
            len(history) >= 2 or any(POLICY._composition_action(item.action) for item in options),
        )

    @staticmethod
    def _context(graph, state, depth, history):
        return build_decision_context(
            graph,
            semantic_state=dict(state.get("semantic_state", {})),
            action=dict(state.get("action", {})),
            ancestor_actions=history,
            depth=depth,
            stage=str(state.get("stage", "composition")),
            terminal=False,
            projection=dict(state.get("decision_projection", {})),
        )

    def _known_action(self, action):
        return all(self.vocab.index("action", token) != 0 for token in POLICY._action_tokens(action, "current"))

    def _known_graph(self, graph):
        for node in POLICY._nodes(graph):
            attrs = node.get("attributes") if isinstance(node.get("attributes"), Mapping) else {}
            if not all((
                self.vocab.index("node_kind", str(node.get("kind", "Other"))),
                self.vocab.index("node_operation", str(node.get("operation", node.get("kind", "other")))),
                self.vocab.index("node_type", str(node.get("output_type", attrs.get("relation", "other")))),
            )):
                return False
        return all(
            self.vocab.index("edge_relation", str(edge.get("relation", "other")))
            for edge in POLICY._edges(graph)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    oracle = Oracle(args.checkpoint, device)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = oracle.handle(request)
        except Exception as error:  # fail-open transport response; caller supplies neutral priority
            response = {"status": "error", "error": str(error)[:2000]}
        print(json.dumps(response, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
