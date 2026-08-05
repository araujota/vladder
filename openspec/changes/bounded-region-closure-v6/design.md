# Design

## Research Basis

LLVM represents aggregate values with first-class aggregate operations or ABI-selected output
storage, and represents control merge through CFG edges and phi/select values. The Itanium C++ ABI
distinguishes trivial register-passed aggregates from nontrivial indirect results. Clang's semantic
AST retains written return, record, template, and member structure. The C++ container contract makes
reallocation and invalidation observable, so only a proved no-growth projection can be treated as a
borrowed bounded output.

## Decisions

### Shared closure vocabulary

`RegionClosureGraph` uses the existing SemanticFlowGraph vocabulary plus `AggregatePack`,
`AggregateUnpack`, `ExitMerge`, `HelperSummary`, `OwnershipGuard`, and `Append`. Language syntax is
provenance, not a second semantic ontology.

### Aggregate results

Trivial register aggregates and compiler-lowered `sret` results become ordered output projections.
The graph binds the exact lowered signature and field indices. This closes representation, not class
invariants, pointer-target lifetime, or nontrivial copy/destruction.

### Multi-exit regions

Local `return` exits become `(exit_tag, result_projection...)` channels. A region is transformable
only when all exits are ordinary returns, the enclosing function is local-effect and no-unwind, and
no cleanup, synchronization, indirect call, or ownership transition crosses an exit. Source
scheduling candidates are emitted at the whole-function boundary so a lambda cannot change return
semantics.

### Helper summaries

A direct definition-visible helper with recursively local effects receives an exact body hash,
lowered signature, memory-effect summary, and call graph. Call-preserving rewrites may use this
summary as an opaque relation. Rewrites across the helper require compiler inlining or a separately
proved functional summary. External, virtual, and indirect helpers remain protocol boundaries.

### Ownership projection

`std::vector` append is admitted only as a borrowed output projection when a dominating source guard
establishes sufficient spare capacity, the function/region is nonthrowing, elements are bounded
trivial values, and no operation changes allocator or ownership state. The lowerer preserves the
container operation; it does not synthesize access to vector internals. Reallocation, allocation
failure, nontrivial construction/destruction, and escaped iterators remain outside local closure.

### C ABI capture

The standalone C frontend distinguishes an unmodeled ABI from a modeled ABI with no executable
grammar. Scalar returns, fixed-width scalar parameters, and borrowed pointer/extent boundaries are
captured even when they are not the legacy float-transform shape. This prevents an ABI diagnostic
from hiding the actual missing grammar.

## Proof Envelope

- Z3 proves aggregate projection identity, exit-selector completeness, and no-growth capacity.
- Alive2 proves each generated local or whole-function LLVM refinement where applicable.
- Exact definition hashes bind helper summaries; they are not mislabeled as functional proofs.
- Differential execution remains required for result fields, every exit, capacity failure, and
  state/output observables.
- Project tests remain required for owning wrappers and external protocols.

## Explicit Boundaries

Arbitrary RAII, exception unwinding, allocator replacement, indirect or virtual calls, concurrency,
device APIs, syscalls, and external state cannot be inferred from local LLVM alone. The report names
these boundaries while allowing closed subregions and other vLadder workflows to continue.
