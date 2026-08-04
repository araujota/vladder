## Why

vLadder models producers, consumers, materialization, and implementation choices, but it does not
yet model how often a semantic value is realized, how long that realization remains valid, where it
resides, or which transitions invalidate it. Recent architecture-level wins are instances of this
missing dimension: retaining immutable derivations across a generation, reusing a serialized body
across fragments, and eliminating an unobserved GPU intermediate.

## What Changes

- Add a deterministic `LifetimeFlowGraph` over existing expression, operator, pipeline, GPU,
  transport, and repository graphs.
- Add trace attribution for repeated construction, over-retention, and redundant transfer.
- Add a bounded lifetime grammar for retention, serialization reuse, immutable/mutable splitting,
  intermediate elimination or retirement, and placement residency.
- Generate structural and Z3 state-transition obligations for derivation, reuse, invalidation,
  publication, retirement, and placement.
- Emit an explicit agent realization contract for repository-level implementation work.
- Add an isolated regression corpus and physical microbenchmarks without modifying NeuralFusion.
- Extend README, skill, package data, CLI, and release validation after the new gates pass.

## Impact

Lifetime optimization becomes an additive layer above existing compiled-code superoptimization.
It does not claim automatic arbitrary repository rewriting or that Alive2 proves lifecycle
protocols. Unsupported ownership and concurrency models fail closed with adapter requirements.
