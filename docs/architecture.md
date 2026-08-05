# vLadder Architecture

## Agent Evidence Plane (rc6)

`AgentWorkflow` is the default control plane above the existing optimization hierarchy. One
manifest freezes the region, source/compiler identity, contract, attribution, workload, and
promotion policy. Deterministic stages are keyed by those inputs and may be resumed. Every run emits
one promotion summary with independent completion, semantic coverage, candidate, proof, physical,
integration, promotion, and retained-revalidation states.

Artifact lineage is a DAG from source through extraction, candidate, proof, benchmark, and final
disposition. C++ closure can generate incomplete application adapters; two finite retained-state
protocols have direct Z3 encodings. All other external protocols remain plugin/runner boundaries.
Paired physical evidence is randomized and overlap-aware. GPU compute enters through a portable
SPIR-V module workflow whose structural validation remains distinct from output equivalence and
device timing.

The evidence plane changes orchestration and application closure. It does not replace expression,
loop, operator, lifetime, LLVM, Alive2, Z3, or hardware-specific search layers.

## Heterogeneous Execution Plane (rc14)

`heterogeneous-execution-v1` extends `SemanticFlowGraph v2` across GPU kernels and bounded device
protocols. It does not fork the semantic vocabulary by API or vendor. SPIR-V and PTX names remain
provenance; their operations lower into common dispatch, workgroup, lane, memory-transaction,
barrier, atomic, resource-use, and unsupported-operation nodes. CUDA source enters through pinned
PTX lowering when `nvcc` is available.

A hardware manifest supplies the exact device identity and finite resource model. Static search
enumerates workgroup geometry and modeled memory/schedule alternatives, estimates occupancy,
register and shared-memory limits, physical transactions, coalescing, and instruction work, and
classifies each result as launch-only, source-rewritable, or adapter-required. Only unchanged
lane-independent launch geometry and literal GLSL workgroup rewrites currently have executable
generic realization; code-shape changes remain explicit adapter work.

Host/device behavior is represented by separate but composable queue, DMA/topology, and
presentation protocol graphs. Z3 checks declared execution dependencies, visibility, timeline
ordering, ownership transfer, DMA registration/completion/reuse, and acquire/present/scanout
lifecycle obligations. Those bounded models do not prove driver, firmware, NIC, display-engine,
or undeclared failure behavior.

Physical ranking randomizes baseline/candidate order and uses complete output hashes plus clean
device timestamps. CUPTI, ROCprofiler, and Vulkan/runner counters normalize into shared categories
for attribution. Replayed or serialized profiler timing, simulated runners, mismatched device
identity, incomplete observables, or failed protocol obligations cannot promote a candidate.

## Optimization Boundary

vLadder operates above LLVM. It extracts bounded C/C++/Rust/Zig/Julia regions into semantic and physical
information-flow representations, searches a finite implementation grammar, regenerates source,
and delegates instruction selection and scheduling to an unmodified compiler.

## Semantic Flow And Language Adapter Plane (rc10)

`LanguageAdapter` captures build identity, resolves one source region, emits a language semantic
IR, classifies effects, lowers to the shared `SemanticFlowGraph v2`, regenerates native source,
and binds proof and benchmark evidence. C and C++ are authoritative v2 producers rather than
legacy/coarse side channels. The graph vocabulary is language-neutral. C, C++, Rust, Zig, and Julia all
use common value, state, control, materialization, transfer, ownership, and lifetime concepts;
language-specific facts belong in provenance, contracts, and proof obligations unless they express
a genuinely new semantic concept.

V2 formalizes four evidence planes. `SemanticObligation` records a stable ID, category, statement,
scope, proof method, and language binding. `SemanticEffect` records phase, resource,
observability, ordering, participating nodes, and discharged obligations. `ProtocolTransition`
models ownership, lifetime, cleanup, publication, invalidation, dispatch, exception, and
concurrency state changes. `SemanticClaim` distinguishes proved, required, assumed, excluded, and
unverified scope. All are deterministic graph-hash inputs; unresolved references are rejected.

The first Rust adapter captures Cargo plus rustc MIR/LLVM/assembly and closes an exact borrowed-byte
reduction. MIR establishes the source operation and generated schedule, Z3 proves the schedule and
bounded content obligations, and Alive2 checks local fixed-bound LLVM refinement. Unsafe, owning,
destruction, panic-recovery, async, concurrent, FFI, and external protocols remain explicit
boundaries rather than being silently flattened into LLVM behavior.

The Zig adapter follows the same ahead-of-time evidence chain with native safety-mode capture and
explicit allocator, error, defer, volatile, atomic, assembly, and FFI boundaries. The Julia adapter
binds evidence to one concrete method specialization, active project/manifest, world counter,
inferred type/effects/allocation state, and JIT target. Generic functions and later worlds are not
covered by one specialization proof.

Both regenerate native source and parse the realized schedule back from source. A shared
parametric Z3 theorem proves index coverage and exact reduction; a source-derived canonical LLVM
unit validates the common lowerer with Alive2. Native Zig and Julia LLVM remain compiler
provenance rather than being relabeled as direct frontend proofs.

## Executable Deep Grammar Plane

`deep-v2` separates a semantic operation from its physical realization. The initial operation is
an exact byte predicate plus reduction; realizations include scalar lanes, packed words, SIMD
masks/popcount, bounded byte-lane accumulation, and guarded dispatch. `LaneMap`, `Pack`,
`MaskExtract`, `PopulationCount`, `HorizontalReduce`, `Tail`, `Fuse`, and `ComplexityBound` are
shared graph nodes. C object bounds, C++ borrowed/noexcept contracts, Rust borrow/unsafe/panic
facts, Zig many-pointer/safety facts, and Julia rooting/inbounds/specialization facts attach to
this graph as typed adapter obligations.

Search retains alternative acyclic derivations until saturation or an explicit budget. Each rule
records preconditions, physical parameters, complexity deltas, proof obligations, and cost
signals. Native emitters reconstruct C, C++20, Rust, Zig, or Julia from every selected terminal
graph. Z3 proves lane,
bit-vector, reduction, no-wrap, traversal, tail, and dispatch obligations; Alive2 validates
compatible vector cores; differential execution checks native memory behavior; hardware ranking
uses randomized same-executable pairs. Normalized assembly identities prevent compiler-equivalent
forms from being counted as independent candidates.

The expert grammar audit is a meta-validation layer. A known fast source form must cross
representation, derivation, lowering, proof, and performance stages. A failure at an earlier stage
invalidates a broad negative optimization claim. Only a saturated finite region with every unique
terminal closed may be called `bounded_optimal_local`.

The core hierarchy is:

1. Expression graph: scalar arithmetic, predicates, and bit-vector operations.
2. Loop graph: iteration spaces, dependence, reductions, scans, recurrences, and schedules.
3. Operator graph: streams, state, layouts, materialization, multiple outputs, and fusion.
4. Projection/kernel graph: packed representations, decode, accumulation, and physical resources.
5. Pipeline/traversal graph: cross-operator movement, work reuse, runtime dispatch, and portfolios.

Each level owns a grammar, legality checks, proof obligations, static filters, physical benchmark,
and result classification. Lower levels may be exhaustive; larger levels are normally
`best_verified_found`.

## Registry-Driven Lowering

The `vladder-v1` registry resolves every family to an importable lowerer class. Each class owns an
independent table of implemented rule effects; validation compares that table with the registry
and fails on missing or extra rules. Every rule can produce a deterministic plan containing:

- established and missing semantic facts,
- ordered information-flow operations,
- required parameters and guards,
- proof obligations and cost signals,
- an optional specialized backend route,
- grammar and input identities plus a derivation hash.

Plan lowering is universal; generic source emission is not. A specialized route points to an
existing shape-specific generator, search engine, layout transformer, or proof adapter. Source
mode fails closed when no such route exists, and a routed plan is not promotable source until its
backend emits a candidate that passes verification and physical benchmarking.

## Core Data Flow

```text
source + contract + target + workload
                  |
   source frontend + semantic IR extraction
                  |
       normalized information flow
                  |
        grammar-bounded candidates
                  |
 structural / Z3 / Alive2 / differential gates
                  |
     assembly, llvm-mca, and hardware runs
                  |
       ranking and promotion policy
                  |
      source patch and proof bundle
```

## Automatic Bounded-Region Frontend

`bounded-regions-v1` is the common fail-closed frontend. It independently checks the canonical C
ABI, extracts one structured loop, compiles the target with Clang, classifies the LLVM-derived
flow graph, and admits only pointwise, guarded-pointwise, stencil, scan, recurrence, and bounded
indirect-memory classes. Its generated source candidate is executed through the same strict proof
and measurement pipeline as hand-registered candidates.

Everything outside that finite set produces an `adapter_required` report naming the required
language, ABI, loop, call, control-flow, memory-order, compile-command, or specialized graph
boundary. This is the contract between generic automation and attending-agent reimplementation:
the agent supplies missing semantics, while vLadder remains responsible for regeneration, proof,
measurement, and source-identity checks once the region is admitted.

The information-flow graph records operation identity, dependency, type, shape, address and alias
sets, lifetime, ordering, numerical class, hardware facts, and provenance. Specialized graphs add
state ownership, layouts, quantization blocks, resource pressure, or token/sequence lanes.

## Bounded C++ Closure Frontend

`bounded-cpp-regions-v6` treats semantic capture, local closure, proof, candidate generation,
benchmarking, source realization, and protocol equivalence as separate facts.
It selects a concrete definition with Clang and the production compilation database, preserves
source-level ownership and exception hazards, and recursively summarizes definition-visible LLVM
callees. The resulting typed ABI, effect summary, helper closure, source subregions, and
information-flow graph are build-specific evidence.

The support lattice is:

1. `canonical_source_transform`: automatic source extraction, local proof, measurement, and C++
   regeneration are implemented.
2. `whole_function_local_ir`: the complete compiled function has modeled boundaries and local
   effects and can be emitted as a proof unit; a nonidentity rewrite requires a matching grammar.
3. `bounded_state_transition`: local compiled effects exist, but correctness also depends on an
   explicit object-state projection and invariant.
4. `extractable_subregions`: useful loops are identified inside an owning or external wrapper;
   eligible regions are compiled as noinline lambda proof capsules and can receive bounded source
   schedule candidates.
5. `external_protocol`: the function remains outside local LLVM refinement and needs a declared
   semantic adapter.

For tiers 2 through 4, vLadder can emit compositional proof units and, where a grammar matches,
candidate source without applying it. The capability vector distinguishes predicted from actual
evidence. Categorical protocol scopes name exception/destructor, ownership, concurrency, and
external API claims that local IR cannot generically close, while preserving local optimization,
hardware attribution, lifetime/placement search, and explicit domain-adapter workflows.

## Search

Local expression and loop regions use enumeration or saturation with canonicalization and
assembly deduplication. Operator and pipeline regions use bounded beam search and dominance
pruning. Static costs rank or reject obvious regressions but do not replace the real hardware
oracle. Every candidate retains its ordered derivation, grammar hash, contract, and rejection
reason.

New grammar families require an attribution study tied to measured cycles, bytes, cache traffic,
dependency depth, or synchronization. This keeps representational breadth from creating an
unbounded low-value search space.

## Release Surfaces

- `vladder.api`: typed embedding facade
- `vladder` CLI: analysis, search, proofs, benchmarking, patching, diagnostics, and skill tools
- `vladder/grammars`: vocabulary, callable lowerer entrypoints, backend routes, and maturity metadata
- `vladder/skills/vladder`: coding-agent workflow
- `openspec`: behavioral contracts and research provenance
- `examples`: standalone and specialist contract fixtures

The generalized release excludes compiler sources, model files, external application trees, and
benchmark outputs. Specialist integrations consume externally pinned dependencies.
