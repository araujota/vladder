# Tasks

Status key: checked items are implemented and covered by the end-to-end v2 run.

## 1. Lower To IR

- [x] Add a normalized IR emission mode distinct from benchmark harness IR.
- [x] Emit target-only `.ll` files for the selected `transform` function.
- [x] Store compiler flags and LLVM version in graph metadata.
- [x] Emit target-only `.ll` files for every candidate slice before benchmarking.

## 2. Semantic Slice

- [x] Implement function-level IR parser or bind to LLVM tooling.
- [x] Extract target-only IR so unrelated benchmark harness code is not present.
- [x] Extract output-producing slices rooted at `dst` stores with dependence edges.
- [x] Remove unrelated harness/control code from analysis artifacts.

## 3. Information-Flow Graph

- [x] Define graph node/edge schema.
- [x] Serialize graphs as JSON for reports and tests.
- [x] Build graphs for pointwise map, clamp, stencil, recurrence, and indirect kernels.

## 4. Flow-Shape Classification

- [x] Implement classifier for pointwise, guarded pointwise, stencil,
  recurrence, reduction/scan, and indirect access.
- [x] Add corpus classification report.
- [x] Add tests for all 25 corpus kernels.

## 5. Canonicalization

- [x] Normalize selected branch/select forms.
- [x] Normalize affine and exact strength-reduction forms.
- [x] Normalize clamp/min/max/select forms.
- [x] Reject or label FP-inexact canonicalizations.
- [x] Canonicalize directly from parsed LLVM IR instead of source-shape rules.

## 6. Grammar Search

- [x] Define per-family grammar files.
- [x] Implement bounded equality saturation or a minimal e-graph backend.
- [x] Implement cost-guided extraction.
- [x] Replace top-level source-template selection with graph-family candidate selection for clamp/affine kernels.
- [x] Replace candidate emission itself with solver/e-graph-derived rewrites.

## 7. Verification

- [x] Connect graph rewrite provenance to proof artifacts in reports.
- [x] Keep Z3 schema proofs for scalar rewrites.
- [x] Add Alive2 slice verification for tractable target-only IR.
- [x] Mark proof status as `proved`, `bounded`, `tested`, `timeout`, or `unsupported`.
- [x] Add memory/pointer-aware proof obligations for busy heap interactions.

## 8. Evaluation

- [x] Add static candidate pruning using `llvm-mca` thresholds.
- [x] Add repeated corpus trials and median/trimmed-mean reporting.
- [x] Add perf-counter corpus mode.
- [x] Compare new graph-search path against current outer-shell baseline.

## 9. C Lifting

- [x] Define C AST/lowering model for selected graphs.
- [x] Generate readable C candidates for pointwise and guarded pointwise graph families.
- [x] Preserve preconditions and target-specific intrinsics in report metadata.
- [x] Lift from a normalized graph AST rather than reusing helper templates.
- [x] Add a zero-trust DeepSeek proposal/SMT feedback loop with deterministic fallback.
- [x] Reject LLM proposals that fail syntax, operation-policy, graph, constant, or SMT checks.

## 10. E2E Repeat

- [x] Rerun 25-kernel corpus with graph-superoptimization enabled.
- [x] Compare success rate and magnitude against `out-corpus-llvm-proof`.
- [x] Write final report explaining what “optimal within this grammar” means for each winner.
- [x] Rerun the v2 inner loop over all 25 kernels with perf counters and memory proofs.
