## Architecture

`BoundedDataflowGraph` is an executable grammar layer over SemanticFlowGraph v2. It uses shared
semantic nodes (`CapacityGuard`, `Mask`, `PrefixScan`, `Compact`, `Codec`, `Project`, `Commit`,
`Rollback`, and `Tile`) while C++ spans, vectors, trivial structs, and exception behavior remain
typed language bindings and protocol obligations.

The search hierarchy is:

1. infer or load a finite semantic contract;
2. validate borrowed inputs, caller-owned output, capacity, aliasing, and failure policy;
3. derive scalar, fused, mask/scan, SIMD, or guarded realizations;
4. emit native C++20 with no allocation in the generated kernel;
5. prove bounded sequence, bitvector, state, and capacity obligations with Z3;
6. bind generated source and, where tractable, local LLVM refinements;
7. differentially execute all outputs, extents, status, and state;
8. leave application integration and physical promotion to a paired workload adapter.

## Families

### Predicate, Mask, Stable Compaction

The contract defines predicate, output mode, order, capacity, overflow behavior, and aliasing.
Terminals include scalar two-pass, fused stable, mask-prefix stable, guarded AVX2 mask extraction,
and guarded AVX-512 compress-store where supported. Exact failure-atomic output uses a count/capacity
guard before writes.

### Bounded C++ Closure

The frontend recognizes `std::span`, contiguous iterator/data-size pairs, and `std::vector` views.
No-growth append is admitted only with a checked `size + maximum_output <= capacity` guard,
trivially copyable/destructible elements, no alias violation, and no throwing operation in the
closed region. Otherwise it emits a specific adapter requirement without blocking other regions.

### Fixed-Width Codecs

Typed fields lower to exact endian/bit placement with fused scalar and word-store realizations.
Malformed-input behavior, field bounds, shifts, padding, and output capacity are observables.

### Stateful Delta Transducers

The generated kernel computes a bounded delta into caller-owned storage and a candidate next state.
State publication is separate: capacity failure rolls back output extent and state; success commits
both. Z3 proves reconstruction and transition atomicity for the bounded model. Concurrency and
external acknowledgement transport remain protocol adapters.

### AoS Multi-Reduction

The grammar projects trivial fields and fuses predicates, counters, byte totals, or bounded
histograms into one traversal. It does not claim that an AoS-to-SoA conversion is universally
beneficial.

### Quantized 4x4 Blocks

The grammar models fixed tiles, endpoint reduction, deterministic palette construction, nearest
index selection, and packed output. Proof classes are exact encoded bytes, exact decoded values,
or bounded quality with deterministic tie-breaking. Classes are never combined in reporting.

## Research Basis

LLVM exposes masked compress-store semantics and Clang exposes corresponding masked builtins;
prefix scans are the standard stable-compaction offset primitive. LLVM's own vectorizer documents
that complicated control flow and memory effects inhibit ordinary loop vectorization, which is why
this graph-level family is not reducible to a compiler flag. C++ capacity guarantees support a
finite no-reallocation contract, but do not remove construction, exception, or lifetime
obligations. Alive2 validates local LLVM refinement; Z3 arrays and bitvectors model bounded output
sequences, codecs, and state transitions.

## NeuralFusion Validation

Validation is read-only. The audit hashes tracked source before and after, consumes the production
compilation database, and classifies the four rc10 sample functions. It may report local archetype
closure or an adapter plan, but must not generate or apply a NeuralFusion patch and must not claim a
speedup.
