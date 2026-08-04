# Changelog

All notable changes to vLadder are documented here.

## Unreleased

### Added

- `bounded-cpp-regions-v4` capability vectors separating semantic capture, actual isolation,
  candidate generation, local proof, benchmark readiness, source emission, and whole-protocol
  equivalence.
- Whole local-function identity proof units and source-preserving noinline lambda capsules for
  eligible loops nested in owning or externally interacting C++ functions.
- Guarded Clang unroll-hint candidates with deterministic placement and hashes, Z3 schedule
  obligations, explicit physical-candidate Alive2 boundaries, and fail-closed workload adapters.
- `vladder cpp synthesize` and materialized C++ audit mode with capability and categorical protocol
  aggregates and source-integrity evidence.
- `bounded-cpp-regions-v3` semantic decomposition for typed spans including byte spans, borrowed
  structured views, structured references and compiler-lowered aggregate results.
- Recursive definition-visible LLVM effect summaries combined with source-authoritative ownership,
  exception, object-state, synchronization, and runtime-control hazards.
- Five explicit C++ support tiers separating automatic source transformation from whole-function
  local IR, bounded state transitions, extractable subregions, and external protocols.
- Deterministic C++ information-flow graphs, helper-closure and subregion inventories,
  compositional proof envelopes, and inspection-only `vladder cpp audit` manifests.

### Boundaries

- Arbitrary C++ ingestion remains impossible where RAII/destructor, allocator ownership,
  exceptions, concurrency/memory order, callbacks, syscalls, Vulkan/OpenUSD, or another external
  protocol is not closed in local IR. Reports scope that blocked claim without disabling eligible
  local regions or other vLadder workflows.
- A source scheduling contract and identity proof build do not constitute Alive2 refinement of
  the physically unrolled candidate or evidence of a performance win.
- v3's broader C++ acceptance provided decomposition and proof planning; v4 adds local proof-unit
  materialization and bounded schedule-source emission while retaining separate benchmark and
  protocol gates.
- Owning containers, RAII, allocation, exceptions, synchronization, callbacks, and external APIs
  retain explicit proof and source-lowering obligations.

## 1.0.0rc5 - 2026-08-04

### Added

- `bounded-cpp-regions-v2` with exact compilation-database ingestion, Clang semantic AST target
  selection, concrete mangled-symbol provenance, and production LLVM IR extraction.
- Automatic kernel isolation for `noexcept` pointer, `std::span<float>`, and borrowed
  `std::vector<float>` views, including state-independent methods and concrete template
  specializations.
- Z3 adapter extent obligations, canonical C kernel handoff, C++ source regeneration, and the
  `vladder cpp inspect|isolate|optimize` CLI and library workflow.
- Independent C++ fixtures covering executable parity, methods, templates, containers, overloads,
  RAII, exceptions, synchronization, and external calls.

### Boundaries

- `kernel_isolated_adapter_proved` covers the bounded adapter, not a transformed candidate.
- `kernel_proved_adapter_bounded` covers the selected local kernel under adapter preconditions;
  it does not prove owning C++ object, exception, concurrency, Vulkan, OpenUSD, or callback
  protocols.

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
