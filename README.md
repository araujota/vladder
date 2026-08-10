# vLadder

vLadder, short for **Velocity Ladder**, is a proof-gated, hardware-grounded information-flow
superoptimization library for performance-sensitive C, C++, Rust, Zig, and Julia development.

Its workflow is deliberately hierarchical:

```text
repository, runtime traces, and semantic contract
                       |
 semantic identity, validity, and lifetime attribution
                       |
  realization lifetime and physical placement
                       |
 expression / loop / operator information-flow graphs
                       |
        grammar-bounded synthesis
                       |
 Z3 + protocol checks + LLVM refinement + differential tests
                       |
         physical hardware benchmarking
                       |
       verified repository realization
```

LLVM decides how a supplied graph becomes machine instructions. vLadder searches which
semantically equivalent implementation graph should be supplied, then works back up to a
developer-readable source replacement. Architectural lifetime changes emit a realization
contract for an attending code agent; they do not claim generic repository source generation.

## One Agent Entry Point

Start with the production source region. vLadder now performs a cheap feasibility pass before any
candidate compilation and routes the complete reachable workflow internally:

```bash
vladder can-optimize transform \
  --source src/transform.cpp \
  --project . \
  --compile-commands build/compile_commands.json \
  --out-dir vladder-transform

vladder optimize src/transform.cpp \
  --function transform \
  --project . \
  --compile-commands build/compile_commands.json \
  --out-dir vladder-transform
```

The preflight produces one `optimization-plan.json` containing language and region routing,
code-derived contract candidates, unresolved assumptions with a mechanical patch, an upfront
external-authority map, project test/benchmark candidates, grammar coverage, proof-unit
representativeness, dependencies, expected runtime and artifact volume, the first unreachable
evidence state, and an economic `CONTINUE`, `STOP`, or `ESCALATE` recommendation. Discovered tests
and contracts remain candidates until explicitly bound; planning has no proof or promotion
authority.

The terminal `disposition.json` defaults to the five facts an agent needs: semantic coverage,
candidate generation, proof badge, physical measurement, and application integration. Its terminal
status is one of `NO_COVERAGE`, `NO_CANDIDATE`, `NO_PROOF`, `NO_BENCHMARK`,
`INTEGRATION_REQUIRED`, `VERIFIED_REJECTION`, or `PROMOTABLE`, with a directly executable next
command. Full artifact lineage remains available on demand. `vladder resume --out-dir ...` reuses
matching content-addressed stages and restarts at the first invalid input; `vladder optimize
--portfolio --project ...` inventories, prioritizes, and deduplicates repository regions.

Existing specialist commands remain stable and are the delegated expert surface. The historical
`vladder optimize source.c --function transform` arguments still invoke the same bounded-C search,
proof, benchmark, and patch engine, with the new disposition layered on top.

## Release Status

The package version is `1.0.0rc23`, the C++ closure matrix is
`bounded-cpp-regions-v8`; it retains the
`bounded-regions-v1` C frontend and includes `bounded-rust-regions-v2`,
`bounded-zig-regions-v3`, and `bounded-julia-regions-v3` adapters. These three frontends share
`canonical-bounded-regions-v1`, which compiler-corroborates exact predicate reductions,
pointwise maps, guarded maps, stencils, scans, recurrences, and constant-stride indirect reads.
The C frontend fully
automates extraction, LLVM-derived classification, transformation, C source regeneration,
formal refinement, differential execution, hardware benchmarking, and proof-gated patch
promotion for canonical functions with this ABI:

```c
void transform(float *dst, const float *src, size_t n);
```

Automatically admitted C classes are pointwise maps, guarded pointwise maps, stencils, ordered
scans, ordered recurrences, and constant-stride modulo-n indirect reads.

The C++ frontend consumes the selected translation unit's exact `compile_commands.json` entry,
uses Clang's semantic AST to select a concrete mangled definition, and combines source authority
with recursively summarized production LLVM effects. It models scalar, pointer, byte or typed
span, borrowed vector, structured-reference, and compiler-lowered aggregate-result boundaries.
It also inventories loops, helper closures, object-state projections, ownership, exceptions,
synchronization, and external calls, then emits an authoritative `SemanticFlowGraph v2` with
typed obligations, effects, protocol transitions, and claim boundaries. The C frontend attaches
the same authoritative v2 graph to every admitted legacy `FlowGraph`; legacy classification
fields remain compatibility views.

The v8 C++ `RegionClosureGraph` additionally represents noncanonical first-order C ABIs, ordered
aggregate-result projections, ordinary multi-exit CFGs, definition-visible helper summaries, and
guarded no-growth trivial container writes. These close local representation boundaries; they do
not make reallocation, nontrivial destruction, exceptions, indirect calls, or external ownership
generic. A modeled C ABI with no executable family is reported as `grammar-adapter`, not
misreported as an ABI failure.

Results expose independent capture, isolation, candidate-generation, local-proof, benchmark,
source-rewrite, and protocol-equivalence capabilities. v8 can materialize whole local functions
and eligible nested loops as proof units, and can emit bounded source schedule candidates for the
latter. It still requires a workload adapter before ranking a noncanonical C++ candidate. Alive2
can prove local LLVM rewrites; it does not prove RAII, allocation, object invariants, exception,
concurrency, Vulkan/OpenUSD, callback, or other owning protocols. These categorical protocol
limits do not block independently closed subregions or the attribution, lifetime, placement, and
contract-bounded parts of vLadder.

rc17 closes the grammar-limitation incident classes that can be represented from available source,
IR, and public contracts without claiming arbitrary C++ or proprietary runtime equivalence:

- typed SPIR-V capture for logical operations, unsigned division/remainder, dot and matrix
  operations, image accesses, and cooperative matrices, with explicit validity and numeric
  obligations;
- SCC-safe C++ effect composition, parametric library/runtime summaries, exceptional cleanup
  traces, named member projections, and atomic/volatile ordering descriptors;
- a domain-neutral finite-resource protocol DSL for publication, queues, partial socket outcomes,
  and device ownership while preserving opaque external calls;
- structured dataflow recognition for sparse updates, parse/materialize flows, retained caches,
  stable partition/scatter, state coalescing, and realization lifetime, with an explicit route to
  local lowering, protocol proof, or agent realization;
- bounded content-addressed artifact names with full identities retained in manifests.

Capture is not proof. A parsed shader may still require numeric, divisor-validity, descriptor,
output-oracle, and device-timestamp evidence. A recognized owning C++ archetype remains
adapter-required unless a bounded executable region or finite protocol closes its observables.

rc18 extends semantic closure across translation units. `vladder build index` binds production
compilation commands, sources, object definitions, and object references. `vladder build closure`
materializes persistent LLVM summaries only for a bounded caller/callee slice, upgrades uniquely
resolved project helpers from opaque calls to definition edges, derives an ownership closure graph,
and emits Z3 obligations for definition identity, provenance, effect composition, ownership
disposition, and zero added search dimensions. Multiple weak/COMDAT bodies, arbitrary callbacks,
and external authorities remain explicit boundaries. See
[Cross-TU Semantic Closure](docs/cross-tu-semantic-closure.md).

rc6 adds a manifest-driven agent workflow and closes several application-promotion gaps:

- one `promotion-summary.json` distinguishes inspection, meaningful semantic coverage, candidate
  generation, proof, physical benchmarking, integration, promotion, and retained revalidation;
- C++ closure reports generate benchmark, observable, state-projection, and agent-task adapters
  with unresolved semantics as explicit blockers;
- versioned-cache and transactional-publication state projections receive bounded Z3 proofs;
- paired same-executable measurements use randomized process order and bootstrap confidence
  intervals, while overlapping regional speedups are rejected unless an interaction run exists;
- weak lifetime traces return `insufficient_attribution` and generate no candidates;
- GLSL/SPIR-V compute modules can be compiled, validated, transformed, and connected to exact
  output and device-timestamp runners. SPIR-V structural validation is not equivalence, and CUDA
  remains an external toolchain/runner boundary when unavailable.

rc14 extends that evidence chain into heterogeneous execution without creating a separate GPU
semantic ontology. `Q4KPhysicalExecutionGraph`-style machine resources, SPIR-V/PTX operations,
queue synchronization, DMA topology, and presentation ownership lower into shared
`SemanticFlowGraph v2` nodes, effects, obligations, and protocol transitions. The
`heterogeneous-execution-v1` workflow provides:

- SPIR-V, PTX, and CUDA-to-PTX capture with operation, resource, provenance, and claim-boundary
  inventories;
- native CUDA device probing and a bounded pointwise source lowerer that searches thread geometry
  and contiguous per-thread schedules, proves index coverage/injectivity, checks exact output
  hashes, and emits source plus launch plan only after clean physical promotion;
- architecture manifests and static occupancy, register, shared-memory, cache-transaction, and
  coalescing estimates for pruning, calibrated with CUDA-driver JIT resource inspection and a
  measured copy-flow bandwidth bound;
- bounded launch-plan proof and GLSL local-workgroup source regeneration where the source and
  recognized lane-independent semantics permit it;
- queue/semaphore/barrier, GPU/NIC DMA/topology, and acquire/present/scanout protocol verification;
- live CUDA/Vulkan UUID joining, Vulkan queue-family capability capture, PCIe/IOMMU/NIC/RDMA route
  discovery, and DRM connector binding with fail-closed protocol templates;
- built-in Nsight Compute attribution plus CUPTI, ROCprofiler, and runner-counter normalization with
  randomized paired physical ranking.

Static models never promote. Exact output hashes, matching device identity, clean device
timestamps, protocol closure, and confidence intervals are required for a physical win.
Profiler-replayed, serialized, or simulated measurements remain attribution-only.

The `heterogeneous-algorithm-orchestration-v2` layer extends this from local schedules to bounded
algorithm and policy changes. It uses the same semantic vocabulary for predicate/scan/scatter,
queue dependencies, sparse/dense representation dispatch, and acquire/render/present/release:

- `gpu-stable-compaction` emits CUDA source and launch plans for exact one-workgroup or bounded
  hierarchical predicate, prefix-scan, capacity guard, stable index/value scatter, and extent commit;
- `queue-overlap` exhaustively assigns a finite dependency DAG to eligible queues, generates
  cross-queue synchronization, invokes the existing hazard verifier, and reports modeled makespan;
- `sparse-update-policy` emits C++ for exact sparse/dense selection with stable output,
  fail-unchanged capacity behavior, and atomic extent publication;
- `presentation-policy` enumerates only device-supported modes, image counts, and flight counts,
  then verifies each finite image lifecycle.

Every family requires measured attribution before search, emits deterministic JSON and GraphML,
and remains non-promotable until an exact application runner supplies matching output/state hashes
and representative physical timestamps. GraphML or a learned model may rank candidates but cannot
establish legality or proof. Queue plans are executable runtime manifests, not source rewrites;
driver overlap and visible presentation remain physical claims.

rc15 makes that optimization stack consumable as a public agent workflow. It adds stable schemas,
three reproducible frontend demonstrations, seeded accepted/rejected transformations, a
requirement-level release gate, a canonical review record, an opt-in Convex review service, and a
static-first release site. Optimization remains local-only by default. Neither source nor raw
artifacts are accepted by the review schema, and review submission requires durable scope consent,
explicit CLI confirmation, and record-level consent.

rc16 adds compositional semantic closure across systems of selected C, C++, Rust, Zig, and Julia
functions. Each frontend emits a shared effect/call summary. `vladder system closure` composes
direct calls through an SCC-aware bounded fixpoint, validates finite ownership/protocol envelopes,
proves summary joins with Z3, and groups necessary external boundaries without blocking closed
neighbors. Protocol summaries add zero implementation candidates: they constrain legality and
proof, while attributed computational grammars remain the only source of search alternatives.
See [Compositional Semantic Closure](docs/compositional-semantic-closure-v1.md).

This is not arbitrary-C++ or whole-device equivalence. RAII, allocation, exceptions, general
concurrency, callbacks, syscalls, drivers, presentation, Vulkan/CUDA host protocols, and external
libraries are proved only through explicit finite adapters over their actual observables.

The Rust frontend captures one exact Cargo package/target/profile, compiler identity, source, MIR,
LLVM IR, and assembly. It lowers supported functions into the same language-neutral
`SemanticFlowGraph` used by the existing frontends; Rust borrow, panic, `Drop`, unsafe, and
monomorphization facts remain proof contracts and provenance rather than a separate semantic
vocabulary. R2 recognizes the seven canonical bounded families over borrowed byte or `f32`
slices and corroborates them against the selected MIR and LLVM. Exact byte reductions additionally
have executable native regeneration: vLadder recaptures MIR, proves the schedule with Z3,
checks fixed-bound LLVM refinement with Alive2, runs adversarial differential tests, and ranks
candidates in a randomized same-executable benchmark. Unsafe contracts, owning allocation,
custom destruction, async, concurrency, FFI, unresolved calls, and external protocols fail closed
with explicit adapter requirements.

The Zig frontend captures a selected native function in its original module graph, compiler/build
identity, safety mode, LLVM IR, and assembly. Z2 accepts explicit bounded comptime type
specializations such as `countScalar(u8, ...)`; Z3 additionally recognizes the seven canonical
bounded families over borrowed byte or `f32` slices. Exact byte reductions regenerate
Zig, derives the realized schedule back from source, proves it with Z3 and canonical Alive2 LLVM,
runs differential tests, and ranks variants in one executable. Allocator ownership, error unions,
`defer`, volatile/atomic effects, assembly, FFI, and unresolved calls remain explicit boundaries.

The Julia frontend captures one concrete module/method/tuple specialization through the declared
project and package module, Julia version, project/manifest, world counter, inferred effects,
lowered/typed IR, LLVM IR, and native assembly. Reflection does not execute arbitrary target
methods. J3 recognizes the seven canonical bounded families for concrete, type-stable,
zero-allocation byte or `Float32` vector specializations. Exact byte reductions additionally rank
warmed steady-state native Julia candidates in independent processes. Other methods/worlds, dynamic
dispatch, GC-visible allocation, globals, exceptions, tasks, `ccall`, nondeterminism, and external
effects fail closed.

For Rust, Zig, and Julia, `status: supported` establishes compiler-corroborated semantic capture,
not automatic optimization by itself. Read the independent `candidate_generation`, `local_proof`,
`benchmark`, and `source_rewrite` capabilities. Families without an executable native lowerer
return `lowerer_required` and never enter the byte-reduction generator.

The package also contains specialist operator, pipeline, projection, quantized-kernel, and
weight-traversal research adapters. Use `vladder grammar` and `vladder lower list` to distinguish
automatic source workflows from shape-specific routes, modeled plans, and research-only modes.

rc10 completes `deep-v2`, the first shared grammar whose coverage is executable end to end rather than
only declarative. Its initial exact byte-predicate-reduction archetype searches scalar, packed-word
SWAR, SIMD mask/popcount, bounded SIMD byte-accumulator, tail, traversal, fusion, constant, and
runtime- or deployment-dispatch realizations. The same derivation regenerates native C, C++20,
Rust, Zig, or Julia source for every terminal. Language adapters contribute typed bounds,
ownership, lifetime, exception, unsafe, numeric, and ISA obligations without forking the
information-flow vocabulary. Z3, compatible Alive2 core refinements, exhaustive boundary
execution, non-empty symbol-resolved assembly or LLVM identities, and randomized paired ranking are all
required by the closed path.

An unresolved hot body is never hashed as an empty physical identity. It is measured without
deduplication and forces `best_verified_found`; `bounded_optimal_local` additionally requires every
terminal identity to resolve and every unique identity to be measured.

`SemanticFlowGraph v2` is the common evidence contract. Obligations have stable IDs, categories,
scopes, proof methods, and native-language bindings. Effects name memory, allocation, cleanup,
exception, synchronization, external-call, publication, invalidation, and transfer behavior.
Protocol transitions and claims are graph-hash inputs, and dangling effect/protocol references
fail closed.

The scope is intentionally precise. `deep-v2` does not enumerate every LLVM-equivalent program or
every algorithm. A negative result is meaningful only after known expert realizations pass the
five-stage audit: representation, derivation, lowering, proof, and physical performance. A failure
before performance identifies missing grammar/tooling coverage rather than a physically inferior
semantic equivalent.

`bounded-dataflow-v1` extends that executable path beyond scalar counts to bounded variable-output
and stateful regions. Its five families cover predicate/mask/stable compaction, fixed-width
wire codecs, transactional baseline/delta transducers, AoS projected multi-reductions, and
deterministic 4x4 packed blocks. All 17 terminals have native C, C++20, Zig, and Julia emission,
deterministic SemanticFlowGraph v2 derivations, bounded Z3 obligations, and compiled differential execution;
fixed codec helpers also receive local Alive2 refinement evidence. Guarded AVX2 and AVX-512
compaction terminals retain scalar fallbacks. Bindings unable to express a named ISA terminal
report `semantic_scalar_fallback` and do not count as distinct physical coverage.

The C++ closure is intentionally finite. Borrowed spans and caller-owned output can close when a
pre-write capacity guard proves no growth, element lifetime is trivial, aliases are declared, and
the local region cannot throw. `std::vector::reserve()` alone does not prove this. Allocating or
owning wrappers, nontrivial records, concurrent publication, callbacks, and external protocols
remain explicit adapters rather than being mislabeled as unsupported local computation. See
[Bounded Variable-Output Dataflow](docs/bounded-dataflow-v1.md).

```bash
vladder dataflow coverage
vladder dataflow verify \
  --contract examples/dataflow/compaction-contract.json \
  --target guarded-avx2-compaction \
  --language cpp \
  --out-dir /tmp/vladder-compaction
```

Semantic realization lifetime is also a first-class graph and grammar dimension.
`LifetimeFlowGraph` models when information becomes valid, how often it is constructed, where it
resides, which transitions invalidate it, when it is last consumed, and how it falls back. The
initial `lifetime-v1` grammar supports repeated-derivation elimination, serialization-body reuse,
immutable/mutable projection splitting, intermediate elimination or final-use retirement, and
placement-resident state.

Every registry rule has a callable deterministic plan lowerer. A plan records legality guards,
information-flow operations, proof obligations, cost signals, and any specialized backend route.
This is distinct from generic source emission: rules without a compatible source backend fail
closed when source mode is requested.

## Public Release Evidence

Run the complete local release decision from one command:

```bash
vladder release check --execute --require-target release_candidate \
  --out build/release-readiness.json
```

The report evaluates source identity, the full test and proof surfaces, quality checks, release
demonstrations, service builds, wheel and sdist contents, clean isolated installs, and each
publication channel independently. Add `--online --require-target formal_release` for the final
GitHub/PyPI/Homebrew decision. `pass`, `fail`, `not_run`, `setup_required`, and `unavailable` are
never collapsed into one optimistic result. Three small C, C++, and Rust demonstrations are documented in
[`demos/README.md`](demos/README.md). The substantial application study is
[`docs/case-studies/neuralfusion.md`](docs/case-studies/neuralfusion.md).
Use `--online --reuse-local-report build/release-readiness.json` when only publication-account
state changed; root and version identity are checked before local evidence is reused.

Public artifacts are schema-versioned:

```bash
vladder schema list
vladder schema validate --kind promotion-summary --artifact promotion-summary.json
vladder review template --promotion-summary promotion-summary.json \
  --project PROJECT --revision GIT_SHA --out agent-review.json
vladder review validate --review agent-review.json
```

Optional source-free contributions use the shipped release service. They require a durable,
scope-specific user decision in addition to `--confirm-upload` and
`privacy.submission_consent=true`; no shared credential is packaged. On first opted-in use, the
client obtains a random installation-scoped `training:write` or `review:write` capability and
stores it under `$XDG_CONFIG_HOME/vladder` with mode `0600`. Unknown state is not consent:

```bash
vladder consent show
vladder consent set --scope canonical-training-data --decision opt-in --confirmed-user-choice
vladder consent set --scope agent-experience-review --decision opt-out --confirmed-user-choice
```

Agents must present the full `consent show` notice and explicitly ask for opt in or opt out before
recording an unknown scope. Training and review are independent. A saved opt-out suppresses upload
and repeated requests across sessions and package updates until the user explicitly asks to change
it. Training opt-in authorizes continuous contribution at every eligible opportunity of all
supported pseudonymized model-training forms the installed release can encode. Review opt-in authorizes a review
request at most once every 30 days, with exact-review approval still required.

The decisive automatic contribution boundary is the terminal `promotion-summary.json`. At that
point semantic coverage, candidate, proof, physical evidence, disposition, blockers, and artifact
lineage have stopped changing for the workflow invocation. `vladder workflow run` and
`vladder workflow summarize` locally anonymize and schema-validate that complete record, then submit
it automatically only when durable canonical-training consent is `opt_in`. Upload failure is
reported in the promotion summary and never invalidates local optimization evidence. Unknown or
opt-out state performs no network action.

The client writes each validated bundle to an owner-only persistent outbox before transport. A
temporary network, service, or rate-limit failure records `continuous_contribution_queued`; a
later opted-in terminal workflow replays pending records. The training opportunity is not lost,
and unknown or opt-out consent never flushes the queue.

The capability is append-only and scope-specific. It cannot read pending records, approve or
modify records, invoke internal Convex functions, or access the deployment. Convex exposes no
direct table API to the client; this registered-function authorization boundary is the service's
equivalent of row-level access control. Verify both positive paths and the negative boundaries
without storing a contribution:

```bash
vladder contribution doctor
```

Where a canonical store already exists, run `vladder training export-prior` without durable
consent first and disclose its record, bundle, and byte estimate. This preflight is local-only.

For a canonical prior store, the continuous path is:

```bash
vladder training sync-prior --store experience --project-id PROJECT_ID \
  --agent AGENT --model MODEL --out-dir training-sync
vladder review submit --review agent-review.json --confirm-upload
```

The v3 training exporter includes bounded normalized graph nodes, edges and topology; structured
grammar actions; search executions; parent/child branch lineage; grammar/candidate/composition and
cross-TU stages; exhaustive, sound, partial, and truncated coverage authority; direct and propagated
descendant utility; search cost; all supported outcome classes; evidence quality; and coarsened
hardware/workload descriptors. The survival target is conservative: observed useful descendants are
`KEEP`, exhaustive or soundly closed dead subtrees may be pruned, and every incomplete negative is
`KEEP_UNCERTAIN`. It excludes source, paths, symbols,
user-defined type names, literals, raw artifacts, prompts, personal data, and the unredacted prior
store. This is pseudonymized structural data, not anonymous data: distinctive topology can
fingerprint an algorithm. A policy change that broadens disclosure invalidates old training
consent. Agents must report an eligible form lacking an exporter rather than silently treating it
as contributed.

The consent ledger is stored outside the package under the user's configuration directory (or
`VLADDER_CONSENT_FILE`) with owner-only permissions. Use `--validate-only` to test the remote path
without storage; because it sends the exact payload to the service, it requires opt-in too. Reviews
and graph-ready v3 search bundles are private pending moderation. Override endpoints with
`VLADDER_REVIEW_ENDPOINT` or `VLADDER_MODEL_TRAINING_ENDPOINT`; ordinary optimization never uses
the network. v1 and flat v2 training bundles are historical validation artifacts only: current producers
reject them, queued historical records are quarantined locally, and the retired service routes return
`410 Gone`. The local privacy policy
is in [`docs/privacy.md`](docs/privacy.md); schema compatibility is in
[`docs/artifact-schemas.md`](docs/artifact-schemas.md).

Release and contributor guides:

- [`docs/designing-systems-code-for-vladder.md`](docs/designing-systems-code-for-vladder.md)
- [`docs/grammar-authoring.md`](docs/grammar-authoring.md)
- [`docs/proof-boundaries.md`](docs/proof-boundaries.md)
- [`docs/benchmark-reproducibility.md`](docs/benchmark-reproducibility.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`ROADMAP.md`](ROADMAP.md)

## Install

Install the current published GitHub candidate with its release artifacts. PyPI publication is a
separate channel; when `1.0.0rc23` is published there, install the Python library and CLI with:

```bash
python3 -m pip install --pre 'vladder==1.0.0rc23'
vladder doctor
```

PyPI installs Python dependencies, not Clang/LLVM, llvm-mca, Alive2, Linux perf, or native language
toolchains. Use the installer, pin rustc/Cargo with the target project's `rust-toolchain.toml`, and
retain the exact Zig and Julia identities recorded in each capture.

On Ubuntu x86_64, the installer provisions an isolated Python environment, installs pinned Zig and
Julia releases with checksum verification when absent, and validates Clang/LLVM, llvm-mca, Z3,
Alive2, perf, rustc/Cargo/rustfmt, and the bundled coding-agent skill:

```bash
./scripts/install.sh --prefix "$HOME/.local/share/vladder"
export PATH="$HOME/.local/share/vladder/bin:$PATH"
vladder doctor --strict
```

Inspect without changing the machine:

```bash
./scripts/install.sh --dry-run
```

Reuse an existing system toolchain:

```bash
./scripts/install.sh --no-system-packages --prefix /tmp/vladder-install
```

Alive2 is pinned to a revision compatible with LLVM 20 when it must be built. Use
`--without-alive2` only for non-promoting analysis; strict source promotion requires it.
Use `--without-language-tools` only when Zig and Julia are intentionally managed outside the
installer. Automatic Zig/Julia bootstrapping currently supports Linux x86_64; other platforms must
provide compatible native toolchains explicitly.

Install from a source checkout for development:

```bash
python3 -m venv .venv
.venv/bin/pip install '.[dev]'
.venv/bin/vladder doctor --strict
```

The release workflow emits and tests an exact-hash `vladder.rb` formula. After the public tap is
configured and a release is published:

```bash
brew install araujota/tap/vladder
vladder doctor
```

The Homebrew formula installs Python, LLVM 20, and Z3. Alive2 and perf remain platform-specific;
strict replacement work must pass `vladder doctor --strict` on the actual benchmark host.

The deprecated `silicontune` console alias remains for one release. The Python import namespace
is `vladder` only.

## CLI Workflow

Start an agent investigation from the production region:

```bash
vladder can-optimize transform --source src/transform.cpp --project . \
  --compile-commands build/compile_commands.json --out-dir vladder-transform
vladder optimize src/transform.cpp --function transform --project . \
  --compile-commands build/compile_commands.json --out-dir vladder-transform
```

Read `disposition.json` first. It contains five evidence facts, the terminal status, a bounded proof
badge, grammar and representativeness qualifications, normalized failures, an economic stopping
decision, one argv-form next command, and at most five decisive artifacts. Use `vladder resume
--out-dir vladder-transform` after supplying a missing contract, oracle, runner, or adapter.
Matching source, compiler, grammar, contract, workload, and tool inputs reuse content-addressed
stages and are classified as revalidation rather than new discovery.

The operational decision tree is:

1. Let `can-optimize` classify the region and read its first unreachable state.
2. Honor `STOP`; resolve generated scaffolds before continuing from `ESCALATE`.
3. Run `optimize` only when the plan says `CONTINUE`.
4. Require candidate proof and randomized paired physical evidence.
5. Require project integration and composed-system confirmation before retention.

Use `workflow`, `cpp`, `region`, `dataflow`, `shader`, `gpu`, and other specialist commands when the
generated plan delegates to them or when authoring an expert manifest directly. They remain stable
interfaces but are no longer the default agent routing decision.

### Learned Search Prior

The optional Prior v0 layer ranks already enumerated semantic-graph actions so vLadder can spend
less proof, compilation, differential-test, and benchmark capacity on low-value candidates. It is
strictly advisory: it cannot emit code, establish legality or equivalence, suppress the baseline,
replace hardware measurement, or promote a rewrite.

```bash
vladder prior init --out prior.yaml
vladder prior run --manifest prior.yaml --out-dir prior-out
vladder prior template --out training-template.yaml
vladder prior materialize --manifest training-template.yaml --store experience
```

Read `prior-out/prior-summary.json` first. The default run is a controlled Grade C pilot and reports
`production_model_status: insufficient_dataset`; synthetic measurements never count toward the
production corpus gate. Real deployment requires leakage-safe root/project/language/hardware
holdouts, calibrated abstention, shadow replay, at least 95% winner recall at the declared budget,
and the unchanged deterministic vLadder proof and promotion path. See
[`docs/learned-search-prior-v0.md`](docs/learned-search-prior-v0.md).
The template is open to future typed graph fields and structured grammar primitives; unknown
semantic vocabulary participates in identity and model features instead of being discarded.

```bash
vladder cpp adapter --report vladder-cpp-inspect/cpp-support.json --out-dir vladder-cpp-adapter
vladder protocol verify --manifest state-protocol.yaml --out-dir vladder-protocol-proof
vladder benchmark paired --manifest paired-benchmark.yaml --out-dir vladder-paired
vladder benchmark compose --manifest regional-effects.yaml --out vladder-composition.json
vladder shader synthesize --source kernel.comp --runner-manifest gpu-runner.yaml --out-dir vladder-shader-out
vladder gpu capture --manifest heterogeneous-workflow.yaml --out-dir vladder-gpu-capture
vladder gpu synthesize --manifest heterogeneous-workflow.yaml --out-dir vladder-gpu-candidates
vladder gpu verify --manifest heterogeneous-workflow.yaml --out-dir vladder-gpu-proof
vladder gpu rank --manifest heterogeneous-workflow.yaml --out-dir vladder-gpu-ranking
vladder gpu probe --out gpu-architecture.yaml
vladder gpu topology --out device-topology.json
vladder gpu cuda-optimize --source kernel.cu --function transform \
  --architecture gpu-architecture.yaml --out-dir vladder-cuda-out
vladder gpu queue-template --topology device-topology.json --out queue.yaml
vladder gpu protocol-verify --manifest queue.yaml --out-dir queue-proof
vladder gpu plan-synthesize --manifest algorithm-or-policy.yaml --out-dir plans
vladder gpu plan-rank --manifest physical-plan-ranking.yaml --out-dir plan-ranking
```

For an automatically supported Rust region:

```bash
vladder workflow init --kind rust --out vladder-rust-workflow.yaml
vladder rust inspect --manifest-path Cargo.toml --source src/lib.rs --function module::count
vladder rust synthesize --manifest-path Cargo.toml --source src/lib.rs --function module::count
vladder rust optimize --manifest-path Cargo.toml --source src/lib.rs --function module::count
```

Read `rust-support.json` before synthesis. `supported` means the selected common information-flow
operation and local effect envelope closed; it does not mean arbitrary Rust, owning-wrapper, or
external protocol equivalence. Proof and benchmark artifacts remain separate promotion gates.

For bounded Zig and Julia regions:

```bash
vladder zig optimize --source src/root.zig --function countEqual --build-root .
vladder julia optimize --project . --source src/Package.jl --module Package \
  --function count_equal --signature 'Vector{UInt8},UInt8'
```

Read `zig-support.json` or `julia-support.json` first. Native compiler LLVM is retained as
provenance; strict local proof composes source-derived schedule validation, parametric Z3, and a
canonical schedule LLVM refinement. Do not report that canonical lowerer proof as direct proof of
Zig frontend aliases or Julia's GC/safepoint ABI.

The shader or heterogeneous GPU runner must emit exact output hashes and device timestamps. A
candidate that only passes `spirv-val`, a bounded launch proof, a static cost model, or a simulated
runner remains non-promotable. Use `vladder gpu support` to inspect available kernel, counter, and
device tooling and see [GPU Compute Evidence](vladder/skills/vladder/references/gpu-workflow.md).

For repository or runtime architecture work, begin with an explicit lifetime manifest and trace:

```bash
vladder lifetime analyze \
  --manifest examples/lifetime/lifetime_corpus.yaml \
  --trace examples/lifetime/lifetime_trace.json \
  --out-dir vladder-lifetime-analysis

vladder lifetime synthesize \
  --manifest examples/lifetime/lifetime_corpus.yaml \
  --trace examples/lifetime/lifetime_trace.json \
  --out-dir vladder-lifetime-out
```

The manifest is authoritative for source identity, scopes, invalidators, ownership, publication,
retirement, placement, and fallback. Traces measure repeated construction, retention, and
transfer; observed non-mutation never widens a valid lifetime. Accepted plans emit Z3 obligations,
transition replay, an invalidation matrix, debug-oracle requirements, and an
`AGENT_REALIZATION.md` handoff. Concurrent or device-owned protocols require an explicit CBMC,
TLA+, or equivalent adapter. Alive2 proves only local compiled helpers, not lifecycle protocols.

The bundled capability evaluation is isolated from production applications:

```bash
vladder lifetime evaluate-corpus \
  --manifest examples/lifetime/lifetime_corpus.yaml \
  --trace examples/lifetime/lifetime_trace.json \
  --out-dir vladder-lifetime-evaluation
```

Its timings are mechanism microbenchmarks, not NeuralFusion or production application results.

Analyze a target:

```bash
vladder analyze examples/clamp.c \
  --function transform \
  --out-dir vladder-analysis
```

Inspect the grammar and one family:

```bash
vladder grammar
vladder grammar --family memory-alias
```

Validate and inspect the executable lowering layer:

```bash
vladder lower validate
vladder lower list
vladder lower show --family layout-representation --rule aos-to-soa
```

Audit and rank the executable deep grammar before interpreting a local search result:

```bash
vladder deep coverage
vladder deep audit \
  --manifest examples/deep_grammar/expert-audit.yaml \
  --out-dir vladder-deep-audit
vladder deep rank \
  --language rust \
  --predicate equal-u8 \
  --processes 10 \
  --repetitions 3 \
  --cpu 0 \
  --out-dir vladder-deep-ranking
```

`deep rank` proves every reachable terminal, deduplicates normalized hot assembly, and physically
ranks each unique realization. It reports `bounded_optimal_local` only when the finite region is
saturated and all terminal proof/measurement gates close; otherwise it reports
`best_verified_found`.

Lower a rule into an auditable plan only after establishing its contract facts:

```bash
vladder lower plan \
  --family hardware-codegen \
  --rule avx2 \
  --fact 'target ISA' \
  --fact 'OS vector state' \
  --fact 'fallback availability' \
  --input-identity sha256:REGION_HASH
```

Search, prove, benchmark, and rank candidates:

```bash
vladder optimize examples/clamp.c \
  --function transform \
  --graph-inner-loop \
  --verification-policy strict \
  --min-speedup-pct 2 \
  --alive2 \
  --reps 25 \
  --cpu 0 \
  --out-dir vladder-out
```

For the fully automatic bounded-region path, classify first and then run the closed workflow:

```bash
vladder region inspect \
  --source examples/automatic_regions/supported_scan.c \
  --function transform \
  --out-dir vladder-inspect

vladder region optimize \
  --source examples/automatic_regions/supported_scan.c \
  --function transform \
  --out-dir vladder-region-out
```

`bounded-regions-v1` emits regenerated source and requires structural legality, Z3 loop and
memory proofs, canonical LLVM IR identity or Alive2, differential execution, and hardware
measurement. The report records whether canonical identity discharged refinement before solver
invocation or whether `alive-tv` ran. Unsupported regions fail closed with a typed adapter
requirement. See
`vladder/skills/vladder/references/automatic-regions.md` for the precise boundary.

For a bounded C++ region, export the production compilation database and use the C++ workflow:

```bash
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

vladder cpp inspect \
  --source src/transform.cpp \
  --function transform \
  --compile-commands build \
  --out-dir vladder-cpp-inspect

vladder cpp audit \
  --manifest cpp-regions.yaml \
  --materialize-isolation \
  --out-dir vladder-cpp-audit

vladder cpp synthesize \
  --source src/owning_path.cpp \
  --function OwningPath::run \
  --compile-commands build \
  --out-dir vladder-cpp-synthesis

vladder cpp optimize \
  --source src/transform.cpp \
  --function transform \
  --compile-commands build \
  --min-speedup-pct 2 \
  --out-dir vladder-cpp-out
```

Without `--materialize-isolation`, `cpp audit` only classifies. With it, vLadder compiles and
proves predicted local units but still performs no optimization, benchmark, or source change. Use
`--symbol _Z...` when overloads or template instances share a source name, and
`--command-index N` when the compilation database contains multiple configurations for one file.
Inspect `closure.disposition`, each independent `closure.capabilities` entry, categorical
`protocol_scopes`, `compiled-effects.json`, `typed-abi.json`, `subregions.json`,
`cpp-information-flow.json`, `region-closure.json`, `region-closure-proof.json`, and
`proof-envelope.json`. `bounded-cpp-regions-v8` can emit whole
local-function proof units and source-preserving lambda capsules for eligible loops inside owning
C++ methods. Ordinary early-return loops use a whole-function CFG boundary so return semantics are
not changed by lambda extraction. Guarded no-growth trivial vector regions and call-preserving
local helpers are eligible bounded capsules. Its bounded schedule grammar emits guarded Clang unroll candidates with identity and
Z3 schedule evidence, but requires an application benchmark adapter before ranking or applying
them. RAII, exceptions/destructors, allocation ownership, concurrency, callbacks, Vulkan/OpenUSD,
and other external protocols remain explicitly outside generic whole-function proof. They do not
block independently closed local regions or vLadder's attribution, lifetime, placement, and
contract-bounded workflows. See [C++ kernel
extraction](docs/cpp-kernel-extraction.md) for the exact support and claim boundary and the
[NeuralFusion v4 acceptance benchmark](docs/neuralfusion-cpp-v4-acceptance.md) for production
coverage evidence.

Key outputs:

- `analysis/`: target LLVM IR, information-flow graph, semantic slice, and SMT model
- `build/`: generated candidate C, LLVM IR, assembly, and llvm-mca inputs
- `proofs/`: Z3/SMT obligations and memory-footprint proofs
- `alive2/`: sanitized IR and Alive2 logs
- `benchmark.csv`: candidate measurements and rejection statuses
- `perf.json`: complete run, toolchain, grammar, proof, ranking, and promotion record
- `optimized.c` and `optimized.patch`: emitted only for a promotable non-baseline winner
- `report.html`: developer-readable result

After applying a promoted patch, close the source/proof correspondence chain:

```bash
vladder verify-application \
  --report vladder-out/perf.json \
  --source path/to/production.c \
  --function transform \
  --compile-arg=-Ipath/to/includes \
  --out vladder-out/applied-verification.json
```

This checks that the applied function is the same generated function that passed the recorded Z3,
memory, LLVM-refinement, and differential gates, then asks Clang to syntax/type check it in its source
context. Project tests and end-to-end benchmarks remain mandatory.

## Python Library

```python
from pathlib import Path

from vladder import (
    AutomaticRegionRequest,
    BenchmarkPolicy,
    CppRegionRequest,
    LifetimeRequest,
    OptimizationRequest,
    VelocityLadder,
    VerificationPolicy,
    LoweringRequest,
)

engine = VelocityLadder()
result = engine.optimize(
    OptimizationRequest(
        source=Path("kernel.c"),
        function="transform",
        output_directory=Path("vladder-out"),
        verification_policy=VerificationPolicy.STRICT,
        minimum_speedup_pct=2.0,
        benchmark=BenchmarkPolicy(repetitions=25, cpu=0),
        graph_inner_loop=True,
    )
)

print(result.winner)
print(result.promoted)
print(result.patch_path)

automatic = engine.optimize_region(
    AutomaticRegionRequest(
        source=Path("bounded.c"),
        function="transform",
        output_directory=Path("vladder-region-out"),
    )
)
print(automatic.report)

cpp = engine.cpp_region(
    CppRegionRequest(
        source=Path("src/transform.cpp"),
        function="transform",
        compilation_database=Path("build/compile_commands.json"),
        output_directory=Path("vladder-cpp-out"),
        action="optimize",
    )
)
print(cpp.report["proof_classification"])

lifetime = engine.lifetime(
    LifetimeRequest(
        manifest=Path("examples/lifetime/lifetime_corpus.yaml"),
        trace=Path("examples/lifetime/lifetime_trace.json"),
        output_directory=Path("vladder-lifetime-out"),
    )
)
print(lifetime.report["claim_boundary"])

plan = engine.lower(
    LoweringRequest(
        family="memory-alias",
        rule="add-restrict",
        contract_facts={
            "pointer provenance": True,
            "alias sets": True,
            "object bounds": True,
        },
        input_identity="sha256:bounded-region",
    )
)
print(plan.to_dict())
```

The library and CLI share one execution path and the same artifact schema.

## Grammar Coverage

The `vladder-v1` capability registry has complete deterministic plan lowering for:

- executable scalar/word/SIMD lane, mask, reduction, traversal, tail, fusion, and dispatch forms
- expression and bit-vector algebra
- branches, selects, masks, and guarded specialization
- unrolling, tiling, interchange, fusion/fission, and software pipelines
- pointer footprints, aliasing, alignment, restrict, prefetch, gather, and scatter
- reductions, scans, recurrences, and online reductions
- AoS/SoA, blocking, packing, interleaving, and layout adapters
- producer-consumer fusion and materialization choices
- bounded mutable state, windows, and transition systems
- single-owner and modeled SPSC/memory-order concerns
- ISA, SIMD width, unroll, prefetch, and compiler/codegen variants
- operator, pipeline, and useful-work-per-byte execution organization
- semantic validity, realization frequency, retention, invalidation, retirement, and placement

Every family declares contract facts, proof strategies, cost signals, maturity, and an importable
lowerer. `vladder lower list` reports plan coverage and specialized backend-route coverage
separately. A backend route points to an existing shape-specific vLadder generator or verifier;
it does not mean that arbitrary source can be emitted for that rule. New production grammar
families require a measured attribution study and plausible improvement ceiling before admission.

## Verification Policy

Three policies are available:

- `strict`: memory legality, schema/SMT proof, canonical LLVM IR identity or Alive2 correctness,
  differential execution, and minimum measured effect are all required for patch promotion.
- `balanced`: memory legality, differential execution, measured effect, and at least one formal
  equivalence path are required.
- `exploratory`: permits investigation but never promotes a source replacement.

Proof scope is explicit. Canonical identity is used only when normalized proof functions are
alpha-identical; otherwise Alive2 validates LLVM refinement for the compiled functions and flags
it receives. A bounded pointer-footprint proof is not a whole-C proof, and differential tests do
not generalize beyond their corpus. Unsupported or timed-out obligations fail strict promotion.
For lifetime candidates, Z3 proves bounded version and mutation obligations, transition replay
checks lifecycle sequences, and protocol adapters cover concurrency or device ownership.

## Agent Skill

The distribution includes a Codex-compatible `vladder` skill:

```bash
vladder skill validate
vladder skill install --target "${CODEX_HOME:-$HOME/.codex}/skills"
```

The skill directs a resident coding agent through profiling, semantic contracts, grammar
selection, bounded search, zero-trust source reconstruction, proof inspection, source rewrite,
post-application verification, project testing, and bounded reporting. It also directs agents to
inspect semantic lifetime before local code generation and preserve invalidation, retirement,
fallback, and shadow-oracle requirements during architectural rewrites.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install '.[dev]'
python3 scripts/audit_release.py --root .
.venv/bin/python -m pytest -q
.venv/bin/vladder release check --execute --require-target release_candidate
openspec validate release-vladder-library --strict
openspec validate release-channels-rc4 --strict
openspec validate lifetime-aware-realization-v1 --strict
openspec validate direct-cpp-kernel-extraction --strict
openspec validate deep-shared-grammar-v2 --strict
python3 -m build
python3 -m twine check dist/*
python3 scripts/audit_release.py --artifact dist/*.whl --artifact dist/*.tar.gz
python3 scripts/release_preflight.py --repository araujota/vladder
```

The optional website and review service are independently buildable under `apps/release-site` and
`services/review-backend`. Their deployment credentials are never prerequisites for local
optimization.

The source audit checks every tracked and non-ignored release input. Distribution audits reject
generated outputs, caches, model files, vendored application trees, credentials, compiled objects,
and oversized machine-local artifacts even when the checkout contains ignored development output.

The pinned no-write C, C++, Zig, and Julia acceptance study is documented in
[docs/cross-language-rc12-evaluation.md](docs/cross-language-rc12-evaluation.md). It distinguishes
compiler capture, semantic closure, candidate generation, proof, and physical rejection rather
than treating successful command execution as optimization success.

## Publishing

Tag-triggered GitHub Actions first require the formal release-readiness target, then build and test
the package, verify the exact Homebrew formula on macOS, create checksums, publish a GitHub
prerelease, and upload the same wheel and sdist to PyPI through Trusted Publishing. Tap publication
is protected by a separate GitHub environment. PyPI and Homebrew remain `setup_required` until the
one-time account configuration in the release guide has been completed. Maintainer
setup and release commands are in [docs/releasing.md](docs/releasing.md); changes are summarized
in [CHANGELOG.md](CHANGELOG.md).

## Claim Boundary

vLadder may report the best measured verified candidate within a named grammar region, target,
workload, and contract. It does not claim universal or physical global optimality. A verified
regional win is not an end-to-end win until the production application is rebuilt, tested, and
measured under the original workload.

## License

MIT. See [LICENSE](LICENSE).
