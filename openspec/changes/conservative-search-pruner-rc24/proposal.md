# Conservative Search Pruner RC24

## Why

The first v3 branch-survival model learned useful signal, but its single loss, checkpoint metric,
uncertainty estimate, and global threshold missed 41 useful branches while reporting branch-count
reduction rather than avoided search work. The existing frozen C++ corpus already contains parent
lineage, exhaustive child coverage, utility severity, failure observations, and search-cost fields.
Those records should be fully exploited before another exhaustive campaign is justified.

## What Changes

* Reconstruct complete branch forests and derive subtree utility, cost, severity, and failure labels.
* Train grammar, candidate, and composition heads in stages before joint fine-tuning.
* Add asymmetric focal survival loss, sibling ranking, failure-class, utility-severity, and subtree-cost
  auxiliary supervision.
* Select checkpoints and calibrate policies for maximum avoided subtree expansion subject to at least
  99.9% useful-descendant recall.
* Use per-stage and sufficiently supported per-family thresholds, ensemble upper-confidence bounds,
  OOD fail-open behavior, historical retrieval consensus, and an exploration reserve.
* Evaluate static decisions and online lazy-search replay separately, including severity-weighted misses.
* Compare against smaller neural encoders and a non-neural graph-summary baseline.

## Non-Goals

* Predicting candidate speedup.
* Replacing sound deterministic rejection or semantic proof.
* Allowing the model to prune new grammar families, OOD branches, or unknown actions.
* Regenerating the exhaustive corpus before the frozen-corpus ablations are complete.
