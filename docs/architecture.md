# vLadder Architecture

## Optimization Boundary

vLadder operates above LLVM. It extracts bounded C/C++ regions into semantic and physical
information-flow representations, searches a finite implementation grammar, regenerates source,
and delegates instruction selection and scheduling to an unmodified compiler.

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
      Clang IR and source extraction
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

`bounded-cpp-regions-v4` treats semantic capture, local closure, proof, candidate generation,
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
