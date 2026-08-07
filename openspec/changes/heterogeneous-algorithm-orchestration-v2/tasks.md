# Tasks

## 1. Research And Requirements

- [x] 1.1 Audit existing GPU IR, protocol proofs, sparse dataflow, runners, and claim boundaries.
- [x] 1.2 Research GPU staging, queue synchronization, presentation modes/timing, and pacing.
- [x] 1.3 Define finite algorithm/policy families and external evidence boundaries.

## 2. Shared Plan IR

- [x] 2.1 Implement deterministic HeterogeneousPlanGraph and candidate provenance.
- [x] 2.2 Add bounded candidate enumeration and static cost/risk annotations.
- [x] 2.3 Add deterministic GraphML export with SCC and recursion-bound metadata.

## 3. Executable Grammars

- [x] 3.1 Add bounded GPU stable-compaction source lowering and compilation validation.
- [x] 3.2 Add queue-overlap plan synthesis composed with queue protocol proof.
- [x] 3.3 Add exact sparse-update policy plan/source lowering with capacity and commit semantics.
- [x] 3.4 Add presentation policy plan synthesis composed with lifecycle proof.

## 4. Verification And Physical Evidence

- [x] 4.1 Emit and discharge Z3 obligations for every family.
- [x] 4.2 Add one external runner contract and randomized physical ranking path.
- [x] 4.3 Fail closed on simulated evidence, missing output/state hashes, unsupported present modes,
  unresolved recursion, and undeclared external behavior.

## 5. Validation And Release

- [x] 5.1 Add valid, invalid, and counterexample fixtures plus CLI/end-to-end tests.
- [x] 5.2 Validate relevant NeuralFusion surfaces read-only and record adapters precisely.
- [x] 5.3 Update capability registry, README, bundled skill, and release evidence.
- [x] 5.4 Run strict OpenSpec, tests, package build/install, and strict doctor.
