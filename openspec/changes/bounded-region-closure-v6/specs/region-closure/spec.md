## ADDED Requirements

### Requirement: Shared bounded region closure graph

The system SHALL represent typed live-ins, scalar or aggregate live-outs, ordinary exit channels,
helper relations, and bounded ownership projections in one language-neutral semantic graph.

#### Scenario: C++ aggregate with early status return

- **WHEN** a selected no-unwind local C++ function returns a compiler-modeled aggregate through
  registers or `sret` and has multiple ordinary returns
- **THEN** the report contains ordered aggregate projections and a tagged `ExitMerge`
- **AND** the graph binds the selected source, compiler, symbol, and lowered ABI

### Requirement: Honest first-order C ABI classification

The standalone C frontend SHALL distinguish a modeled noncanonical ABI from an unmodeled ABI.

#### Scenario: Scalar checksum result

- **WHEN** a C function returns a fixed-width scalar and accepts a borrowed byte pointer plus extent
- **THEN** its ABI is classified as closed
- **AND** absence of an executable semantic family is reported as a grammar gap rather than an ABI gap

### Requirement: Bounded ordinary multi-exit lowering

The C++ frontend SHALL model ordinary local returns as explicit exit tags and live-outs without
changing return semantics through lambda extraction.

#### Scenario: Search loop returning the first matching index

- **WHEN** a no-unwind local loop returns from its enclosing function and no cleanup or protocol
  transition crosses the exit
- **THEN** the loop is isolated at the whole-function CFG boundary
- **AND** schedule candidates preserve the source return statements

#### Scenario: Unstructured or cleanup-crossing exit

- **WHEN** a region contains `goto`, coroutine transfer, exception unwind, or nontrivial cleanup
- **THEN** automatic multi-exit lowering is rejected with the specific remaining protocol

### Requirement: Exact helper-summary closure

The system SHALL admit only inlined helpers or direct definition-visible recursively local helpers
as generic helper relations.

#### Scenario: Direct no-unwind helper

- **WHEN** a selected loop calls a definition-visible helper whose transitive effects are local
- **THEN** call-preserving candidates may use an exact build-bound helper summary
- **AND** transformations crossing the call require inlined IR or a separate functional proof

#### Scenario: Indirect callback

- **WHEN** a helper target is indirect, virtual, external, or retains unmodeled effects
- **THEN** the call remains an external protocol boundary

### Requirement: No-growth ownership projection

The system SHALL admit bounded container output only under a dominating capacity guard, trivial
element lifetime, nonthrowing local execution, and unchanged allocation ownership.

#### Scenario: Guarded trivial vector append

- **WHEN** a C++ region proves sufficient spare capacity before appending bounded trivial values
- **THEN** the region is represented as `OwnershipGuard` plus `Append`
- **AND** Z3 proves the capacity inequality while the owning wrapper remains outside local proof

#### Scenario: Reallocation or nontrivial element

- **WHEN** spare capacity is not established or appended elements have nontrivial lifetime
- **THEN** the region requires an ownership/capacity adapter

### Requirement: Proof and promotion separation

The system SHALL keep representation closure separate from candidate refinement and physical
promotion.

#### Scenario: Closure proof passes

- **WHEN** aggregate, exit-selector, helper-binding, or no-growth obligations pass
- **THEN** the report claims only bounded closure
- **AND** each transformed candidate still requires applicable Alive2, differential, project, and
  benchmark evidence before promotion
