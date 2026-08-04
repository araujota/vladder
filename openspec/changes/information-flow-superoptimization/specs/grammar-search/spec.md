## ADDED Requirements

### Requirement: Explicit Transformation Grammar

SiliconTune SHALL generate candidates from named grammar rules over canonical
graphs.

Each rule SHALL declare:

- input pattern
- output pattern
- preconditions
- proof obligation
- cost annotations if available

#### Scenario: Clamp grammar

- **GIVEN** a canonical saturating projection graph
- **WHEN** grammar search runs
- **THEN** it explores branch, select, min/max, mask/blend, and vector-lane
  realizations allowed by the target and proof policy.

### Requirement: Bounded Optimality

Search SHALL distinguish saturated optimality from best-found results.

#### Scenario: Budget exhausted

- **GIVEN** an e-graph search that reaches node or time budget before saturation
- **WHEN** extraction selects a winner
- **THEN** the report marks the result `best_found`
- **AND** records the search budget.
