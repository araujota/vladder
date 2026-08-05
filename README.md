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

## Release Status

The package version is `1.0.0rc11`, the C++ closure matrix is
`bounded-cpp-regions-v5`; it retains the
`bounded-regions-v1` C frontend and includes `bounded-rust-regions-v1`,
`bounded-zig-regions-v1`, and `bounded-julia-regions-v1` adapters. The C frontend fully
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

Results expose independent capture, isolation, candidate-generation, local-proof, benchmark,
source-rewrite, and protocol-equivalence capabilities. v5 can materialize whole local functions
and eligible nested loops as proof units, and can emit bounded source schedule candidates for the
latter. It still requires a workload adapter before ranking a noncanonical C++ candidate. Alive2
can prove local LLVM rewrites; it does not prove RAII, allocation, object invariants, exception,
concurrency, Vulkan/OpenUSD, callback, or other owning protocols. These categorical protocol
limits do not block independently closed subregions or the attribution, lifetime, placement, and
contract-bounded parts of vLadder.

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

This is not arbitrary-C++ or whole-device equivalence. RAII, allocation, exceptions, general
concurrency, callbacks, syscalls, drivers, presentation, Vulkan/CUDA host protocols, and external
libraries are proved only through explicit finite adapters over their actual observables.

The Rust frontend captures one exact Cargo package/target/profile, compiler identity, source, MIR,
LLVM IR, and assembly. It lowers supported functions into the same language-neutral
`SemanticFlowGraph` used by the existing frontends; Rust borrow, panic, `Drop`, unsafe, and
monomorphization facts remain proof contracts and provenance rather than a separate semantic
vocabulary. R1 automatically regenerates and verifies safe, monomorphic, allocation-free
borrowed-slice reductions. It emits native Rust, recaptures MIR, proves the schedule with Z3,
checks fixed-bound LLVM refinement with Alive2, runs adversarial differential tests, and ranks
candidates in a randomized same-executable benchmark. Unsafe contracts, owning allocation,
custom destruction, async, concurrency, FFI, unresolved calls, and external protocols fail closed
with explicit adapter requirements.

The Zig frontend captures a selected native function, compiler/build identity, safety mode, LLVM
IR, and assembly. Z1 closes allocation-free exact byte reductions over borrowed slices, regenerates
Zig, derives the realized schedule back from source, proves it with Z3 and canonical Alive2 LLVM,
runs differential tests, and ranks variants in one executable. Allocator ownership, error unions,
`defer`, volatile/atomic effects, assembly, FFI, and unresolved calls remain explicit boundaries.

The Julia frontend captures one concrete module/method/tuple specialization, Julia version,
project/manifest, world counter, inferred effects and allocation, lowered/typed IR, LLVM IR, and
native assembly. J1 closes type-stable zero-allocation exact byte reductions and ranks warmed
steady-state native Julia candidates in independent processes. Other methods/worlds, dynamic
dispatch, GC-visible allocation, globals, exceptions, tasks, `ccall`, nondeterminism, and external
effects fail closed.

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
execution, normalized assembly identities where available, and randomized paired ranking are all
required by the closed path.

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
and stateful C++ regions. Its five families cover predicate/mask/stable compaction, fixed-width
wire codecs, transactional baseline/delta transducers, AoS projected multi-reductions, and
deterministic 4x4 packed blocks. All 17 terminals have native C++20 emission, deterministic
SemanticFlowGraph v2 derivations, bounded Z3 obligations, and compiled differential execution;
fixed codec helpers also receive local Alive2 refinement evidence. Guarded AVX2 and AVX-512
compaction terminals retain scalar fallbacks.

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

## Install

Install the current published GitHub candidate with its release artifacts. PyPI publication is a
separate channel; when `1.0.0rc11` is published there, install the Python library and CLI with:

```bash
python3 -m pip install --pre 'vladder==1.0.0rc11'
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

The release workflow emits an exact-hash `vladder.rb` formula. After the project tap is created:

```bash
brew install OWNER/tap/vladder
vladder doctor
```

The Homebrew formula installs Python, LLVM 20, and Z3. Alive2 and perf remain platform-specific;
strict replacement work must pass `vladder doctor --strict` on the actual benchmark host.

The deprecated `silicontune` console alias remains for one release. The Python import namespace
is `vladder` only.

## CLI Workflow

Start an agent investigation from one manifest:

```bash
vladder workflow init --kind cpp --out vladder-workflow.yaml
# Fill every TODO and record attribution, contract, and workload identity.
vladder workflow run --manifest vladder-workflow.yaml --out-dir vladder-workflow-out
```

Read `promotion-summary.json` first. It contains the proof class, meaningful-coverage state,
candidate/proof/benchmark/integration states, blockers, one next action, five decisive artifacts,
and a queryable artifact lineage. Matching source, compiler, grammar, contract, workload, and tool
inputs resume deterministically and are classified as revalidation rather than a new discovery.

The operational decision tree is:

1. Choose `c`, `cpp`, `rust`, `zig`, `julia`, `lifetime`, `shader`, or `protocol` from the region's actual semantic boundary.
2. Run inspection and read `meaningful_semantic_coverage`.
3. If an adapter remains, generate or complete it; do not relabel local proof as wrapper proof.
4. Require candidate proof and randomized paired physical evidence.
5. Require project integration and composed-system confirmation before retention.

```bash
vladder cpp adapter --report vladder-cpp-inspect/cpp-support.json --out-dir vladder-cpp-adapter
vladder protocol verify --manifest state-protocol.yaml --out-dir vladder-protocol-proof
vladder benchmark paired --manifest paired-benchmark.yaml --out-dir vladder-paired
vladder benchmark compose --manifest regional-effects.yaml --out vladder-composition.json
vladder shader synthesize --source kernel.comp --runner-manifest gpu-runner.yaml --out-dir vladder-shader-out
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

The shader runner must emit exact output hashes and device timestamps. A candidate that only passes
`spirv-val` remains non-promotable.

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
`cpp-information-flow.json`, and `proof-envelope.json`. `bounded-cpp-regions-v5` can emit whole
local-function proof units and source-preserving lambda capsules for eligible loops inside owning
C++ methods. Its bounded schedule grammar emits guarded Clang unroll candidates with identity and
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
openspec validate release-vladder-library --strict
openspec validate release-channels-rc4 --strict
openspec validate lifetime-aware-realization-v1 --strict
openspec validate direct-cpp-kernel-extraction --strict
openspec validate deep-shared-grammar-v2 --strict
python3 -m build
python3 -m twine check dist/*
python3 scripts/audit_release.py --artifact dist/*.whl --artifact dist/*.tar.gz
python3 scripts/release_preflight.py --repository OWNER/REPOSITORY
```

The release audit rejects generated outputs, caches, model files, vendored application trees,
credentials, compiled objects, and oversized machine-local artifacts.

## Publishing

Tag-triggered GitHub Actions build and test the package, create checksums and a Homebrew formula,
publish a GitHub prerelease, and upload the same wheel and sdist to PyPI through Trusted
Publishing. Optional tap publication is protected by a separate GitHub environment. Maintainer
setup and release commands are in [docs/releasing.md](docs/releasing.md); changes are summarized
in [CHANGELOG.md](CHANGELOG.md).

## Claim Boundary

vLadder may report the best measured verified candidate within a named grammar region, target,
workload, and contract. It does not claim universal or physical global optimality. A verified
regional win is not an end-to-end win until the production application is rebuilt, tested, and
measured under the original workload.

## License

MIT. See [LICENSE](LICENSE).
