# Tasks

## Corpus Derivation

- [x] Reconstruct branch forests from the frozen 770-root v3 corpus.
- [x] Derive subtree size, avoided cost, failure mode, utility severity, and sibling groups.
- [x] Verify that derived outcome fields never enter inference features.

## Training

- [x] Add configurable small and full encoders with explicit handcrafted decision features.
- [x] Add staged head training, asymmetric focal loss, sibling ranking, and auxiliary objectives.
- [x] Add hard-positive and hard-negative mining without dropping rare positives.
- [x] Add independent-seed ensemble training.

## Calibration And Policy

- [x] Add per-stage and supported per-family risk calibration.
- [x] Prune on ensemble upper confidence bounds with branch-level OOD fail-open behavior.
- [x] Add historical retrieval consensus and exploration reserve.

## Evaluation

- [x] Add online lazy-search replay and avoided subtree/proof/compiler cost metrics.
- [x] Report stage, family, project, severity, and held-project results separately.
- [x] Compare smaller GNN and graph-summary non-neural baselines.
- [x] Select the maximum reduction policy satisfying at least 99.9% useful-descendant recall.

## Validation

- [x] Add focused tests for lineage derivation, calibration, OOD, retrieval, and replay.
- [x] Run strict OpenSpec and project quality gates.
- [x] Document whether frozen-corpus performance justifies or rejects a new data campaign.
