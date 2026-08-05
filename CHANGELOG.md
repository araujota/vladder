# Changelog

All notable changes to vLadder are documented here.

## Unreleased

## 1.0.0rc11 - 2026-08-05

### Added

- `bounded-dataflow-v1`, a language-neutral SemanticFlowGraph v2 grammar for stable variable-output
  compaction, exact fixed-width codecs, transactional state deltas, AoS projected multi-reductions,
  and deterministic 4x4 packed blocks.
- Seventeen native C++20 terminals with guarded AVX2/AVX-512 fallbacks, Z3 sequence/bitvector/state
  obligations, local codec Alive2 evidence, compiled differential oracles, and source/graph hashes.
- Contract-bounded no-growth C++ container closure and a fail-closed, tracked-source no-write
  repository acceptance audit.

### Boundaries

- Owning allocation, nontrivial elements, exceptions, concurrent publication, and external
  protocols remain explicit adapters. A proved borrowed dataflow region is not a whole-wrapper or
  application equivalence claim.
- NeuralFusion validation is read-only archetype acceptance. It generated no production patch and
  establishes no application speedup.

## 1.0.0rc10 - 2026-08-05

### Added

- `SemanticFlowGraph v2` with typed, hash-bound obligations, effects, protocol transitions, and
  claims plus fail-closed reference validation and deterministic v1 string normalization.
- Authoritative v2 graph production for the bounded C frontend and Clang/LLVM C++ closure
  frontend, including typed memory, allocation, cleanup, exception, synchronization, ownership,
  state, and external-call evidence.
- Native C++20, Zig, and Julia emitters for every executable `deep-v2` terminal, including scalar,
  packed-word SWAR, SIMD mask/popcount, bounded byte-lane accumulation, and guarded realizations.
- Five-language source reconstruction, typed emitter obligations, native differential harnesses,
  LLVM/assembly capture, and CLI ranking support.

### Boundaries

- Shared semantic shape does not erase language runtime contracts. C++ `noexcept`/ownership, Zig
  pointer/safety/target, and Julia rooting/world/specialization obligations remain explicit.
- Alive2 proves compatible canonical LLVM cores; native frontend, runtime, and external protocol
  semantics retain their typed proof boundaries and differential/project evidence.

## 1.0.0rc9 - 2026-08-05

### Added

- Native `bounded-zig-regions-v1` and `bounded-julia-regions-v1` adapters over the existing
  language-neutral `SemanticFlowGraph`; no language-specific information-flow ontology was added.
- Zig compiler/build/safety capture, LLVM and assembly provenance, native source regeneration,
  source-derived schedules, Z3 and canonical Alive2 proof, differential execution, paired physical
  ranking, audit, CLI, library, workflow, diagnostics, examples, and installer support.
- Julia project/manifest/world/specialization capture with lowered, typed, LLVM, and native IR,
  inferred type/effect/allocation checks, native method regeneration, schedule proof, warmed
  independent-process ranking, audit, CLI, library, workflow, diagnostics, and examples.
- Checksum-verified Zig and Julia toolchain bootstrapping shared by local installation, CI, and the
  release workflow so native adapter tests cannot silently disappear from release evidence.

### Boundaries

- Z1 excludes allocator/error/defer/volatile/atomic/assembly/FFI protocols. J1 applies to one
  concrete type-stable zero-allocation method specialization and excludes other worlds, dynamic
  dispatch, GC ownership, globals, tasks, exceptions, nondeterminism, and external calls.
- Native Zig/Julia LLVM is retained as compiler provenance. Alive2 validates the source-derived
  canonical schedule lowerer; this is not relabeled as direct proof of Zig frontend attributes or
  Julia's GC/safepoint ABI.

## 1.0.0rc8 - 2026-08-05

### Added

- `deep-v2`, an executable shared physical-realization grammar for exact byte-predicate reductions
  spanning scalar, packed-word SWAR, SIMD masks/popcount, bounded SIMD byte accumulators, tails,
  fusion, constants, traversal, and guarded ISA dispatch.
- One language-neutral `SemanticFlowGraph` vocabulary for lanes, packs, masks, population counts,
  horizontal reductions, materialization, complexity, and dispatch, with deterministic native C
  and Rust regeneration from the same derivation.
- Layered Z3 obligations for bit-vector identities, lane packing, reductions, bounded accumulator
  no-wrap, traversal/tails, constants, and dispatch, plus bidirectional Alive2 refinements for
  vector mask/popcount and byte-accumulator cores.
- `vladder deep coverage|graph|search|emit|benchmark|rank|audit|neuralfusion-audit`, including
  saturated local derivation search, normalized assembly deduplication, randomized paired ranking,
  and explicit representation/grammar/lowering/proof/performance failure stages.
- Pinned expert-transfer evaluation against `bytecount` and read-only NeuralFusion evidence
  validation. The generated guarded Rust realization beat the upstream runtime-dispatched expert
  path by 6.07% in the same executable on the reference host.

### Corrected Claim Boundary

- A baseline win is dispositive only for the executable grammar region actually audited. Unknown
  expert realizations or failures before physical ranking are grammar/tooling gaps, not evidence
  that no faster semantic equivalent exists.
- `bounded_optimal_local` requires finite saturated derivation coverage, successful native
  lowering and proof, assembly-identity accounting, and physical ranking of every unique terminal.
  LLVM-wide, algorithm-wide, and whole-program optimality remain explicitly unclaimed.

## 1.0.0rc7 - 2026-08-04

### Added

- A versioned, language-neutral adapter protocol and deterministic `SemanticFlowGraph` shared by
  C, C++, and Rust rather than parallel language-specific information-flow vocabularies.
- `bounded-rust-regions-v1` with Cargo target capture, exact rustc identity, source/MIR/LLVM/assembly
  provenance, safe-region effect closure, and native Rust source regeneration.
- Parametric schedule proofs plus bounded MIR-derived Z3 obligations, fixed-length bidirectional
  Alive2 refinement, adversarial differential execution, and randomized same-executable physical
  ranking for the first exact byte-reduction grammar.
- `vladder rust inspect|isolate|synthesize|optimize|audit|support`, library integration, canonical
  agent workflow routing, release diagnostics, installer support, examples, and regression tests.

### Boundaries

- Rust R1 is not arbitrary Rust equivalence. Unsafe contracts, allocation and owning containers,
  custom `Drop`, panic recovery, async, concurrency, FFI, inline assembly, unresolved calls, and
  external protocols fail closed with named adapter requirements.
- Textual MIR evidence is pinned to the exact rustc build. Alive2 compatibility normalization may
  erase unsupported assumptions and metadata but never executable operations, and all before/after
  hashes are retained.
- Local proof and speedup do not establish project-level value until the native patch, project
  tests, and attributed project workload pass.

## 1.0.0rc6 - 2026-08-04

### Added

- Manifest-driven agent workflow with resumable content identities, queryable artifact lineage,
  five decisive artifacts, one next action, and a unified promotion state machine.
- Deterministic C++ application adapter bundles generated from closure metadata, plus concrete
  recovery recipes for overloads, templates, member state, owning views, callbacks, coroutines,
  and external protocols.
- Bounded Z3 verification for versioned-cache and transactional-publication state projections.
- Randomized same-executable paired-process benchmarks with bootstrap intervals, exact observable
  checks, retained-revalidation classification, and overlap-safe effect composition.
- Lifetime trace sufficiency gating that reports `insufficient_attribution` instead of producing
  a technically successful empty search.
- Portable GLSL/SPIR-V compute inspection and bounded synthesis with structural validation,
  explicit output-oracle/device-timestamp promotion gates, and CUDA toolchain disposition.
- Content-addressed C++ matrix reuse keyed by source, compilation database, selected symbol,
  support version, and isolation mode.

### Boundaries

- Generated application adapters are incomplete contracts, not proof or benchmark evidence.
- SPIR-V validation and optimizer provenance do not establish shader output equivalence.
- Generic whole-function C++ proof remains unavailable when relevant ownership, exception,
  concurrency, callback, syscall, driver, or external protocol state is outside the modeled
  finite boundary.

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
