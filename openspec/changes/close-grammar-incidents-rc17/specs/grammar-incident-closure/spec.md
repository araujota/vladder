# Grammar Incident Closure

## ADDED Requirements

### Requirement: Syntax-directed SPIR-V capture

The system SHALL derive opcodes only from valid instruction positions and SHALL attach result type,
operands, validity conditions, numeric policy, and provenance to every supported operation.

#### Scenario: Debug name begins with Op

- **WHEN** a module contains an `OpName` string such as `OpacityMap`
- **THEN** that string is not classified as an instruction

### Requirement: Exact SPIR-V core vocabulary

The system SHALL represent scalar/vector logical operations, unsigned division/remainder, dot,
matrix-vector, image, and cooperative-matrix operations with their declared semantic restrictions.

#### Scenario: Dynamic unsigned divisor

- **WHEN** a candidate changes an unsigned divide or remainder
- **THEN** the divisor-validity domain is preserved or proved by a guard

### Requirement: Recursive compositional C++ summaries

Definition-visible recursive and mutually recursive calls SHALL converge through a finite SCC
effect fixpoint and SHALL NOT be classified as external solely because they are recursive.

#### Scenario: Recursive helper with no external effects

- **WHEN** a finite recursive component only accesses declared argument memory
- **THEN** it closes as a recursive call-preserving component

### Requirement: Parametric C++ ownership and cleanup

The system SHALL represent container state, initialized element lifetime, allocation ownership,
normal/exceptional outcomes, cleanup order, and retirement for supported bounded C++ protocols.

#### Scenario: Capacity-preserving append

- **WHEN** capacity dominates append count and element operations satisfy the declared exception
  contract
- **THEN** the wrapper exposes a proved borrowed mutation region and exact normal/failure outcomes

### Requirement: Aggregate and object-state channels

The system SHALL bind source fields or compiled offset projections to register, `sret`, and `this`
state channels and SHALL express old-state/new-state relations for member functions.

#### Scenario: Member field update

- **WHEN** a method mutates a finite set of object fields
- **THEN** the graph identifies those fields or offsets and leaves all other object state preserved

### Requirement: Finite protocol traces

The system SHALL verify declared finite resource state, effects, failure outcomes, happens-before,
publication, rollback, and retirement without claiming external implementation equivalence.

#### Scenario: Opaque driver operation

- **WHEN** orchestration is valid against a declared API protocol
- **THEN** local orchestration may close while driver execution remains an excluded physical claim

### Requirement: Structured deep archetypes

The system SHALL recognize structured sparse, parse/materialize, cache-patch,
partition/prefix/scatter, state-transition, traversal-fusion, and realization-lifetime regions and
SHALL distinguish executable lowerer routes from hypotheses.

#### Scenario: No executable route

- **WHEN** an archetype is recognized but no native emitter and proof strategy exist
- **THEN** it is reported as a hypothesis and does not increment executable candidate count

### Requirement: Bounded artifact identities

Generated path components SHALL remain within the configured byte limit while preserving full
identity and collision detection in their manifests.

#### Scenario: Long C++ symbol

- **WHEN** a mangled symbol exceeds the platform filename limit
- **THEN** every proof artifact is emitted using a bounded prefix and stable hash

### Requirement: No-write application acceptance

Application acceptance SHALL record revision, status hash, and content identity before and after
and SHALL fail if any source-controlled file changes.

#### Scenario: Read-only corpus evaluation

- **WHEN** the NeuralFusion acceptance corpus is inspected
- **THEN** its revision and complete pre-existing worktree status remain unchanged
