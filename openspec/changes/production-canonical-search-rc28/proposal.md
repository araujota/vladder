# Production Canonical-State Search

## Why

RC27 established that exact canonical identity and state-scoped partial-order reduction can collapse
large numbers of redundant transformation paths while preserving bounded terminal sets. The research
engine does not yet provide production defaults, adaptive reduction selection, durable checkpoints,
concurrent identity authority, memory ceilings, complete cache/footprint telemetry, or measured
cross-system scaling and expensive-root evidence.

## What Changes

- Make canonical semantic states the production search objects for fast, guided, and exhaustive modes.
- Keep raw transformation-sequence traversal as an explicit qualification/debug mode only.
- Add a conservative adaptive policy selecting enumeration, canonicalization, or qualified POR from
  measured search cost and footprint coverage.
- Add versioned state identity, collision-safe concurrent interning, state-derived memoization,
  checkpoint/resume, memory accounting, and fail-open incremental rematerialization.
- Emit grammar-family footprint coverage, cache statistics, mechanism timing, reduction attribution,
  production defaults, and exact terminal-preservation evidence.
- Add permanent scaling, concurrency, memory, and measured proof/compiler qualification suites across
  at least three independent source systems.

## Non-Claims

Canonical hashes are not proofs. Cost estimates do not affect semantic authority. Instance-level
commutativity is not a global rewrite law. Dominance, macros, coarse equivalence, and global e-graphs
remain disabled unless separately qualified. Learned models may order but never delete search states.
