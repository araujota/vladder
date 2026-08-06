# Design

## Incident Validation

The release corpus reproduces 69 C++ closures with 55 helper, 51 ownership, 46 cleanup, 22 ABI,
and five concurrency boundaries. It also reproduces incomplete capture for the reported SPIR-V
operations. Disassembly parsing additionally mistakes debug or source names beginning with `Op`
for opcodes; instruction parsing must be syntax-directed.

## SPIR-V Semantic Layer

`SpirvSemanticModule` parses result IDs, result types, operands, type declarations, constants,
capabilities, decorations, execution modes, and instruction provenance from real instruction
positions. An exact operation registry supplies semantic class, type rules, validity domain,
numeric policy, and candidate families. Dynamic unsigned divisors remain legal source semantics but
emit a non-zero-domain obligation for transformations that change division. Floating dot and
matrix operations retain declared contraction and rounding policy. Image and cooperative-matrix
instructions require their descriptor/capability contracts; recognition alone does not prove
external sampler state or hardware execution.

## C++ Semantic Protocols

`CppContainerState` records data identity, size, capacity, allocator identity, initialized range,
and element lifetime. `CppOutcomeTrace` records normal/exception/terminate outcome, committed
fields, cleanup order, allocation ownership, synchronization, and externally visible effects.
Known standard operations map to parametric descriptors derived from the selected ABI and compiled
calls. These summaries remove false `external_io` classifications but remain call-preserving unless
a functional relation is proved.

Definition-visible calls are summarized by a finite SCC fixpoint. Recursion is a graph edge, not an
external call. Aggregate and member state are projected by source fields where available and LLVM
offset channels otherwise. Exceptional CFGs preserve `invoke` normal/unwind successors,
landingpads/funclets, cleanup calls, resume, and terminate paths.

## Finite Protocol DSL

The shared DSL contains resources, finite states, transitions, preconditions, effects, outcomes,
linearization events, happens-before edges, and retirement rules. The verifier proves declared
transition legality, resource lifetime, publication visibility, rollback, and terminal behavior
with bounded Z3 traces. API-specific bindings instantiate the DSL; they do not introduce a second
semantic vocabulary or claim equivalence of external implementations.

## Structured Deep Dataflow

The deep classifier consumes SemanticFlowGraph nodes, effects, protocols, and compiled instruction
features. It recognizes structured archetypes and routes executable instances to existing bounded
dataflow/lifetime/state lowerers. Regions lacking an emitter remain explicit hypotheses and cannot
be counted as generated candidates. Candidate cardinality is attributable and bounded per matched
region.

## Artifact Identity

Every generated filename uses `<kind>-<bounded-prefix>-<sha256-prefix>.<suffix>`, stays below a
conservative 180-byte component limit, and stores the full identity inside a manifest. Hashes bind
the untruncated identity so collisions fail closed.

## Proof Boundaries

- Z3 proves finite operation, capacity, state, cleanup-trace, protocol, and summary obligations.
- Alive2 remains local LLVM refinement and does not prove owning wrappers or external protocols.
- SPIR-V structural validation is not output equivalence.
- Application differential runners and physical timestamps remain mandatory for promotion.

## Research Basis

- Khronos SPIR-V unified specification and machine-readable grammar.
- LLVM exception handling, LangRef, MemorySSA, and Attributor fixpoint model.
- C++ object lifetime, vector capacity/invalidation, exception cleanup, and memory-model clauses.
- Vulkan resource lifetime and synchronization specifications as one protocol binding example.

