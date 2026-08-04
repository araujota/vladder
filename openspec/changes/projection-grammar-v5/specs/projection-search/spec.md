## ADDED Requirements

### Requirement: Hierarchical Projection Search

SiliconTune SHALL search projection realization choices hierarchically and preserve
the unsaturated status of every child region.

#### Scenario: Shared preparation candidate

- **GIVEN** two or more projections sharing an F32 activation
- **WHEN** activation preparation search runs
- **THEN** independent and prepare-once realizations are costed
- **AND** preparation cost and scratch lifetime remain in the result.

### Requirement: Guarded Regime Dispatch

Every regime-specific candidate SHALL carry checked token, sequence, phase, context,
ISA, alignment, KV occupancy, and quantization guards that it relies upon.

#### Scenario: Token tile four

- **GIVEN** a candidate requiring four activations
- **WHEN** fewer than four are available
- **THEN** dispatch selects a legal fallback.
