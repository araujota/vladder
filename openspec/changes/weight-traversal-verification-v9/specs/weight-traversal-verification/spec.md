## ADDED Requirements

### Requirement: Sequence-State Equivalence

Candidate schedules SHALL produce the same prompt and decode completion state for every request.

#### Scenario: Reorder independent ready sequences

- **GIVEN** identical request traces and different legal schedules
- **WHEN** both simulations complete
- **THEN** every sequence has identical completed work despite different timestamps.

### Requirement: Speculation Fails Closed

Tentative token lanes SHALL remain illegal until commit, rollback, accepted-prefix, KV-state,
and generated-output verification are implemented.

#### Scenario: Speculation is present only in the graph vocabulary

- **GIVEN** the V9 exact manifest disables speculation
- **WHEN** search considers a speculative plan
- **THEN** the plan is rejected and no semantic claim is made.
