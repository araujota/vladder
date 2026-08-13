#!/usr/bin/env python3
"""Evaluate a calibrated non-GNN baseline over v3 pre-decision graph summaries."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys

import numpy as np

try:
    from sklearn.ensemble import HistGradientBoostingClassifier
except ImportError as error:  # pragma: no cover
    raise SystemExit("summary baseline requires scikit-learn") from error


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("vladder_search_pruner", ROOT / "scripts" / "search_pruner.py")
assert SPEC and SPEC.loader
PRUNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PRUNER
SPEC.loader.exec_module(PRUNER)


def _bucket(token: str, width: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode()).digest()
    return int.from_bytes(digest[:4], "big") % width, 1.0 if digest[4] & 1 else -1.0


def feature_vector(example, width: int) -> np.ndarray:
    nodes = example.graph.get("node_features", ())
    edges = example.graph.get("edge_features", ())
    dense = PRUNER._graph_summary(example, max(len(nodes), 1), max(len(edges), 1))
    dense.extend(
        PRUNER._feature((example.state_features or {}).get("numeric", []), name)
        for name in ("depth", "selected_count", "remaining_count", "action_count", "region_count")
    )
    dense.extend(
        PRUNER._feature((example.semantic_delta or {}).get("numeric", []), name) for name in ("factor", "width", "tile")
    )
    dense.extend([math.log1p(example.depth), len(example.action.get("primitives", ())), len(example.lineage)])
    hashed = np.zeros(width, dtype=np.float32)
    tokens = [*PRUNER.action_tokens(example.action, current=True), *PRUNER.context_tokens(example)]
    for ancestor in example.lineage:
        tokens.extend(PRUNER.action_tokens(ancestor, current=False))
    tokens.extend(
        f"node.kind={key}:{value}" for key, value in Counter(str(node.get("kind", "Other")) for node in nodes).items()
    )
    tokens.extend(
        f"node.op={key}:{value}"
        for key, value in Counter(str(node.get("operation", "other")) for node in nodes).items()
    )
    tokens.extend(
        f"edge={key}:{value}" for key, value in Counter(str(edge.get("relation", "other")) for edge in edges).items()
    )
    for token in tokens:
        index, sign = _bucket(token, width)
        hashed[index] += sign
    return np.concatenate([np.asarray(dense, dtype=np.float32), hashed])


def train_models(examples, args):
    labeled = [item for item in examples if item.target is not None]
    features = np.stack([feature_vector(item, args.hash_width) for item in labeled])
    targets = np.asarray([item.target for item in labeled], dtype=np.int8)
    weights = np.asarray(
        [
            (args.positive_weight if item.target else 1.0)
            * (1.0 + args.subtree_weight * min(8.0, math.log1p(item.subtree_cost)))
            for item in labeled
        ],
        dtype=np.float32,
    )
    roots = sorted({(item.project, item.root_id) for item in labeled})
    models = []
    for member in range(args.ensemble_size):
        rng = random.Random(args.seed + member * 1009)
        sampled = {roots[rng.randrange(len(roots))] for _ in range(len(roots))}
        indices = np.asarray(
            [index for index, item in enumerate(labeled) if (item.project, item.root_id) in sampled], dtype=np.int64
        )
        model = HistGradientBoostingClassifier(
            max_iter=args.iterations,
            max_leaf_nodes=args.max_leaf_nodes,
            learning_rate=args.learning_rate,
            l2_regularization=1.0,
            early_stopping=False,
        )
        model.fit(features[indices], targets[indices], sample_weight=weights[indices])
        models.append(model)
    return models, {str(item.action.get("family", "other")) for item in labeled}


def predict(models, examples, known_families, args):
    if not examples:
        return []
    features = np.stack([feature_vector(item, args.hash_width) for item in examples])
    probabilities = np.stack([model.predict_proba(features)[:, 1] for model in models])
    rng = np.random.default_rng(20260811)
    projection = rng.normal(size=(features.shape[1], args.retrieval_width)).astype(np.float32) / math.sqrt(
        features.shape[1]
    )
    embeddings = features @ projection
    embeddings /= np.maximum(np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-8)
    return [
        {
            "example": item,
            "probability": float(probabilities[:, index].mean()),
            "uncertainty": float(probabilities[:, index].std()),
            "member_min": float(probabilities[:, index].min()),
            "member_max": float(probabilities[:, index].max()),
            "embedding": embeddings[index],
            "unknown": str(item.action.get("family", "other")) not in known_families,
            "signature": PRUNER.decision_signature(item),
        }
        for index, item in enumerate(examples)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, action="append", required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=120)
    parser.add_argument("--max-leaf-nodes", type=int, default=31)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--positive-weight", type=float, default=80.0)
    parser.add_argument("--subtree-weight", type=float, default=0.25)
    parser.add_argument("--hash-width", type=int, default=192)
    parser.add_argument("--retrieval-width", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--recall-target", type=float, default=0.999)
    parser.add_argument("--uncertainty-k", type=float, default=2.5)
    parser.add_argument("--uncertainty-quantile", type=float, default=0.995)
    parser.add_argument("--threshold-shrink-quantile", type=float, default=0.75)
    parser.add_argument("--grammar-threshold-shrink-quantile", type=float, default=0.25)
    parser.add_argument("--candidate-threshold-shrink-quantile", type=float)
    parser.add_argument("--composition-threshold-shrink-quantile", type=float)
    parser.add_argument("--ood-quantile", type=float, default=0.9975)
    parser.add_argument("--min-family-samples", type=int, default=80)
    parser.add_argument("--min-family-positives", type=int, default=12)
    parser.add_argument("--retrieval-neighbors", type=int, default=5)
    parser.add_argument("--minimum-retrieval-support", type=int, default=12)
    parser.add_argument("--exploration-fraction", type=float, default=0.01)
    args = parser.parse_args()
    examples = PRUNER.load_campaign_examples(args.progress, args.manifest)
    projects = sorted({item.project for item in examples})
    folds = []
    for heldout in projects:
        train, calibration_examples = PRUNER.root_partition(examples, heldout=heldout)
        test = [item for item in examples if item.project == heldout]
        models, families = train_models(train, args)
        train_rows = predict(models, train, families, args)
        calibration_rows = predict(models, calibration_examples, families, args)
        calibration = PRUNER.calibrate(calibration_rows, train_rows, args)
        metrics = PRUNER.evaluate(predict(models, test, families, args), calibration)
        folds.append({"heldout_project": heldout, "metrics": metrics})
    positives = sum(fold["metrics"]["positives"] for fold in folds)
    misses = sum(fold["metrics"]["misses"] for fold in folds)
    branches = sum(fold["metrics"]["branches"] for fold in folds)
    pruned = sum(fold["metrics"]["policy_counts"]["PRUNE_HIGH_CONFIDENCE"] for fold in folds)
    report = {
        "schema_version": "vladder-search-pruner-summary-baseline-v1",
        "model": "histogram-gradient-boosting over pre-decision canonical graph summaries",
        "examples": len(examples),
        "roots": len({(item.project, item.root_id) for item in examples}),
        "folds": folds,
        "aggregate": {
            "branches": branches,
            "positives": positives,
            "misses": misses,
            "useful_descendant_recall": 1 - misses / max(positives, 1),
            "search_space_reduction": pruned / max(branches, 1),
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation.json").write_text(json.dumps(PRUNER._jsonable(report), indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()
