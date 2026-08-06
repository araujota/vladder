# Design

## Research Basis

LLVM's function attributes already expose a finite effect vocabulary such as `memory(argmem:
read)`, `nofree`, `nocallback`, `nosync`, `nounwind`, and `willreturn`. MemorySSA supplies
intraprocedural def/use/clobber structure, while LLVM's Attributor demonstrates a fixpoint model for
interprocedural attribute deduction. Alive2 explicitly does not prove interprocedural
transformations, so local LLVM refinement must be composed with separate call-relation and protocol
obligations.

Rust MIR makes drop elaboration and cleanup control explicit. Zig's error unions and `defer`
represent explicit control and cleanup relationships. Julia's typed SSA and escape analysis expose
return, thrown, alias, and allocation/escape facts for one concrete specialization. These facts are
language bindings to a shared model; they do not justify parallel language-specific semantic IRs.

Primary references:

- https://llvm.org/docs/LangRef.html#function-attributes
- https://llvm.org/docs/MemorySSA.html
- https://llvm.org/devmtg/2019-10/slides/Bram-Adve-The-Attributor.pdf
- https://github.com/AliveToolkit/alive2
- https://rustc-dev-guide.rust-lang.org/mir/drop-elaboration.html
- https://ziglang.org/documentation/master/#defer
- https://docs.julialang.org/en/v1/devdocs/EscapeAnalysis/

## Architecture

### EffectFootprint

`EffectFootprint` is a finite product lattice. It records read/write memory regions and boolean
effects for allocation, deallocation, cleanup, unwind, synchronization, atomics, volatile access,
publication, invalidation, external I/O, callbacks, nondeterminism, and nontermination. Joining two
footprints is set union and boolean disjunction. The lattice is deliberately not an implementation
grammar.

### CallRelation

A call relation binds one callsite to either:

- an intrinsic or modeled primitive,
- a definition-visible function summary,
- a finite-target dispatch set,
- a declared protocol envelope, or
- an opaque external boundary.

It records argument ownership, result channels, preconditions, postconditions, effect footprint,
proof method, and authority. Transformations may cross a call only when the relation is functional
and its proof permits crossing. Call-preserving candidates need only retain the relation and its
selected-build identity.

### FunctionSummary And SystemFlowGraph

Each function summary contains its local `SemanticFlowGraph`, direct call relations, local and
transitive effects, protocol obligations, source/compiler identities, and closure class. The system
graph connects summaries by concrete callsites. A deterministic SCC algorithm computes recursive
components, and monotone joins reach a bounded fixpoint. Unknown targets remain boundary nodes;
they do not poison unrelated components.

### Protocol Envelopes

Protocol envelopes are finite semantic descriptors, not search dimensions. Initial envelopes are:

- borrowed contiguous view,
- bounded no-growth append with trivial element lifetime,
- aggregate result projection,
- tagged multi-exit result,
- trivial cleanup,
- scoped allocation and retirement,
- versioned single-writer publication.

Each envelope declares applicability guards, effects, transitions, proof obligations, and whether
a transformation may cross it. Language adapters map native constructs to these descriptors.

## Search-Space Discipline

The implementation grammar continues to enumerate only transformations supported by attribution:
maps, reductions, scans, compaction, codecs, state transitions, layout, scheduling, and other
registered families. System closure performs three operations before search:

1. reject candidates that violate composed effects or protocol envelopes;
2. identify closed subgraphs where existing grammars may run; and
3. emit proof obligations for candidate integration.

No protocol summary introduces a candidate choice unless an independently attributed grammar rule
explicitly consumes it. Search complexity is therefore bounded by the selected computational
regions and grammar, not by the number of summarized calls in the application.

## Language Bindings

### C And C++

Map LLVM memory effects and function attributes, aggregate ABI channels, direct definitions,
no-growth contiguous containers, trivial destruction, exceptional exits, atomics, volatile
operations, and explicit allocation to shared descriptors. Virtual or indirect calls close only
when the target set is finite and build-bound.

### Rust

Map references and slices to borrowed views; MIR `Drop`, cleanup blocks, panic paths, allocation,
atomics, FFI, trait dispatch, and async state machines to shared effects and protocols. A no-growth
`Vec` projection requires a dominating capacity guard and trivial element drop behavior.

### Zig

Map slices to borrowed views; error returns to tagged exits; `defer`/`errdefer` to cleanup; allocator
operations to scoped ownership; optionals and tagged unions to aggregate/tagged results; atomics,
volatile, async, and FFI to shared effects.

### Julia

Map one concrete typed specialization and world to a function summary. Typed SSA escape, thrown
escape, allocation, bounds-error paths, mutable globals, tasks, atomics, and `ccall` bind to shared
effects. Isbits aggregates may close as aggregate channels; GC-visible ownership and future world
states remain explicit scopes.

## Proof Model

- Alive2 proves local LLVM refinement only.
- Z3 proves bounded aggregate, exit, capacity, state, and summary-composition obligations.
- Definition hashes and compiler identities bind exact call-preserving helpers.
- Crossing a helper requires inlining or a functional relation proof.
- Stateful publication/retirement uses the protocol verifier or a stronger model checker.
- Differential and application tests remain required for production promotion.

## Failure Semantics

Opaque boundaries are verbose and local. Each reports its callsite, native construct, missing
contract, affected effect dimensions, excluded claim, and actionable adapter or protocol workflow.
The containing system may still have closed subgraphs and may continue attribution, synthesis, and
proof there.
