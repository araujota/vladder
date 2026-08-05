## Why

RC10 closes exact byte predicate reductions but loses the predicate result after reducing it to a
count. Production C++ paths frequently need the selected indices or values, an exact output extent,
and an atomic state update. NeuralFusion's sparse P2, packet codec, Route A, and fixed 4x4 block
paths demonstrate that these semantics are load-bearing and currently remain behind container,
allocation, and protocol adapters.

## What Changes

- Add a language-neutral bounded-dataflow grammar over SemanticFlowGraph v2.
- Model capacity, output extent, stability, failure atomicity, state publication, and numerical
  quality as typed contracts and proof obligations.
- Close explicitly guarded C++ spans and no-growth contiguous containers with trivial element
  lifetime; preserve owning wrappers as protocol boundaries.
- Add executable C++ realizations and bounded proofs for stable compaction, exact codecs, stateful
  deltas, AoS fused reductions, and deterministic 4x4 packed blocks.
- Add a no-write repository audit that classifies production regions without editing source.

## Non-Claims

This change does not prove arbitrary `std::vector` growth, allocators, throwing element
construction, concurrent publication, external APIs, floating-point reassociation, or whole owning
C++ wrappers. AVX-512 terminals require a checked ISA guard. Bounded-quality block candidates are
not exact unless their encoded or decoded observables satisfy the selected exact contract.
