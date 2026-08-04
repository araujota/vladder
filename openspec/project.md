# vLadder OpenSpec Context

## Purpose

vLadder is a proof-of-concept hardware-aware optimizer for standalone C99
array kernels. The current system already provides the outer loop:

- extract a target `transform(float *dst, const float *src, size_t n)`
- generate candidates
- compile with Clang 20
- emit LLVM IR, assembly, and `llvm-mca` data
- run schema proofs, optional Alive2, and differential tests
- benchmark on the target CPU
- rank and emit reports/patches

The next architectural objective is information-flow superoptimization:

> Find the lowest-cost semantically equivalent realization of a function within
> an explicit grammar of information-flow transformations, then lift the selected
> realization back to developer-readable C.

## Current Constraints

- C99 standalone functions.
- Single target machine.
- No threads, system calls, I/O, or dynamic allocation changes.
- Correctness requires proof or explicit proof-gap reporting plus differential
  tests.
- Performance claims must be backed by generated artifacts and benchmark data.

## Definition: Optimal Within A Grammar

For a function `f`, a grammar `G`, target hardware `H`, and budget `B`, a result
is optimal only relative to:

- the semantic domain modeled by the extractor,
- the equivalence rules in `G`,
- the proof policy used to admit candidates,
- the target cost model and empirical benchmark harness,
- the finite search budget `B`.

vLadder must not claim global optimality over all C programs, LLVM IR, or
machine code.

## V3 Direction

V3 adds fused streaming operators above the scalar graph. It supports C17 and a
restricted C++20 subset, multiple streams and outputs, bounded state,
reductions, materialization/fusion choices, layout alternatives, and objective
profiles for token generation and low-latency replay. A machine-readable
semantic contract and immutable hardware/workload identity are mandatory.

V3 requirements are split by workstream so each change has its own proposal,
design, tasks, spec deltas, implementation evidence, and strict validation:

- `operator-ir-v3`
- `operator-grammar-v3`
- `operator-verification-v3`
- `operator-measurement-v3`
- `operator-token-v3`
- `operator-hft-v3`
- `operator-e2e-v3`

## V4 Direction

V4 introduces a `PipelineGraph` above immutable OperatorGraph leaves and searches
inter-operator fusion, materialization, traversal, layout, state, reduction, and
scratch-lifetime choices. Its objective is a retained cost vector spanning compute,
critical path, synchronization, scratch, and register/L1/L2/LLC/DRAM movement.
Logical, modeled, and measured traffic are reported separately. The first research
milestone requires verified synthesized regions covering 25% of measured decode; the
commercial milestone requires a statistically established 5% model-level token gain.

V4 requirements are split into:

- `pipeline-ir-v4`
- `pipeline-grammar-v4`
- `pipeline-verification-v4`
- `pipeline-measurement-v4`
- `pipeline-llm-v4`
- `pipeline-e2e-v4`

## V5 Direction

V5 introduces `ProjectionComplexGraph` beneath PipelineGraph and above immutable
OperatorGraph children. It searches exact weight-block layouts, shared activation
preparation, traversal, accumulator, materialization, token/sequence reuse, and
guarded runtime dispatch. Candidates are ranked against a declared portfolio;
regional wins cannot establish V5 success without exact model verification and a
statistically supported portfolio-level tokens-per-second improvement.

V5 requirements are split into:

- `projection-ir-v5`
- `projection-grammar-v5`
- `projection-verification-v5`
- `projection-measurement-v5`
- `projection-llm-v5`
- `projection-e2e-v5`
