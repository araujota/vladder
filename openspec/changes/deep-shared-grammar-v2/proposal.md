## Why

vLadder's registry describes broad optimization concerns, but many registered rules currently
lower only to declarative plans or route into narrow shape-specific generators. The Rust
`bytecount` study made the consequence measurable: vLadder proved and rejected five scalar
schedule variants while an expert word/SIMD realization was about 8.16 times faster than the
selected scalar baseline. The proof and measurement gates worked; the executable grammar did not
contain the important representation change.

## What Changes

- Introduce a language-neutral deep realization graph for lanes, words, vectors, masks,
  reductions, traversal, tails, dispatch, fusion, tables, and complexity bounds.
- Add deterministic, proof-backed derivations from scalar map/reduce semantics to word-parallel,
  SIMD, fused, and guarded physical realizations.
- Require every promoted deep rule to construct a target graph, emit native C and Rust source for
  an explicitly supported bounded region, generate proof obligations, and enter a same-executable
  physical benchmark.
- Add an expert-implementation audit that independently classifies representation, grammar,
  lowering, proof, and performance coverage.
- Validate with C and Rust byte-oriented kernels and inspect NeuralFusion evidence read-only,
  without changing any validation repository.

## Non-Claims

The change does not claim arbitrary source synthesis, arbitrary vectorization, global optimality,
or proof of language ownership and external protocols absent from the selected bounded region.
Language adapters continue to own overflow, provenance, panic, exception, alias, and ownership
contracts; they do not receive separate optimization vocabularies.
