---
name: vladder
description: Attribute, synthesize, formally verify, benchmark, and safely rewrite performance-critical C, C++, Rust, Zig, or Julia systems with vLadder. Use for semantic realization lifetime, caching, serialization, GPU residency, intermediate elimination, latency, throughput, cache, memory traffic, SIMD, loops, reductions, layouts, fusion, state, quantized kernels, or runtime plans where explicit invalidation, semantic equivalence, and physical evidence are required.
---

# vLadder

## Required Package

This skill is the agent workflow layer; it does not bundle the vLadder CLI. Before running a
workflow, verify that the attendant [`vladder` package](https://pypi.org/project/vladder/) is
installed and matches the release targeted below:

```bash
vladder --version
```

If the command is unavailable or reports another version, tell the user that the skill requires
the PyPI package and obtain permission before installing or upgrading it:

```bash
python3 -m pip install --pre 'vladder==1.0.0rc19'
vladder doctor --strict
```

Do not imply that installing this skill installs the CLI, LLVM, Alive2, Z3, or target-project
toolchains. The package installer provides the Python command surface; `vladder doctor --strict`
reports any remaining host dependencies before optimization begins.

This skill targets vLadder `1.0.0rc19`, grammar `vladder-v1`, executable deep grammar `deep-v2`,
lifetime grammar `lifetime-v1`, and automatic support matrices `bounded-regions-v1` and
`bounded-cpp-regions-v8`, plus `bounded-rust-regions-v2`, `bounded-zig-regions-v3`, and
`bounded-julia-regions-v3` adapters over `canonical-bounded-regions-v1`, and
`heterogeneous-execution-v1`. Use vLadder as a proof-gated workflow: semantic
identity and lifetime -> realization and placement -> compiled IR -> information-flow graph ->
bounded grammar search -> Z3/protocol/LLVM refinement -> physical measurement -> project-level
replacement. Treat the compiler as the instruction-lowering engine and vLadder as the system that
chooses which verified realization and implementation graph should exist.

The executable `bounded-dataflow-v1` grammar adds stable variable-output compaction, exact
fixed-width codecs, transactional state deltas, AoS projected multi-reductions, and deterministic
4x4 packed blocks. Read [bounded-dataflow.md](references/bounded-dataflow.md) when the observable
includes indices, values, exact extent, packed bytes, or next state rather than only a scalar.

Read [systems-code-design.md](references/systems-code-design.md) before restructuring production
code; preserve idiomatic ownership/protocol shells and expose bounded semantics and observables.

All supported frontends converge on `SemanticFlowGraph v2`. Read typed `obligations`, `effects`,
`protocols`, and `claims` before interpreting a graph. An obligation is actionable through its ID,
scope, proof method, and language binding; do not recover semantics by parsing its human-readable
statement. A successful graph build with an excluded or unverified claim is not proof of it.
When a hot path crosses functions, read [system-closure.md](references/system-closure.md). Compose
native inspection reports with `vladder system closure` before generating candidates. Protocol
envelopes constrain legality and add zero candidate dimensions; arbitrary callbacks and undeclared
third-party APIs remain local boundaries while closed components continue.
For cross-TU C++ helpers, read [cross-tu-closure.md](references/cross-tu-closure.md) and run
`vladder build closure`; it adds bounded build summaries, ownership, and Z3, not search dimensions.
Read [canonical-regions.md](references/canonical-regions.md) for the shared Rust/Zig/Julia
seven-family extraction model and the semantic-capture versus executable-lowering decision.
For C/C++, inspect `region-closure.json` before requesting an adapter. It distinguishes a missing
grammar from an unmodeled ABI and records aggregate projections, tagged exits, local helper
relations, and no-growth ownership projections. Treat `closed_at_compiled_abi` as representation
closure, not proof of a future candidate or an owning wrapper.

Read [incident-closure.md](references/incident-closure.md) for recursive helpers, RAII cleanup,
member/global state, atomic publication, structured owning dataflow, image sampling, or cooperative
matrices. Do not promote typed SPIR-V capture with unresolved numeric, validity, descriptor, or
capability obligations. Do not describe a recognized structured archetype as generated code unless
its route is `executable_local`.

The optional learned search prior is subordinate to this workflow. Read
[learned-prior.md](references/learned-prior.md) before using `vladder prior`. It ranks structured,
already enumerated grammar actions; it never supplies legality, equivalence, authoritative runtime,
or promotion evidence. Preserve the baseline, exploration reserve, abstention fallback, and every
ordinary proof and physical gate.

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
10. A baseline win is bounded by grammar coverage. Before saying no faster equivalent was found,
    audit known expert forms through representation, derivation, lowering, proof, and performance.
    A pre-performance failure is a grammar/tooling gap, not a negative hardware result.
11. Optional contribution consent is never inferred. Before offering or performing canonical
    training-data contribution or an agent-experience review, run `vladder consent show`. For each
    `unknown` scope, explicitly ask the user to opt in or opt out and persist the exact answer with
    `vladder consent set ... --confirmed-user-choice`. Honor the two scopes independently.
12. A saved `opt_out` means do not upload and do not ask again across turns, sessions, or package
    updates unless the user explicitly requests reconsideration. Training opt-in means contribute
    every eligible anonymized training form at every opportunity without re-prompting; report any
    form lacking an export adapter. Review opt-in means request a review only when the persistent
    30-day cadence is due and obtain approval for the exact review before submission. Neither scope
    waives schema/privacy validation or permits source/raw-artifact upload.

## Workflow

### Canonical Agent Entry

Read [agent-workflow.md](references/agent-workflow.md) and
[release-evidence.md](references/release-evidence.md), then begin with one manifest rather than
assembling subcommands from memory:

```bash
vladder consent show
vladder workflow init --kind cpp --out vladder-workflow.yaml
vladder workflow run --manifest vladder-workflow.yaml --out-dir vladder-workflow-out
```

Before the first canonical workflow run, show the user the complete machine-readable notice for
each `unknown` contribution scope and ask for an explicit opt-in or opt-out. This is a required
informed clarification, not a suggestion; optimization remains available regardless of either
answer.

Terminal promotion-summary creation is the ubiquitous canonical training trigger. When durable
`canonical_training_data` consent is `opt_in`, `workflow run` and `workflow summarize` must
automatically anonymize, schema-validate, and submit the complete disposition record without
asking again. Read `optional_contributions.canonical_training_data` for completion or a retryable
transport failure. The validated record is durably queued before transport; a later opted-in
terminal workflow replays pending records. Unknown or opt-out consent must perform no network
request and must not flush the outbox.

Read `promotion-summary.json` first. Answer, in order:

1. What region kind and semantic boundary were selected?
2. Is semantic coverage meaningful or merely syntactic/selection-level?
3. Was a candidate generated and proved?
4. Was it measured with complete observables and paired physical evidence?
5. Was it integrated and retained, or is this only a new hypothesis/revalidation?

Follow `next_action`; inspect only the five decisive artifacts before expanding into full lineage.
Do not confuse `workflow_completed` with any later evidence state.

For search-prior dataset and shadow-evaluation work, use its separate one-manifest route:

```bash
vladder prior init --out prior.yaml
vladder prior run --manifest prior.yaml --out-dir prior-out
```

Read `prior-summary.json`. A valid synthetic pilot and a trained model do not imply production
eligibility or that any live candidate was pruned.

The operational state order is strict:

1. `meaningful_semantic_coverage`
2. `candidate_generated`
3. `candidate_proved`
4. `physically_benchmarked`
5. `application_integrated` and `production_promoted`

Stop at the first false state and report its named adapter or evidence requirement. Successful
command execution is not a substitute for any state.

Validate stable public artifacts before interpreting them:

```bash
vladder schema list
vladder schema validate --kind promotion-summary --artifact promotion-summary.json
```

vLadder is local-only by default. Read [consent.md](references/consent.md). Do not upload
source, compilation databases, IR, proofs, traces,
benchmarks, patches, prompts, or raw artifacts. Optional agent reviews and derived-feature training
bundles use `vladder review|training template|validate|submit`. Submission uses the packaged HTTPS
release endpoint and requires durable scope opt-in, schema validation, record consent, and
`--confirm-upload`; no shared token is required. Training opt-in authorizes those per-opportunity
mechanical gates without repeated questions. Reviews still require exact-record approval.
`--validate-only` is also a network action and
requires the same durable opt-in, though it tests remote acceptance without storage. Training
bundles are a strict source-free schema, not an upload path for local prior stores or arbitrary
artifacts. Read [release-evidence.md](references/release-evidence.md) and `docs/privacy.md`.
On first opted-in use, the client obtains an owner-protected, installation-scoped append capability;
it does not receive a Convex deployment credential. Run `vladder contribution doctor` when release
service access must be verified. The probe stores no contribution and must show both intended
append scopes, cross-scope denial, moderation denial, and absence of a private training read path.

When changing vLadder itself, use `vladder release check`. Require `release_candidate` with
`--execute` during development and `formal_release` with both `--execute --online` before tagging.
Treat `not_run`, `setup_required`, and `unavailable` as blockers for the target that names them;
successful execution of a subset is not release readiness.

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

For C++, do not create a hand-written C capsule before trying the semantic frontend. Export the
production compilation database and run:

```bash
vladder cpp inspect --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-inspect
vladder cpp isolate --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-isolation
vladder cpp synthesize --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-synthesis
vladder cpp optimize --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-out
vladder cpp audit --manifest cpp-regions.yaml --materialize-isolation --out-dir vladder-cpp-audit
```

Use `--symbol` to select an overload or concrete template specialization. Read
`closure.disposition` and the independent semantic-capture, isolation, candidate-generation,
local-proof, benchmark, source-rewrite, and protocol-equivalence capabilities. The v5 frontend
can emit whole local-function proof units and noinline lambda capsules for eligible nested loops,
then produce guarded schedule candidates without editing the repository. It must not rank or
apply a noncanonical C++ candidate without an application workload adapter.

Treat `protocol_scopes` as claim boundaries, not global blockers. Generic ingestion cannot prove
RAII/destructor, allocator ownership, exceptions, concurrency/memory ordering, Vulkan/OpenUSD,
callbacks, syscalls, or other external protocols whose state is absent from local IR. Continue
with independently closed local regions, attribution, lifetime/placement analysis, or explicit
domain contracts. Never call identity-capsule proof whole-wrapper equivalence, and never call a
source scheduling contract an Alive2 proof of the physical candidate. Read
[cpp-regions.md](references/cpp-regions.md).

When inspection identifies bounded variable output or a state transition, do not collapse it to a
count-only proof unit. Preserve masks, stable order, extent, capacity failure, and state
publication in `bounded-dataflow-v1`:

```bash
vladder dataflow coverage
vladder dataflow graph --contract contract.json --target mask-prefix-stable --out graph.json
vladder dataflow verify --contract contract.json --target guarded-avx2-compaction --out-dir proof
```

Add `--language c|cpp|zig|julia` to emit the shared derivation natively. Read
`candidate.lowering_class`: `semantic_scalar_fallback` establishes native semantic execution but
does not establish a distinct SIMD realization.

No-growth vector closure requires a checked available-capacity guard before any write, trivial
element lifetime, no throwing local operation, and declared aliases. `reserve()` is not enough.
An owning wrapper that remains outside this envelope is an explicit adapter, not a blocker for the
borrowed local kernel and not part of its Z3/Alive2 claim.

For Rust, preserve native ownership and panic semantics and start from Cargo rather than a C FFI
capsule. Read [rust-regions.md](references/rust-regions.md), then run:

```bash
vladder rust inspect --manifest-path Cargo.toml --source src/lib.rs --function module::count --out-dir vladder-rust-inspect
vladder rust synthesize --manifest-path Cargo.toml --source src/lib.rs --function module::count --out-dir vladder-rust-synthesis
vladder rust optimize --manifest-path Cargo.toml --source src/lib.rs --function module::count --out-dir vladder-rust-out
```

Rust uses the same `SemanticFlowGraph` vocabulary as C/C++. MIR, borrow, panic, `Drop`, unsafe, and
monomorphization facts are language-bound proof obligations and provenance, not a parallel
information-flow ontology. R1 closes safe, monomorphic, allocation-free scalar/array/borrowed-slice
regions with a registered common operation. Unsafe code, owning allocation, custom destruction,
async, atomics, FFI, and external effects remain explicit adapter boundaries. Require native Rust
regeneration, MIR recapture, parametric schedule/Z3 proof, bounded LLVM refinement, differential
execution, and physical ranking before promotion.

R2 compiler-corroborates exact reductions, pointwise maps, guarded maps, stencils, scans,
recurrences, and constant-stride indirect reads. A supported graph whose
`candidate_generation.actual` is false is meaningful semantic capture, not executable synthesis;
`rust synthesize` returns `lowerer_required` for that case.

For Zig, read [zig-regions.md](references/zig-regions.md), preserve the compiler safety mode, and
start from native source:

```bash
vladder zig inspect --source src/root.zig --function countEqual --build-root . --out-dir vladder-zig-inspect
vladder zig synthesize --source src/root.zig --function countEqual --build-root . --out-dir vladder-zig-synthesis
vladder zig optimize --source src/root.zig --function countEqual --build-root . --out-dir vladder-zig-out
```

Use `--specialization u8` for a compatible `comptime T: type` byte reduction. Capture keeps the
target at its original module path; a detached source copy is invalid compiler provenance.
Z3 recognizes the same seven canonical bounded families as Rust and C. Check
`candidate_generation.actual`; non-reduction families currently require a native family lowerer.

For Julia, read [julia-regions.md](references/julia-regions.md). Always provide one exact module,
method, and tuple signature; a generic function name is not a proof boundary:

```bash
vladder julia inspect --project . --source src/Package.jl --module Package --function count_equal --signature 'Vector{UInt8},UInt8' --out-dir vladder-julia-inspect
vladder julia synthesize --project . --source src/Package.jl --module Package --function count_equal --signature 'Vector{UInt8},UInt8' --out-dir vladder-julia-synthesis
vladder julia optimize --project . --source src/Package.jl --module Package --function count_equal --signature 'Vector{UInt8},UInt8' --out-dir vladder-julia-out
```

Zig and Julia use the shared graph and source-derived exact-reduction schedule proof. Julia loads
the declared package/module and does not invoke arbitrary methods during reflection. Methods beyond
the executable grammar may still be `local_graph_only` with typed/LLVM/native capture. Native LLVM
is compiler provenance; the strict Alive2 artifact validates the canonical schedule lowerer. Do
not claim direct whole-frontend refinement. Zig allocator/error/defer/atomic/FFI protocols and
Julia other methods/worlds, GC allocation, dynamic dispatch, tasks, globals, `ccall`, and external
effects remain named adapters.
J3 recognizes the same seven canonical families for concrete, zero-allocation byte or `Float32`
vector specializations. `status: supported` and `candidate_generation.actual: false` means the
typed SSA/LLVM-backed graph is closed but no candidate was generated.

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

For exact byte predicates/reductions or a grammar-depth investigation, read
[deep-grammar.md](references/deep-grammar.md) and run the closed shared-grammar path first:

```bash
vladder deep coverage
vladder deep audit --manifest examples/deep_grammar/expert-audit.yaml --out-dir vladder-deep-audit
vladder deep rank --language cpp --predicate equal-u8 --processes 10 --repetitions 3 --cpu 0 --out-dir vladder-deep-ranking
```

Inspect the earliest failed audit stage. Use `bounded_optimal_local` only when finite search is
saturated, every hot identity is non-empty and resolved, and all unique terminal realizations are
lowered, proved, and measured.
Every `deep-v2` terminal has native C, C++20, Rust, Zig, and Julia emission. Select the production
language; do not translate through C merely to access a deeper grammar. Language runtime scopes
remain explicit typed obligations rather than claims of arbitrary-language equivalence.

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

For C++ inspect `cpp-support.json`, `typed-abi.json`, `compiled-effects.json`, `subregions.json`,
`cpp-information-flow.json`, `proof-envelope.json`, and `closure`. Materialized closure runs also
emit `cpp-closure.json`, identity proof units, candidate source hashes, Z3 schedule obligations,
and explicit benchmark requirements. Canonical runs also emit
`adapter-contract.json`, `adapter-extents.smt2`, `provenance.json`, and
`cpp-optimization.json`. Never use `supported` alone: inspect every capability's `ready` and
`actual` fields. A proved local unit is not a proved owning wrapper. `kernel_isolated_adapter_proved` is not a proved transformed candidate.
Require `kernel_proved_adapter_bounded` plus a passing regenerated source before considering the
local rewrite.

When an application boundary remains, generate its explicit starting point rather than inventing
a harness from prose:

```bash
vladder cpp adapter --report vladder-cpp-inspect/cpp-support.json --out-dir vladder-cpp-adapter
```

Complete every manifest TODO and observable hook. For retained class state, use a bounded
`versioned_cache` or `transactional_publication` projection with `vladder protocol verify` only
when that protocol matches exactly. Other ownership, callback, coroutine, driver, syscall, and
external-library protocols remain explicitly scoped adapters.

Reject a result when the optimized region is not load-bearing, the confidence interval includes
the minimum effect, the benchmark changes workload semantics, or the proof excludes production
behavior.

For application regions, use `vladder benchmark paired` and require exact observable hashes.
Before reporting composed effects, use `vladder benchmark compose`; parent/child or otherwise
overlapping regions cannot be compounded without an explicit interaction measurement.

For public resources, run `vladder protocol template --kind queue` and `protocol verify`; never add
external implementation internals to local candidate search.

For GPU compute, algorithms, and device protocols, follow
[gpu-workflow.md](references/gpu-workflow.md). Use `cuda-synthesize|cuda-optimize` for bounded CUDA,
`capture|synthesize|verify|rank` for general kernel evidence, and `plan-synthesize|plan-rank` for
attributed compaction, queue, sparse-policy, or presentation grammars. Use
[heterogeneous-plan-triage.md](prompts/heterogeneous-plan-triage.md) first. Generated source and
runtime plans are distinct; GraphML and simulation never prove or promote. External DMA, driver,
network, and visible presentation behavior require explicit protocols and physical runners.

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

- Streaming operators and stateful pipelines: `vladder operator analyze|optimize`, `vladder pipeline optimize`
- Hierarchical pipelines and projections: `vladder pipeline analyze-v4|optimize-v4`, `vladder projection ...`
- Attribution-gated and Q4_K kernels: `vladder sksf validate-attribution|synthesize`, `vladder q4k ...`
- GPU and lifetime workflows: `vladder gpu support|capture|synthesize|verify|rank`, `vladder lifetime ...`

These modes are contract-specific. Read their example manifests in the installed package before
use and preserve their stated proof classification. They are not implied to have generic source
emission merely because their grammar rules have deterministic plan lowerers.
