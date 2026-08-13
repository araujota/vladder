# Canonical-State Search Requirements

## ADDED Requirements

### Requirement: Canonical states are authoritative

Search SHALL recursively expand a unique canonical semantic state at most once while retaining every
transformation edge and path that reaches it.

#### Scenario: Commutative paths converge

- **GIVEN** two legal action orders produce byte-identical canonical semantic states
- **WHEN** the second order is generated
- **THEN** one DAG node records both parent edges and only one recursive expansion occurs.

### Requirement: Hashes are indexes, not proof

Digest equality SHALL be followed by canonical-byte and semantic-envelope comparison.

#### Scenario: Forced hash collision

- **GIVEN** two distinct canonical serializations share a test digest
- **WHEN** both enter the transposition table
- **THEN** two unique state records remain.

### Requirement: Canonicalization preserves legality

Canonicalization SHALL retain observable order, aliases, ownership, synchronization, memory spaces,
atomic/volatile behavior, types, precision, external state, and hardware constraints.

#### Scenario: Distinct atomic semantics

- **GIVEN** otherwise identical states with atomic and non-atomic stores
- **WHEN** canonicalized
- **THEN** their identities differ.

### Requirement: Independence fails open

Actions SHALL be considered independent only after conservative footprint screening and state-scoped
AB/BA canonical equality; unknown relationships SHALL remain dependent.

#### Scenario: Shared contract

- **GIVEN** actions over disjoint owners that mutate one contract
- **WHEN** independence is evaluated
- **THEN** the pair remains dependent unless stronger verification succeeds.

### Requirement: POR preserves terminal states

Every enabled production POR rule SHALL preserve exactly the full canonical terminal-state set on all
qualification fixtures.

#### Scenario: Sleep-set qualification

- **GIVEN** a bounded grammar with verified-independent actions
- **WHEN** full canonical and sleep-set searches finish
- **THEN** canonical terminal bytes are identical and skipped orderings are reported separately.

### Requirement: Symmetry is explicit

Alpha and automorphism reduction SHALL rename only identities declared non-observable or members of an
explicitly interchangeable semantic class.

#### Scenario: Observable lane identity

- **GIVEN** two lanes whose indices are externally visible
- **WHEN** symmetry canonicalization runs
- **THEN** they are not interchangeable.

### Requirement: Dominance and macros are proof gated

Structural cost SHALL NOT authorize deletion. Dominance requires descendant-set inclusion and a macro
requires descendant-set equality for the qualified grammar envelope.

#### Scenario: Cheap state enables no future superset

- **GIVEN** a state with fewer materializations but a missing legal descendant
- **WHEN** dominance qualification compares descendant sets
- **THEN** the proposal is rejected with the missing terminal as counterexample.

### Requirement: Reduction attribution is non-overlapping

Every run SHALL report raw states, canonical transpositions, alpha/symmetry collapses, POR transitions,
dominance, macros, e-graph equivalences, calls, wall time, memory, and terminal states independently.

#### Scenario: Combined reduced search

- **GIVEN** canonicalization and POR both recognize one redundant path
- **WHEN** the waterfall is emitted
- **THEN** the path is attributed to the first mechanism that removed it and is counted once.

### Requirement: ML is ordering only

Learned policy SHALL NOT remove states in exhaustive canonical or exhaustive reduced modes.

#### Scenario: Lowest-scored branch

- **GIVEN** no deterministic or formally qualified reduction applies
- **WHEN** exhaustive reduced search runs
- **THEN** the lowest-scored branch remains reachable and is eventually expanded.
