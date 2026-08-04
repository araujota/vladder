## ADDED Requirements

### Requirement: Reconstruction Before Search

Production grammar search SHALL remain disabled until the regenerated baseline passes E1
and is no more than 3% slower at p50, with a 95% interval that does not permit worse than
5% regression.

#### Scenario: Slow regenerated baseline

- **GIVEN** a semantically correct regenerated kernel more than 5% slower than native
- **WHEN** synthesis is requested
- **THEN** SiliconTune rejects the request and requires attribution first.

### Requirement: Model-Level Baseline Validation

The regenerated baseline SHALL execute through the pinned model with confirmed runtime
binding and deterministic generated-output identity.

#### Scenario: Override not selected

- **GIVEN** a preload artifact that does not bind the active GEMV symbol
- **WHEN** model verification runs
- **THEN** verification fails even if native and candidate text happen to match.
