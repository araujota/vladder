## ADDED Requirements

### Requirement: Tiered Proof Policy

SiliconTune SHALL attach proof status to every candidate.

Allowed statuses:

- `proved`
- `bounded`
- `tested`
- `timeout`
- `oom`
- `unsupported`
- `failed`

#### Scenario: Z3 schema proof

- **GIVEN** an exact scalar rewrite schema
- **WHEN** Z3 proves no counterexample exists
- **THEN** the candidate proof status is `proved`.

#### Scenario: Alive2 timeout

- **GIVEN** Alive2 exceeds the configured budget
- **WHEN** the candidate report is written
- **THEN** Alive2 status is `timeout`
- **AND** the candidate is not falsely reported as Alive2-proved.

### Requirement: Differential Runtime Guard

Every candidate admitted to benchmarking SHALL pass deterministic differential
testing against the reference implementation.

#### Scenario: Runtime mismatch

- **GIVEN** a candidate that differs from the reference on an edge-size or deterministic randomized input
- **WHEN** the differential harness runs
- **THEN** the candidate is marked `failed`
- **AND** it is excluded from ranking and patch generation.
