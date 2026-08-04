# Release Verification Model

## Proof Chain

vLadder promotion is conjunctive under the strict policy:

1. Structural and memory legality pass under declared bounds and alias assumptions.
2. A registered Z3/schema proof establishes its exact bounded obligation.
3. Alive2 establishes reference-to-candidate refinement for tractable compiled LLVM IR.
4. Edge, randomized, overlap/in-place, and differential execution pass.
5. The candidate exceeds the predeclared physical performance threshold.
6. The applied production function matches the proved generated function.
7. Project tests and end-to-end measurements confirm integration value.

Alive2 proof IR is emitted at `-O1` with vectorization and unrolling disabled to keep loop
translation tractable, while candidate arithmetic flags are preserved. Performance IR and
assembly remain `-O3 -march=native`. This proves the source-level transformation before aggressive
target lowering; it does not prove target machine code identity.

## Boundaries

- Z3 models only the obligation written in each SMT artifact.
- Pointer proofs use declared object footprints and assumptions, not arbitrary C provenance.
- Alive2 operates on LLVM semantics and may reject unsupported IR.
- Differential tests are falsification evidence, not universal proof.
- `verify-application` closes generated-to-applied source identity but does not replace a project
  build or test suite.
- Floating-point reassociation, approximation, relaxed atomics, and tolerance contracts require
  separate non-E1 reporting.

Any unavailable, timed-out, unsupported, or failed required layer blocks strict promotion.

## Reproducibility Bundle

Every optimization output records source path and command, compiler and tool versions, CPU model
and relevant ISA flags, grammar version/hash, semantic shape, proof artifacts, generated source,
IR, assembly, static estimates, all candidate timings, confidence interval, winner, promotion
decision, and patch. Domain adapters add model, trace, weight-layout, state, or hardware manifest
hashes as applicable.
