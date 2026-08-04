## 1. Research And Architecture

- [x] 1.1 Audit the NeuralFusion rc5 acceptance matrix and reproduce representative false blockers.
- [x] 1.2 Research Clang dataflow, LLVM effect attributes and CodeExtractor, Alive2 boundaries, and
  CBMC bounded C++ proof practice from primary sources.
- [x] 1.3 Define support tiers, typed ABI schema, effect authority, and compositional proof claims.

## 2. Effect-Aware Frontend

- [x] 2.1 Emit and hash deterministic optimized effect IR for the selected production symbol.
- [x] 2.2 Classify remaining calls, allocation, unwind, synchronization, memory, and lowered ABI.
- [x] 2.3 Replace source-name helper and blanket constructor rejection with combined AST/IR facts.
- [x] 2.4 Add typed descriptors for scalar, pointer, span, borrowed vector, structured, callable,
  and aggregate-return boundaries.

## 3. Region And Proof Planning

- [x] 3.1 Add explicit support tiers and separate transformation readiness from semantic acceptance.
- [x] 3.2 Discover bounded nested source regions and emit source/effect hazards.
- [x] 3.3 Emit proof ABI and compositional verifier obligations for each accepted tier.
- [x] 3.4 Fail closed in `cpp optimize` for accepted tiers without executable source lowerers.

## 4. Audit Surface And Corpus

- [x] 4.1 Add an inspection-only C++ matrix manifest and aggregate report API/CLI.
- [x] 4.2 Add independent byte-span, aggregate-result, helper-inlining, inferred-no-unwind,
  structured-view, allocation, object-state, external-call, and subregion fixtures.
- [x] 4.3 Add regressions proving external protocols and owning operations remain adapter-bound.

## 5. Documentation And Validation

- [x] 5.1 Update architecture, C++ frontend, README, examples, and bundled skill guidance.
- [x] 5.2 Run focused and complete tests, strict OpenSpec validation, and dependency diagnostics.
- [x] 5.3 Run the NeuralFusion matrix in inspection-only mode and record tier/blocker deltas without
  optimizing or modifying NeuralFusion.
