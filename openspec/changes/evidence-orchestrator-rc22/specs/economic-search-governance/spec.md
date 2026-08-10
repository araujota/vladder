## ADDED Requirements

### Requirement: Prospective grammar query
The system SHALL expose recognized semantic patterns, supported and plan-only grammar families,
unsupported semantics, proof requirements, and expected workflow cost before optimization.

#### Scenario: Unsupported external protocol
- **WHEN** a symbol's dominant behavior is an unmodeled external protocol
- **THEN** `can-optimize` reports locally closable subregions separately
- **AND** recommends `ESCALATE` for the protocol boundary without blocking local work

### Requirement: Economic stopping rule
The system SHALL compare expected composed value, workflow cost, remaining closure cost, runtime
share, and grammar coverage before recommending further work.

#### Scenario: Verified measured regression after broad coverage
- **WHEN** all declared relevant families were evaluated and the baseline remains best
- **THEN** the recommendation is `STOP`
- **AND** the result is retained as a grammar-exhausted negative training observation

### Requirement: Forecast authority
Forecasts and learned-prior outputs SHALL remain advisory and SHALL never authorize legality,
equivalence, benchmark acceptance, or source promotion.

#### Scenario: High predicted win
- **WHEN** the forecast predicts a high-value candidate
- **THEN** every ordinary proof, differential, physical, and integration gate still executes
