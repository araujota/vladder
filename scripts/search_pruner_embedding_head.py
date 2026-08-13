#!/usr/bin/env python3
"""Fit calibrated tree heads over frozen GNN embeddings retained by a pruning run."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np

try:
    from sklearn.ensemble import HistGradientBoostingClassifier
except ImportError as error:  # pragma: no cover
    raise SystemExit("embedding-head ablation requires scikit-learn") from error


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("vladder_search_pruner", ROOT / "scripts" / "search_pruner.py")
assert SPEC and SPEC.loader
PRUNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PRUNER
SPEC.loader.exec_module(PRUNER)


def _load(path: Path, examples: dict[tuple[str, str, str], object]) -> tuple[np.ndarray, list[dict[str, object]]]:
    archive = np.load(path, allow_pickle=False)
    data = {name: archive[name] for name in archive.files}
    features = data["embedding"].astype(np.float32)
    stages = np.asarray([[float(value == stage) for stage in PRUNER.STAGES] for value in data["stage"]])
    features = np.concatenate([features, stages], axis=1)
    rows = []
    for index in range(len(data["branch_id"])):
        key = (str(data["project"][index]), str(data["root_id"][index]), str(data["branch_id"][index]))
        example = examples[key]
        rows.append(
            {
                "example": example,
                "embedding": data["embedding"][index],
                "unknown": bool(data["unknown"][index]),
                "signature": PRUNER.decision_signature(example),
            }
        )
    return features, rows


def _fit_models(train_x, train_rows, args):
    labeled = np.asarray([row["example"].target is not None for row in train_rows], dtype=np.bool_)
    train_x = train_x[labeled]
    train_rows = [row for row in train_rows if row["example"].target is not None]
    targets = np.asarray([row["example"].target for row in train_rows], dtype=np.int8)
    weights = np.asarray(
        [
            (args.positive_weight if item else 1.0)
            * (1.0 + args.subtree_weight * min(8.0, math.log1p(row["example"].subtree_cost)))
            for item, row in zip(targets, train_rows, strict=True)
        ]
    )
    models = []
    rng = np.random.default_rng(args.seed)
    for _ in range(args.ensemble_size):
        indices = rng.integers(0, len(train_rows), len(train_rows))
        model = HistGradientBoostingClassifier(
            max_iter=args.iterations, max_leaf_nodes=31, learning_rate=0.08, l2_regularization=1.0, early_stopping=False
        )
        model.fit(train_x[indices], targets[indices], sample_weight=weights[indices])
        models.append(model)
    return models


def _predict(models, target_x) -> tuple[np.ndarray, np.ndarray]:
    values = np.stack([model.predict_proba(target_x)[:, 1] for model in models])
    return values.mean(0), values.std(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, action="append", required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--positive-weight", type=float, default=80.0)
    parser.add_argument("--subtree-weight", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--recall-target", type=float, default=0.999)
    parser.add_argument("--uncertainty-k", type=float, default=2.5)
    parser.add_argument("--threshold-shrink-quantile", type=float, default=0.1)
    parser.add_argument("--grammar-threshold-shrink-quantile", type=float, default=0.1)
    parser.add_argument("--candidate-threshold-shrink-quantile", type=float)
    parser.add_argument("--composition-threshold-shrink-quantile", type=float)
    args = parser.parse_args()
    policy_args = SimpleNamespace(
        **vars(args),
        uncertainty_quantile=0.995,
        ood_quantile=0.9975,
        min_family_samples=100000,
        min_family_positives=100000,
        retrieval_width=64,
        retrieval_neighbors=5,
        minimum_retrieval_support=12,
        exploration_fraction=0.01,
    )
    corpus = PRUNER.load_campaign_examples(args.progress, args.manifest)
    examples = {(item.project, item.root_id, item.branch_id): item for item in corpus}
    folds = []
    for project in sorted({item.project for item in corpus}):
        train_x, train_rows = _load(args.run / f"fold-{project}-train.npz", examples)
        calibration_x, calibration_rows = _load(args.run / f"fold-{project}-calibration.npz", examples)
        test_x, test_rows = _load(args.run / f"fold-{project}-test.npz", examples)
        models = _fit_models(train_x, train_rows, args)
        for features, rows in ((train_x, train_rows), (calibration_x, calibration_rows), (test_x, test_rows)):
            mean, uncertainty = _predict(models, features)
            for index, row in enumerate(rows):
                row["probability"] = float(mean[index])
                row["uncertainty"] = float(uncertainty[index])
        calibration = PRUNER.calibrate(calibration_rows, train_rows, policy_args)
        folds.append({"project": project, "metrics": PRUNER.evaluate(test_rows, calibration)})
    positives = sum(fold["metrics"]["positives"] for fold in folds)
    misses = sum(fold["metrics"]["misses"] for fold in folds)
    branches = sum(fold["metrics"]["branches"] for fold in folds)
    pruned = sum(fold["metrics"]["policy_counts"]["PRUNE_HIGH_CONFIDENCE"] for fold in folds)
    report = {
        "schema_version": "vladder-search-pruner-embedding-head-ablation-v1",
        "run": str(args.run.resolve()),
        "folds": folds,
        "aggregate": {
            "branches": branches,
            "positives": positives,
            "misses": misses,
            "useful_descendant_recall": 1 - misses / max(positives, 1),
            "branch_reduction": pruned / max(branches, 1),
        },
    }
    args.output.write_text(json.dumps(PRUNER._jsonable(report), indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()
