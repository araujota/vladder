---
name: vladder
description: Attribute, synthesize, formally verify, benchmark, and safely rewrite performance-critical C or C++ systems with vLadder. Use for semantic realization lifetime, caching, serialization, GPU residency, intermediate elimination, latency, throughput, cache, memory traffic, SIMD, loops, reductions, layouts, fusion, state, quantized kernels, or runtime plans where explicit invalidation, semantic equivalence, and physical evidence are required.
---

# vLadder

This skill targets vLadder `1.0.0rc4`, grammar `vladder-v1`, lifetime grammar `lifetime-v1`, and
automatic support matrix `bounded-regions-v1`. Use vLadder as a proof-gated workflow: semantic
identity and lifetime -> realization and placement -> compiled IR -> information-flow graph ->
bounded grammar search -> Z3/protocol/LLVM refinement -> physical measurement -> project-level
replacement. Treat the compiler as the instruction-lowering engine and vLadder as the system that
chooses which verified realization and implementation graph should exist.

## Non-Negotiable Rules

1. Profile before adding a grammar family or changing code. Optimize a measured load-bearing
   region, not a plausible-looking loop.
2. Freeze source revision, compiler, flags, hardware, workload, and semantic contract before
   comparing candidates.
3. Keep reference and candidate in the same executable benchmark harness.
4. Never equate differential testing with proof. Record Z3 scope and whether LLVM refinement used
   canonical IR identity or invoked Alive2.
5. Never promote `UNAVAILABLE`, `TIMEOUT`, `UNSUPPORTED`, tolerance-only, or unproved evidence
   under an exact contract.
6. Do not apply `optimized.patch` unless `promotion.promotable` is true.
7. After applying a patch, verify that the project function is byte/token-equivalent to the
   proved generated function and run the real project tests and end-to-end workload.
8. Report negative results. The baseline winning is a valid outcome.
9. Never infer a semantic invariant from observed non-mutation. Runtime traces quantify reuse and
   cost; the contract alone authorizes lifetime extension.

## Workflow

### 1. Establish Environment And Attribution

Run:

```bash
vladder doctor --strict
vladder grammar
vladder lower validate
vladder lower list
```

Read [benchmarking.md](references/benchmarking.md) before profiling. Capture `git status`, the
source revision, build command, input trace or corpus, CPU affinity, governor, frequency, thermal
state, and baseline latency/throughput. Use the application's profiler and counters to identify
the region's runtime share, bytes, misses, stalls, branches, and dependency behavior.

Do not continue if the proposed transformation family is unrelated to the measured bottleneck.

### 2. Write The Semantic Contract

Read [contracts.md](references/contracts.md). State ABI, shapes, bounds, aliasing, alignment,
integer overflow, floating point, NaN/infinity, side effects, lifetime, ordering, threading,
allocation, determinism, and accepted input distribution. Mark assumptions as either checked
dispatch guards or deployment preconditions.

For the canonical standalone workflow, extract or adapt one bounded region to:

```c
void transform(float *dst, const float *src, size_t n);
```

Preserve a traceable mapping to the production function. For multi-stream, stateful, operator,
pipeline, projection, or Q4_K work, use the corresponding vLadder subcommand and contract format;
do not force semantics into the canonical ABI.

For unattended bounded-region work, read [automatic-regions.md](references/automatic-regions.md)
and classify the source before manual adaptation:

```bash
vladder region inspect --source target.c --function transform --out-dir vladder-inspect
```

Continue with `vladder region optimize` only when the result is `supported`. When it is
`adapter_required`, implement the named semantic boundary first; do not claim automatic source
generation or proof for the unsupported production region.

### 3. Select Realization Lifetime And Placement

Before local IR search, ask whether expensive information is constructed too often, retained after
final use, repeatedly transferred, or materialized without an independent observer. For those
cases read [lifetime.md](references/lifetime.md), then run:

```bash
vladder lifetime analyze --manifest lifetime.yaml --trace lifetime.json --out-dir vladder-lifetime-analysis
vladder lifetime synthesize --manifest lifetime.yaml --trace lifetime.json --out-dir vladder-lifetime-out
```

The manifest must declare authority, partial-order scopes, invalidators and non-invalidators,
ownership, publication, retirement, placement, and fallback. Treat an emitted
`AGENT_REALIZATION.md` as an architectural implementation contract, not generated source. Keep the
baseline fallback and sampled shadow oracle until project-level acceptance.

### 4. Analyze Compiled Information Flow

```bash
vladder analyze target.c --function transform --out-dir vladder-analysis
vladder grammar --family loop-schedule
vladder lower show --family loop-schedule --rule unroll
```

Inspect `analysis/flow.json`, LLVM IR, semantic slice, pointer footprints, invariants, and grammar
status. Read [grammar.md](references/grammar.md), then create a contract-gated deterministic plan
with `vladder lower plan`. Plan coverage does not imply generic source emission; a `routed` source
request still requires its specialized backend, proof chain, and physical benchmark.

### 5. Search And Measure

Use strict mode for replacements:

```bash
vladder optimize target.c \
  --function transform \
  --graph-inner-loop \
  --alive2 \
  --verification-policy strict \
  --min-speedup-pct 2 \
  --reps 25 \
  --cpu 0 \
  --out-dir vladder-out
```

Add `--assume-no-alias` only when the production contract proves it. Use `--perf`, cold-cache
runs, larger process counts, and held-out inputs when the expected effect is small or memory
behavior matters. Do not rank instrumented builds.

### 6. Audit Proof And Result

Read [verification.md](references/verification.md). Inspect:

- `perf.json`: policy, assumptions, tool versions, winner, confidence, and promotion decision
- `proofs/*.smt2`: exact encoded Z3 obligations and bounds
- `alive2/*.txt`: canonical-identity or Alive2 refinement result and unsupported operations
- `benchmark.csv`: all passing, rejected, tied, and regressing candidates
- `optimized.patch`: present only for a promotable non-baseline winner

Reject a result when the optimized region is not load-bearing, the confidence interval includes
the minimum effect, the benchmark changes workload semantics, or the proof excludes production
behavior.

### 7. Rewrite Production Source

Apply the implementation at the code level in the owning module. Preserve local style, ABI,
guards, fallback behavior, error handling, and surrounding invariants. Avoid retaining a generated
harness or benchmark-only assumptions in production code.

Verify the exact proof chain after applying:

```bash
vladder verify-application \
  --report vladder-out/perf.json \
  --source path/to/production.c \
  --function transform \
  --compile-arg=-Ipath/to/include \
  --out vladder-out/applied-verification.json
```

Then run the project's compiler, sanitizers where appropriate, unit/integration tests, and the
same end-to-end workload used for attribution. Rebenchmark the full application; a regional win
that disappears end to end is not a successful replacement.

### 8. Report With Bounded Claims

Report baseline and winner, effect size and interval, workload, hardware, grammar version/hash,
proof class, assumptions, code change, regional runtime share, and end-to-end delta. Classify the
result as `bounded_optimal_local` only after exhaustive coverage with sound pruning; otherwise use
`best_verified_found`. Never claim global optimality.

## Advanced Modes

- Fused streaming operators: `vladder operator analyze|optimize`
- Stateful pipelines: `vladder pipeline optimize`
- Hierarchical pipeline research: `vladder pipeline analyze-v4|optimize-v4`
- Projection complexes: `vladder projection analyze|profile|synthesize`
- Attribution-gated kernels: `vladder sksf validate-attribution|synthesize`
- Production Q4_K research: `vladder q4k ...`
- Lifetime-aware realization: `vladder lifetime analyze|synthesize|evaluate-corpus`

These modes are contract-specific. Read their example manifests in the installed package before
use and preserve their stated proof classification. They are not implied to have generic source
emission merely because their grammar rules have deterministic plan lowerers.
