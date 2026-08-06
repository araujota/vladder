## 1. Contracts And Index

- [x] 1.1 Define deterministic whole-build, summary, slice, ownership, and proof schemas.
- [x] 1.2 Implement compile-database and object-symbol indexing.
- [x] 1.3 Detect unique, unresolved, and ambiguous/ODR definitions.

## 2. Cross-TU Semantic Closure

- [x] 2.1 Implement persistent on-demand LLVM function summaries.
- [x] 2.2 Upgrade resolvable cross-TU calls from opaque to definition edges.
- [x] 2.3 Implement bounded upstream and downstream program slicing.
- [x] 2.4 Implement ownership/resource closure derivation.

## 3. Proof And Workflow

- [x] 3.1 Implement compositional Z3 proof obligations and SMT artifacts.
- [x] 3.2 Add `vladder build index` and `vladder build closure` commands.
- [x] 3.3 Add public schemas, documentation, skill recipes, and decisive summaries.

## 4. Verification

- [x] 4.1 Add multi-TU positive, external-boundary, callback, ownership, and ambiguity tests.
- [x] 4.2 Run the full vLadder test and release suites.
- [x] 4.3 Evaluate NeuralFusion read-only and quantify resolved versus irreducible boundaries.
- [x] 4.4 Install and validate the resulting release candidate.
