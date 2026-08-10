# Change: Search-pruner training contract v3

## Why

`vladder-model-training-bundle-v2` records semantic roots, flat candidates, and terminal evidence.
It cannot represent the parent/child search lineage, subtree coverage authority, or descendant
utility required to train a high-recall pruning oracle. Consequently an unexplored branch and an
exhaustively unproductive branch can receive indistinguishable evidence.

## What Changes

- Add `vladder-model-training-bundle-v3`, centered on searches and search branches rather than flat
  candidates.
- Record parent lineage, search stage, expansion status, exhaustive/sound/partial child coverage,
  direct utility, descendant utility, and per-branch search cost.
- Derive `KEEP`, `KEEP_UNCERTAIN`, `PRUNE_HIGH_CONFIDENCE`, and `BLOCKED_BY_CONTRACT` labels from
  evidence and coverage. Producers may not assert these labels without deterministic validation.
- Switch templates, prior exports, terminal workflow contributions, GraphML conversion, outbox,
  transport, and the private contribution service to v3.
- Retain v1 and v2 only for historical local validation. Current emission, enqueue, and upload reject
  both historical formats.

## Impact

The new contract supports grammar-family, candidate-family, composition, and cross-TU pruning
heads. Existing flat prior records remain exportable, but are honestly represented as partial
one-level searches and therefore default to `KEEP_UNCERTAIN` unless they contain positive evidence
or a sound contract closure.
