# Changelog

All notable changes to vLadder are documented here.

## 1.0.0rc4 - 2026-08-04

### Added

- `LifetimeFlowGraph` with partial-order semantic scopes, validity and final-use frontiers,
  ownership, placement, invalidation, fallback, and deterministic provenance.
- Contract-bounded trace attribution for realization redundancy, retention waste, and equivalent
  transfer redundancy.
- Five-family `lifetime-v1` grammar with Z3 transition obligations, stateful replay, agent
  realization contracts, debug-oracle requirements, and lower-level optimizer handoff.
- Isolated lifetime regression corpus with seeded stale-state and premature-retirement failures
  plus physical mechanism microbenchmarks.

### Boundaries

- Runtime traces quantify cost but cannot establish semantic invariants.
- Lifetime plans require repository-agent realization; Alive2 applies to local compiled helpers,
  not ownership, invalidation, publication, or retirement protocols.

## 1.0.0rc3 - 2026-08-04

### Added

- `vladder region inspect|optimize` for fully automatic bounded C region workflows.
- Versioned `bounded-regions-v1` support for pointwise, guarded pointwise, stencil, scan,
  recurrence, and constant-stride modulo-n indirect loops.
- Typed adapter requirements for unsupported language, ABI, loop, call, control-flow,
  memory-order, compiler, pointer-proof, and specialist graph boundaries.
- Exact ordered-unroll source regeneration with scalar tails.
- Canonical LLVM IR identity as a pre-solver refinement proof, with Alive2 retained for
  nonidentical proof IR.
- Independent automatic-region fixtures and end-to-end validation tooling.

### Distribution

- Python library, `vladder` CLI, compatibility `silicontune` alias, bundled coding-agent skill,
  Linux toolchain installer, and machine-readable grammar registry.

### Boundaries

- The common fully automatic frontend accepts canonical C regions. C++ and broader operator,
  pipeline, stateful, concurrent, and quantized regions require declared adapters.
- vLadder reports best verified measured results within a declared grammar and never claims
  universal optimality.
