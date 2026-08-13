# Canonical-State Search Reduction

## Why

RC26 collapsed 38,656 of 66,882 generated states through exact identities, but the search runtime
still treats transformation paths as its primary trace object. It lacks an authoritative quotient
DAG, collision-safe state identity, verified action independence, partial-order reduction, and
mechanism-resolved cost attribution. Learned ordering recovered only 62% of composition terminals at
30% work and therefore cannot serve as deletion authority.

## What Changes

- Make canonical semantic states the search nodes and transformation applications the DAG edges.
- Validate hash matches through canonical bytes, observable summaries, contracts, and enabled actions.
- Aggregate all parent paths, depth bounds, terminal evidence, and memoized summaries in one state record.
- Add conservative action footprints, grammar dependencies, state-scoped AB/BA commutativity checks,
  sleep-set and dynamic partial-order reduction, typed symmetry normalization, and alpha equivalence.
- Add proof-gated dominance, qualified macros, and a bounded local e-graph feasibility layer without
  granting them production deletion authority prematurely.
- Qualify every exact reduction against full canonical exhaustive terminal sets and report a
  non-overlapping reduction waterfall and net cost.

## Non-Claims

Hash equality alone is not semantic identity. Observed commutativity is state-scoped unless a general
proof exists. Structural cost does not establish dominance. Learned policy changes order only. Local
e-graphs do not model arbitrary ownership, protocol, cross-TU, or asynchronous state.
