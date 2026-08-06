# Compositional Semantic Closure V1

## Why

vLadder can capture useful local C, C++, Rust, Zig, and Julia regions, but its closure model is
primarily function-local. A definition-visible helper is either retained exactly or treated as an
external boundary; ownership, cleanup, exceptional exits, synchronization, and runtime services
are usually collapsed into one adapter requirement. This prevents closed computational subgraphs
from being composed into systems of functions even when every call has a finite, checkable effect
summary.

Expanding the implementation grammar to enumerate protocol behavior would be unsound and would
multiply the search space. The missing capability is instead a compositional semantic layer that
summarizes calls and ownership protocols once, proves those summaries independently, and uses them
as legality constraints around ordinary bounded candidate search.

## What Changes

- Add a language-neutral effect and call-relation lattice over memory regions, allocation,
  cleanup, exceptional exit, synchronization, publication, external I/O, callbacks, and
  nondeterminism.
- Add deterministic function summaries and a `SystemFlowGraph` that composes direct calls through
  strongly connected components and bounded fixpoint analysis.
- Add finite protocol envelopes for borrowed views, bounded no-growth append, aggregate results,
  tagged exits, trivial cleanup, explicit allocation scopes, and versioned publication.
- Bind C/C++ LLVM attributes, Rust MIR ownership/drop facts, Zig error/defer/allocator facts, and
  Julia typed-SSA escape/allocation facts to the same semantic vocabulary.
- Keep opaque callbacks, indirect calls without a closed target set, third-party APIs without a
  declared contract, and externally observable protocols as explicit boundaries while preserving
  independently closed subgraphs.
- Add a system-closure CLI that emits one boundary matrix, graph, proof-obligation set, and next
  action without generating implementation candidates.

## Non-Goals

- Whole-program equivalence for arbitrary C++/Rust/Zig/Julia applications.
- Inferring contracts for arbitrary callbacks or third-party APIs.
- Treating Alive2 as an interprocedural verifier.
- Enumerating ownership or protocol states as implementation candidates.
- Optimizing external I/O, driver, scheduler, or runtime behavior without a dedicated physical
  protocol workflow.
