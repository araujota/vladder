#!/usr/bin/env python3
"""Sweep conservative policies over retained held-project predictions without retraining."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("vladder_search_pruner", ROOT / "scripts" / "search_pruner.py")
assert SPEC and SPEC.loader
PRUNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PRUNER
SPEC.loader.exec_module(PRUNER)


def _rows(path: Path, examples: dict[tuple[str, str, str], object]) -> list[dict[str, object]]:
    archive = np.load(path, allow_pickle=False)
    data = {name: archive[name] for name in archive.files}
    result = []
    for index in range(len(data["branch_id"])):
        key = (str(data["project"][index]), str(data["root_id"][index]), str(data["branch_id"][index]))
        example = examples[key]
        result.append(
            {
                "example": example,
                "probability": float(data["probability"][index]),
                "uncertainty": float(data["uncertainty"][index]),
                "embedding": data["embedding"][index],
                "unknown": bool(data["unknown"][index]),
                "signature": PRUNER.decision_signature(example),
            }
        )
    return result


def _values(raw: str) -> list[float]:
    return [float(item) for item in raw.split(",")]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path, action="append", required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-quantiles", default="0.05,0.075,0.1")
    parser.add_argument("--composition-quantiles", default="0.05,0.075,0.1")
    parser.add_argument("--grammar-quantiles", default="0.02,0.05,0.1,0.2")
    parser.add_argument("--uncertainty-k", default="2.0,3.0")
    parser.add_argument("--recall-target", type=float, default=0.999)
    parser.add_argument("--exploration-fractions", "--exploration-fraction", default="0.01")
    parser.add_argument("--retrieval-neighbors", default="5")
    parser.add_argument("--minimum-retrieval-support", default="12")
    parser.add_argument("--uncertainty-quantiles", default="0.995")
    parser.add_argument("--ood-quantiles", default="0.9975")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--model-output", type=Path)
    parser.add_argument("--mc-samples", type=int, default=2)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()

    corpus = PRUNER.load_campaign_examples(args.progress, args.manifest)
    examples = {(item.project, item.root_id, item.branch_id): item for item in corpus}
    projects = sorted({item.project for item in corpus})
    cached = {}
    for project in projects:
        cached[project] = {
            split: _rows(args.run / f"fold-{project}-{split}.npz", examples)
            for split in ("train", "calibration", "test")
        }

    leaderboard = []
    for candidate_quantile in _values(args.candidate_quantiles):
        for composition_quantile in _values(args.composition_quantiles):
            for grammar_quantile in _values(args.grammar_quantiles):
                for uncertainty_k in _values(args.uncertainty_k):
                    for exploration_fraction in _values(args.exploration_fractions):
                        for retrieval_neighbors in [int(value) for value in _values(args.retrieval_neighbors)]:
                            for minimum_retrieval_support in [
                                int(value) for value in _values(args.minimum_retrieval_support)
                            ]:
                                for uncertainty_quantile in _values(args.uncertainty_quantiles):
                                    for ood_quantile in _values(args.ood_quantiles):
                                        leaderboard.append(
                                            _evaluate_policy(
                                                cached,
                                                projects,
                                                args,
                                                candidate_quantile,
                                                composition_quantile,
                                                grammar_quantile,
                                                uncertainty_k,
                                                exploration_fraction,
                                                retrieval_neighbors,
                                                minimum_retrieval_support,
                                                uncertainty_quantile,
                                                ood_quantile,
                                            )
                                        )

    leaderboard.sort(
        key=lambda item: (
            item["operating_point_met"],
            item["per_project_operating_point_met"],
            item["online_work_reduction"],
        ),
        reverse=True,
    )
    report = {
        "schema_version": "vladder-search-pruner-policy-sweep-v1",
        "run": str(args.run.resolve()),
        "recall_target": args.recall_target,
        "trials": leaderboard,
        "best": leaderboard[0],
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.model:
        import torch

        device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
        artifact = torch.load(args.model, map_location="cpu", weights_only=True)
        vocab = PRUNER.Vocab(artifact["vocab"])
        config = PRUNER.ModelConfig(**artifact["config"])
        models = []
        for state_dict in artifact.get("state_dicts") or [artifact["state_dict"]]:
            model = PRUNER.SurvivalModel(vocab, config)
            model.load_state_dict(state_dict)
            model.to(device)
            models.append(model)
        training, calibration_examples = PRUNER.root_partition(corpus)
        prediction_args = SimpleNamespace(batch_size=96, mc_samples=args.mc_samples)
        training_rows = PRUNER.predict(models, training, vocab, prediction_args, device)
        calibration_rows = PRUNER.predict(models, calibration_examples, vocab, prediction_args, device)
        best = report["best"]
        policy_args = _policy_args(args, best, config.retrieval_width)
        artifact["calibration"] = PRUNER.calibrate(calibration_rows, training_rows, policy_args)
        artifact["policy_validation"] = {
            "source": str(args.output.resolve()),
            "status": "shadow_only",
            "operating_point": best,
            "calibration_scope": "final-model held-back roots; not additional evaluation evidence",
        }
        model_output = args.model_output or args.run / "model-conservative.pt"
        torch.save(artifact, model_output)
        report["serving_artifact"] = str(model_output.resolve())
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["best"], indent=2))


def _policy_args(args, values, retrieval_width=64):
    return SimpleNamespace(
        recall_target=args.recall_target,
        uncertainty_k=values["uncertainty_k"],
        uncertainty_quantile=values["uncertainty_quantile"],
        threshold_shrink_quantile=values["candidate_quantile"],
        candidate_threshold_shrink_quantile=values["candidate_quantile"],
        composition_threshold_shrink_quantile=values["composition_quantile"],
        grammar_threshold_shrink_quantile=values["grammar_quantile"],
        ood_quantile=values["ood_quantile"],
        min_family_samples=100000,
        min_family_positives=100000,
        enable_family_thresholds=False,
        retrieval_width=retrieval_width,
        retrieval_neighbors=values["retrieval_neighbors"],
        minimum_retrieval_support=values["minimum_retrieval_support"],
        exploration_fraction=values["exploration_fraction"],
    )


def _evaluate_policy(
    cached,
    projects,
    args,
    candidate_quantile,
    composition_quantile,
    grammar_quantile,
    uncertainty_k,
    exploration_fraction,
    retrieval_neighbors,
    minimum_retrieval_support,
    uncertainty_quantile,
    ood_quantile,
):
    values = {
        "candidate_quantile": candidate_quantile,
        "composition_quantile": composition_quantile,
        "grammar_quantile": grammar_quantile,
        "uncertainty_k": uncertainty_k,
        "exploration_fraction": exploration_fraction,
        "retrieval_neighbors": retrieval_neighbors,
        "minimum_retrieval_support": minimum_retrieval_support,
        "uncertainty_quantile": uncertainty_quantile,
        "ood_quantile": ood_quantile,
    }
    retrieval_width = next(iter(cached.values()))["train"][0]["embedding"].shape[0]
    policy_args = _policy_args(args, values, retrieval_width)
    folds = []
    for project in projects:
        rows = cached[project]
        calibration = PRUNER.calibrate(rows["calibration"], rows["train"], policy_args)
        folds.append({"project": project, "metrics": PRUNER.evaluate(rows["test"], calibration)})
    positives = sum(fold["metrics"]["positives"] for fold in folds)
    misses = sum(fold["metrics"]["misses"] for fold in folds)
    branches = sum(fold["metrics"]["branches"] for fold in folds)
    pruned = sum(fold["metrics"]["policy_counts"]["PRUNE_HIGH_CONFIDENCE"] for fold in folds)
    work = sum(fold["metrics"]["online_replay"]["total_work_units"] for fold in folds)
    avoided = sum(fold["metrics"]["online_replay"]["avoided_work_units"] for fold in folds)
    terminals = sum(fold["metrics"]["online_replay"]["useful_terminals"] for fold in folds)
    killed = sum(fold["metrics"]["online_replay"]["killed_useful_terminals"] for fold in folds)
    allowed = math.floor((1 - args.recall_target) * positives + 1e-12)
    per_project_safe = all(
        fold["metrics"]["misses"] <= math.floor((1 - args.recall_target) * fold["metrics"]["positives"] + 1e-12)
        for fold in folds
    )
    return {
        **values,
        "branches": branches,
        "positives": positives,
        "misses": misses,
        "allowed_misses": allowed,
        "useful_descendant_recall": 1 - misses / max(positives, 1),
        "branch_reduction": pruned / max(branches, 1),
        "online_work_reduction": avoided / max(work, 1e-12),
        "useful_terminal_survival": 1 - killed / max(terminals, 1),
        "operating_point_met": misses <= allowed and killed <= math.floor((1 - args.recall_target) * terminals + 1e-12),
        "per_project_operating_point_met": per_project_safe,
        "folds": [
            {
                "project": fold["project"],
                "misses": fold["metrics"]["misses"],
                "recall": fold["metrics"]["useful_descendant_recall"],
                "branch_reduction": fold["metrics"]["search_space_reduction"],
                "online_work_reduction": fold["metrics"]["online_replay"]["online_work_reduction"],
                "stage_metrics": fold["metrics"]["stage_metrics"],
            }
            for fold in folds
        ],
    }


if __name__ == "__main__":
    main()
