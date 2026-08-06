# Design

## Resolution Model

Clang ASTs provide source-level identity, type, ownership, and control-flow facts for one concrete
compilation command. Object symbol tables provide the definitions and references selected by the
build. LLVM IR provides executable effects and direct call edges. No one representation is
sufficient alone, so RC18 binds all three through source, command, compiler, object, body, and
summary hashes.

## WholeBuildIndex

`WholeBuildIndex` parses every compilation database entry, resolves its source and output object,
and indexes defined and undefined mangled symbols with `llvm-nm`. Strong definitions resolve only
when unique. Multiple weak/ODR definitions remain ambiguous until their materialized normalized
body hashes agree. Missing object files remain indexed translation units with a diagnostic rather
than silently disappearing.

## CrossTUSummaryDatabase

`CrossTUSummaryDatabase` is a content-addressed, persistent summary store. It emits analysis LLVM
IR for a translation unit only when a selected slice needs a definition. The exact production
flags are retained while output/dependency flags are removed and analysis-only no-inline and
no-vectorization controls are added. Each defined function receives a local effect/call summary.
Calls previously marked opaque are upgraded to definition edges only when the whole-build index
resolves a unique project definition.

## BidirectionalProgramSlice

The slice starts from one or more mangled seed symbols. Downstream expansion follows resolved
direct calls. Upstream expansion follows materialized caller edges and object-level references,
materializing only candidate translation units within explicit depth and node budgets. The slice
records unresolved, indirect, protocol, and ambiguous-definition boundaries. It is a proof and
optimization scope, not a claim of whole-program closure.

## OwnershipClosureGraph

Ownership closure is a separate graph over functions and resources. It records construct,
borrow/read, mutate, publish, transfer, invalidate, retire, and unknown-boundary edges derived from
effect summaries and declared contracts. A resource is locally closed only when ownership,
publication, and retirement are represented inside the slice or terminated at an explicit
contract boundary.

## SummaryCompositionProof

The proof layer reuses deterministic effect-summary fixed points and adds finite obligations for:

- unique or equivalent-ODR definition resolution;
- source/command/compiler/object/body hash provenance;
- total disposition of every slice edge;
- transitive effect containment;
- ownership retirement or explicit boundary;
- candidate-count separation between semantic summaries and implementation grammar.

The proof establishes compositional closure for the selected slice. It does not prove functional
equivalence across call boundaries unless a local functional/refinement proof is also supplied.

## Search-Space Discipline

Indexing and summary composition introduce zero candidate dimensions. Slice expansion is bounded
by upstream depth, downstream depth, and node count. Only attributed closed regions are sent to
the existing implementation grammar. External boundaries constrain legality and remain
call-preserving.

## Research Basis

- Clang LibTooling compilation databases and AST import facilities.
- LLVM ThinLTO combined summary indexes for cross-module function discovery.
- LLVM MemorySSA and alias analysis for memory-effect reasoning.
- Linker symbol resolution and C++ ODR constraints for definition identity.

