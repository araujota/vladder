## ADDED Requirements

### Requirement: Bounded Exhaustive Enumeration

The system SHALL enumerate the complete declared V9 cross-product before legality and
dominance filtering and SHALL report counts at every stage.

#### Scenario: Search the default grammar

- **GIVEN** the V9 manifest choices
- **WHEN** search executes
- **THEN** 3,840 raw combinations and all rejection reasons are auditable.

### Requirement: Ready-Lane Legality

The system SHALL NOT batch future tokens from one autoregressive sequence unless an enabled
verification protocol supplies tentative lanes.

#### Scenario: Request a four-token decode tile without speculation

- **GIVEN** one active sequence and speculation disabled
- **WHEN** legality is evaluated
- **THEN** the plan is rejected before compilation or measurement.
