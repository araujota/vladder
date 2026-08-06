# Compositional Semantic Closure

## ADDED Requirements

### Requirement: Language-neutral effect lattice

The system SHALL represent memory-region access, ownership, cleanup, exceptional exit,
synchronization, external I/O, callback, publication, and nondeterminism effects in one finite
language-neutral lattice.

#### Scenario: Equivalent native effects

- **WHEN** C++, Rust, Zig, and Julia constructs have equivalent semantic effects
- **THEN** they map to the same effect footprint
- **AND** native syntax remains provenance or a language binding

### Requirement: Compositional direct-call closure

The system SHALL compose definition-visible and declared call relations into deterministic
function summaries and SHALL reach a bounded monotone fixpoint over recursive components.

#### Scenario: Pure helper chain

- **WHEN** a selected function calls a chain of definition-visible nonallocating helpers
- **THEN** the system graph reports the component as locally closed
- **AND** every helper identity and transitive effect is hash-bound

### Requirement: Local opaque boundaries

Unknown callbacks, unbounded indirect dispatch, and undeclared third-party protocols SHALL remain
explicit local boundaries and SHALL NOT block independently closed subgraphs.

#### Scenario: Closed computation before external submission

- **WHEN** a function contains a closed data transformation followed by an opaque driver call
- **THEN** the data transformation remains eligible for ordinary synthesis and proof
- **AND** the driver call is reported as an external protocol boundary

### Requirement: Protocol envelopes do not expand candidate search

Ownership and runtime summaries SHALL be legality and proof descriptors. They SHALL NOT become
candidate dimensions unless an attributed implementation grammar explicitly references them.

#### Scenario: Many summarized calls

- **WHEN** a system graph contains multiple modeled ownership and cleanup calls around one
  computational region
- **THEN** the candidate count equals the count produced for the computational region alone

### Requirement: Finite ownership closure

The system SHALL support borrowed contiguous views, bounded no-growth append, aggregate results,
tagged exits, trivial cleanup, scoped allocation, and versioned publication through explicit
guards and proof obligations.

#### Scenario: Checked no-growth append

- **WHEN** spare capacity dominates every append, element destruction is trivial, the local region
  cannot throw, and aliases are declared
- **THEN** the append region closes under the no-growth protocol envelope

### Requirement: Honest interprocedural proof scope

The system SHALL distinguish call-preserving summary closure from transformations that cross a
call. It SHALL NOT describe Alive2 evidence as interprocedural proof.

#### Scenario: Rewrite crosses helper boundary

- **WHEN** a candidate changes values or control across a helper call
- **THEN** promotion requires helper inlining or a functional relation proof in addition to local
  LLVM refinement

### Requirement: Shared multilingual bindings

C/C++, Rust, Zig, and Julia frontends SHALL bind native ownership, cleanup, result, dispatch, and
runtime facts to the shared closure model and SHALL emit named residual boundaries for facts that
cannot be proven.

#### Scenario: Necessary arbitrary boundary

- **WHEN** a selected region invokes an arbitrary callback or undeclared third-party API
- **THEN** the report identifies the exact callsite, missing contract, excluded claim, and next
  adapter action without declaring the whole workflow unsupported
