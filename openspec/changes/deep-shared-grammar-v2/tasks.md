## 1. Research And Audit

- [x] 1.1 Audit current graph, registry, lowerer, source, proof, and benchmark coverage.
- [x] 1.2 Research equality saturation, LLVM vector planning, SIMD synthesis, and expert kernels.
- [x] 1.3 Validate this OpenSpec change strictly before implementation completion.

## 2. Shared Deep IR And Grammar

- [x] 2.1 Extend the common semantic vocabulary with lane, word, vector, mask, reduction, tail,
  dispatch, table, fusion, and complexity concepts.
- [x] 2.2 Implement deterministic realization graphs, typed rules, derivation search, graph hashes,
  and bounded-optimality classification.
- [x] 2.3 Implement executable families for every high-value transformation named in the spec.

## 3. Native Lowering And Proof

- [x] 3.1 Implement native C and Rust emitters from the same realization plans.
- [x] 3.2 Generate Z3 obligations for lane identities, reductions, coverage, tails, overflow, and
  dispatch.
- [x] 3.3 Generate LLVM/Alive2 evidence where compatible and native differential evidence for all
  candidates.
- [x] 3.4 Implement randomized paired physical ranking and assembly-identity deduplication.

## 4. Grammar Audit

- [x] 4.1 Implement representation/derivation/lowering/proof/performance audit stages.
- [x] 4.2 Audit multiple known scalar/expert C and Rust implementations.
- [x] 4.3 Emit explicit failure classifications and decisive artifact lineage.

## 5. Validation And Product Surface

- [x] 5.1 Add C and Rust fixtures, counterexample tests, and end-to-end CLI/API tests.
- [x] 5.2 Validate NeuralFusion evidence read-only and retain before/after fingerprints.
- [x] 5.3 Update registry, CLI, API, README, architecture, skill, examples, and packaging.
- [x] 5.4 Run the complete regression, strict doctor, strict OpenSpec validation, package audit,
  and installed-skill smoke test.
