## ADDED Requirements

### Requirement: Useful-descendant preservation

The learned policy SHALL optimize avoided lazy-search work subject to a declared useful-descendant
recall floor and SHALL NOT select checkpoints by ordinary classification accuracy alone.

#### Scenario: Select an operating point

- **GIVEN** held-project exhaustive search traces
- **WHEN** policy thresholds are selected
- **THEN** the report identifies the maximum avoided expansion rate satisfying at least 99.9% useful-descendant recall.

### Requirement: Decision-stage calibration

Grammar, candidate, and composition decisions SHALL use independently trained heads and independently
calibrated thresholds, with family-specific thresholds only when calibration support is sufficient.

#### Scenario: Sparse semantic family

- **GIVEN** a family without enough calibration positives
- **WHEN** its branch reaches the learned policy
- **THEN** the policy uses the conservative stage fallback or keeps the branch uncertain.

### Requirement: Fail-open selective prediction

Unknown actions, new grammar families, decision-level OOD branches, high-uncertainty branches, and the
exploration reserve SHALL not be pruned by the learned policy.

#### Scenario: New grammar action

- **GIVEN** an action token absent from training vocabulary
- **WHEN** the policy evaluates the branch
- **THEN** it returns `KEEP_UNCERTAIN`.

### Requirement: Search-tree evaluation

Evaluation SHALL replay lazy search so that pruning an ancestor suppresses descendant creation and
shall report avoided branch evaluations, proof/compiler calls where known, and useful terminals lost.

#### Scenario: Pruned dead subtree

- **GIVEN** a dead branch with one hundred descendants
- **WHEN** the branch is safely pruned
- **THEN** online replay counts the subtree once rather than one independent branch decision at a time.

### Requirement: Outcome-feature isolation

Post-search subtree utility, failure observations, proof outcomes, and measured costs SHALL be used as
supervision or evaluation targets only and SHALL not enter live inference features.

#### Scenario: Tensorize a training branch

- **GIVEN** two branches with identical pre-decision contexts and different outcomes
- **WHEN** they are tensorized for inference
- **THEN** their inference tensors are identical.
