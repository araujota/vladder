## ADDED Requirements

### Requirement: Six Operator Grammar Families

SiliconTune SHALL provide explicit fusion, layout, reduction, control-flow,
schedule, and specialization rule families.

#### Scenario: Rule audit

- **GIVEN** an emitted candidate
- **WHEN** its audit is inspected
- **THEN** every graph mutation names a versioned rule, preconditions, proof
  obligation, and cost annotation.

### Requirement: Fusion Legality

Fusion SHALL preserve observers, dependence order, alias semantics, numerical
policy, exceptions, and side effects.

#### Scenario: Eliminate private intermediate

- **GIVEN** a single-producer/single-consumer temporary with no external observer
- **WHEN** producer-consumer fusion applies
- **THEN** the temporary materialization is removed
- **AND** data and ordering dependencies remain represented.

#### Scenario: Reject reassociation

- **GIVEN** an exact floating-point contract
- **WHEN** a reduction rule changes operation association
- **THEN** the candidate is rejected unless bitwise equivalence is proved.

### Requirement: Layout Ownership

Layout changes SHALL transform all consumers in the owned region or emit a
verified boundary adapter.

#### Scenario: AoS to SoA boundary

- **GIVEN** an AoS input owned by an external caller
- **WHEN** an internal SoA candidate is selected
- **THEN** adapter traffic and latency are included in the measured candidate.

### Requirement: Guarded Specialization

Specialized candidates SHALL carry a checked guard or deployment precondition.

#### Scenario: Common message fast path

- **GIVEN** an add-message specialization
- **WHEN** a modify message arrives
- **THEN** checked dispatch transfers control to a verified general path.
