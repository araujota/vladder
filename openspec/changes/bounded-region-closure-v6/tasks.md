## 1. Model

- [x] 1.1 Add deterministic RegionClosureGraph types and shared semantic nodes.
- [x] 1.2 Capture C and C++ ABI projections, aggregate results, exits, helper summaries, and ownership guards.
- [x] 1.3 Emit typed Z3 and structural proof obligations with exact artifact binding.

## 2. Lowering

- [x] 2.1 Distinguish modeled noncanonical C ABIs from truly unmodeled ABIs.
- [x] 2.2 Add whole-function scheduling realization for local multi-exit loops.
- [x] 2.3 Admit guarded no-growth trivial container regions without weakening owning-wrapper claims.
- [x] 2.4 Make aggregate and helper closure actionable at IR while keeping source/protocol limits explicit.

## 3. Validation

- [x] 3.1 Add C and C++ fixtures for scalar/aggregate ABI, local exits, local helpers, and no-growth output.
- [x] 3.2 Seed exception, indirect-call, reallocation, and nontrivial-ownership failures.
- [x] 3.3 Re-run relevant upstream/no-write acceptance and the complete test suite.
- [x] 3.4 Validate OpenSpec strictly and document the closed and irreducible boundaries.
