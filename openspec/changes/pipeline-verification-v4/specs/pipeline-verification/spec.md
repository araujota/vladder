## ADDED Requirements

### Requirement: Pipeline Refinement

An admitted realization SHALL refine the pipeline contract at every external observer
and preserve declared state transitions, footprints, ordering, and ownership.

#### Scenario: Eliminated intermediate

- **GIVEN** a temporary is changed from materialized to streamed
- **WHEN** structural verification runs
- **THEN** all consumers are dominated by its producer realization
- **AND** no external observer, alias, or lifetime depends on its storage identity.

### Requirement: Composed Numerical Contract

Numerical verification SHALL propagate local error and reassociation classes into a
pipeline output budget rather than checking each operator independently.

#### Scenario: Multiple tolerance-bounded children

- **GIVEN** two transformed floating-point operators
- **WHEN** their errors compose
- **THEN** the final adversarial and long-run bound must satisfy the pipeline contract.

### Requirement: Deterministic Sampling Boundary

Exact sampling contracts SHALL preserve logits at the sampling observer, selected
tokens, RNG state, and random-value consumption order.

#### Scenario: Equivalent token with changed RNG state

- **GIVEN** a candidate selects the same token but consumes a different RNG count
- **WHEN** exact sequence verification runs
- **THEN** the candidate is rejected.
