## ADDED Requirements

### Requirement: Fail-Closed V8 Entry

V8 SHALL require passing V7 capture, semantic reconstruction, and performance-parity
artifacts and SHALL reject changed source, model, hardware, active path, or assembly shape.

#### Scenario: Drifted production baseline

- **GIVEN** a model or kernel hash differing from the active-path manifest
- **WHEN** decomposition starts
- **THEN** no diagnostic measurement is accepted.

### Requirement: Attribution-Only Claim Boundary

The workflow SHALL make no faster-kernel or tokens-per-second claim unless an optional
candidate passes the separate V8 promotion gate.

#### Scenario: Attribution completes without a candidate

- **GIVEN** all physical gates pass and a next grammar is selected
- **WHEN** no candidate study is run
- **THEN** V8 reports physical evidence and the bounded next experiment only.
