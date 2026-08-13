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
python3 -m pip install --pre 'vladder==1.0.0rc29'
vladder doctor --strict
```
Do not imply that installing this skill installs the CLI, LLVM, Alive2, Z3, or target-project
toolchains. The package installer provides the Python command surface; `vladder doctor --strict`
reports any remaining host dependencies before optimization begins.

This skill targets vLadder `1.0.0rc29`, grammar `vladder-v1`, executable deep grammar `deep-v2`,
lifetime grammar `lifetime-v1`, and automatic support matrices `bounded-regions-v1` and
`bounded-cpp-regions-v11`, plus `bounded-rust-regions-v2`, `bounded-zig-regions-v3`, and
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
Exact byte-popcount reductions and selected-build unroll/vector/interleave composition are also
source-executable through the lazy search route.
For selected C++, read `eligible` separately from `schedule_eligible`. The latter permits a real
compiler candidate in an unchanged owning wrapper but proves no callback, exception, allocation,
atomic, or external protocol. Automatic source search also exposes complete-module
`llvm-function-v1` candidates; require two-module Alive2 PASS before treating one as verified and
never infer a C++ source rewrite from an LLVM replacement artifact.

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
[learned-prior.md](references/learned-prior.md),
[lazy-executable-search.md](references/lazy-executable-search.md), and
[composition-native-search.md](references/composition-native-search.md), and
[canonical-state-search.md](references/canonical-state-search.md). It may set priority or
request an exact check, but never supplies legality, equivalence, runtime authority, or promotion.
Preserve fail-open OOD handling, exploration, exact canonicalization, and exhaustive fallback.
Audit every native corpus before fitting. Do not deploy the RC26 composition checkpoint: its 62.0%
useful recovery at 30% cost failed the scale gates. Its trace format and exact transposition remain
valid research and deterministic search infrastructure. RC27 replaced learned reduction with an
exact canonical DAG. RC28 makes it the production architecture with adaptive POR, checkpoint/resume,
resource controls, and telemetry. Read [production-canonical-search.md](references/production-canonical-search.md).
Use `exhaustive` normally, `exhaustive_canonical` as the no-POR oracle, `exhaustive_reduced` to force
qualified reduction, and `legacy_path_debug` only for compatibility qualification.
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
    every eligible pseudonymized training form at every opportunity without re-prompting; report any
    form lacking an export adapter. Review opt-in means request a review only when the persistent
    30-day cadence is due and obtain approval for the exact review before submission. Neither scope
    waives schema/privacy validation or permits source/raw-artifact upload.
## Workflow
### Canonical Agent Entry
Do not select a specialist command family from memory. Begin with the production region and let
the authoritative planner route it:

```bash
vladder consent show
vladder can-optimize SYMBOL --source SOURCE --project . --out-dir vladder-out
vladder optimize SOURCE --function SYMBOL --project . --out-dir vladder-out
```

Add `--compile-commands build/compile_commands.json` for C++ when it is not auto-discovered. Read
`disposition.json`, not the full artifact tree. Report its five facts, `terminal_status`,
`economic_decision`, and argv-form `next_action`. Use `vladder resume --out-dir vladder-out` after
supplying a named scaffold. Inspect specialist references only when the generated plan routes to
them. Read [agent-workflow.md](references/agent-workflow.md) and
[release-evidence.md](references/release-evidence.md) only for the current blocker.

Before the first canonical workflow run, show the user the complete machine-readable notice for
each `unknown` contribution scope and ask for an explicit opt-in or opt-out. This is a required
informed clarification, not a suggestion; optimization remains available regardless of either
answer.

Terminal promotion-summary creation is the ubiquitous canonical training trigger. When durable
`canonical_training_data` consent is `opt_in`, `workflow run` and `workflow summarize` must
automatically de-identify, schema-validate, and submit the complete disposition record without
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

For real roots, run `vladder source-search run --manifest executable-search.yaml --out-dir
source-search-out --search-mode exhaustive`. Read `executable-closure.json`,
`production-canonical-search.json`, then `canonical-state-dag.json`. For `family: auto`, every
independently classified grammar family is a real first-layer
lazy decision; do not reconstruct family outcomes from reporting-only wrappers. Deterministic
impossibility and exact semantic memoization remain hard-reduction authorities. The learned policy
orders the complete sibling frontier; it does not delete branches. `fast` and `guided` stop on a
declared work budget, while `exhaustive` eventually visits every unique state not removed by
deterministic or formally verified mechanisms. Compare against `exhaustive_canonical` before enabling
a new exact reduction. Read
[lazy-executable-search.md](references/lazy-executable-search.md) for manifests, closure classes,
claim boundaries, and label authority.

Read `prior-summary.json`. A valid synthetic pilot and a trained model do not imply production
eligibility or that any live candidate was pruned.

Require `vladder-model-training-bundle-v3` for auxiliary root/branch supervision and use `training
from-search-trace`; `from-prior` is a partial one-level import. For future composition-policy
updates, require the enumerator-native `composition-native-search-trace.json`, an embedded
`vladder-search-policy-training-contract-v1`, and
`future_policy_training_eligible=true`. Only exhaustive or soundly closed dead subtrees may train
historical prune labels.
Train and evaluate only branches marked `decision_surface=learned_eligible`; deterministic,
canonicalized, and synthetic-wrapper records are audit evidence outside the learned policy surface.
Exhaust every tractable bounded root and a stratified set of deeper roots. A budget-truncated root
may contribute coverage and OOD examples, but every open frontier and affected ancestor remains
`KEEP_UNCERTAIN`; absence of an enumerated Cartesian descendant is never a negative label.
Read [learned-prior.md](references/learned-prior.md) for descendant-label and leakage rules.
Never tensorize a completed native trace directly. Its validated inference view contains only the
current parent state, ordered history, sibling actions, interaction graph, and action deltas; future
states, transpositions, selected actions, outcomes, labels, and measured costs are supervision.
The contextual reference model is `scripts/contextual_search_policy.py` and requires `vladder[ml]`.
Its acceptance gate is useful-terminal recovery under an online work budget, not branch accuracy.
The RC24 `scripts/search_pruner.py` classifier is retained for encoder pretraining, OOD, retrieval,
and historical comparison only; do not optimize or enable its hard-pruning policy.
Use `scripts/build_cpp_search_manifest.py` for deterministic family-stratified C++ campaigns. Pair
every repeated trainer `--progress` with the corresponding `--manifest`; never merge incomplete
campaigns or repeated roots by hand.
Use `scripts/discover_cpp_object_roots.py` for a non-overlapping follow-up drawn from strong symbols
in the exact built objects. For large shadow campaigns, `artifact_retention: decisive` keeps
compressed, resumable search evidence and compact summaries after v3 emission while removing
reproducible terminal products. Retain at least one `full_artifact_identifier` per project for
forensic review. Ordinary optimization and release evidence use full retention.

Candidate-dense roots may emit multiple v3 bundles. Treat `bundles` as the authoritative packet
set and ingest every `full_trace` or `complete_subtree` packet. A `complete_subtree` preserves its
external parent identity and negative-label authority; a `partial_snapshot` never creates a prune
label merely because descendants are absent. Do not raise document-size limits or truncate a tree
to make one artifact fit.

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
benchmarks, patches, prompts, or raw artifacts. Optional agent reviews and graph-ready v3 search training
bundles use `vladder review|training template|from-search-trace|validate|submit`. Submission uses the packaged HTTPS
release endpoint and requires durable scope opt-in, schema validation, record consent, and
`--confirm-upload`; no shared token is required. Training opt-in authorizes those per-opportunity
mechanical gates without repeated questions. Reviews still require exact-record approval.
`--validate-only` is also a network action and
requires the same durable opt-in, though it tests remote acceptance without storage. Model-training
v3 bundles are strict pseudonymized schemas, not upload paths for local stores or arbitrary artifacts.
They include topology and search lineage; distinctive graphs or strategies may fingerprint algorithms.
Re-request stale consent under the v3 notice. Read
[release-evidence.md](references/release-evidence.md) and `docs/privacy.md`.
On first opted-in use, the client obtains an owner-protected, installation-scoped append capability;
it does not receive a Convex deployment credential. Run `vladder contribution doctor` when release
service access must be verified. The probe stores no contribution and must show both intended
append scopes, cross-scope denial, moderation denial, and absence of a private training read path.

When changing vLadder itself, first run `vladder release smoke-canonical-search`, then use
`vladder release check`. Require `release_candidate --execute` during development and
`formal_release --execute --online` before tagging. Treat `not_run`, `setup_required`, and
`unavailable` as blockers for the target that names them; a subset is not release readiness.

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

Use `--symbol` to select an overload or concrete template specialization. If an authoritative
inventory already records the exact definition line, use `--source-line`; selection must resolve
to one Clang definition. Read
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

For Rust, Zig, or Julia, start from native project source and read the corresponding
[Rust](references/rust-regions.md), [Zig](references/zig-regions.md), or
[Julia](references/julia-regions.md) route. All three use the same `SemanticFlowGraph` vocabulary;
borrow/panic/`Drop`, safety/error/defer, GC/world-age/dynamic-dispatch, and FFI facts remain typed
language-bound obligations rather than separate information-flow ontologies.

Select concrete monomorphizations or method signatures, preserve native safety and exception
semantics, and require native regeneration plus compiler-IR recapture. `status: supported` with
`candidate_generation.actual: false` is semantic capture, not executable synthesis. Native LLVM is
compiler provenance; only the declared canonical lowerer and its bounded Z3/Alive2 envelope support
a rewrite claim. Allocation, custom destruction, async/tasks, atomics, unsafe/external effects, and
unresolved runtime dispatch remain named adapter boundaries.

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
