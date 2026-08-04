# Change: Pipeline Verification V4

## Why

Cross-operator transformations alter lifetimes, traversal, state, and numerical error
composition beyond V3's single-operator obligations.

## What Changes

- Add structural graph refinement and footprint verification.
- Add composed numerical contracts and sequence-level differential tests.
- Verify cache claims as performance assumptions, never semantic premises.

## Success

Only candidates preserving external tensors, state transitions, bounds, observers,
sampling semantics, and declared numerical budgets can enter ranking.
