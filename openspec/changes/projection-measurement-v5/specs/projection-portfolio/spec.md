## ADDED Requirements

### Requirement: Projection Substage Attribution

SiliconTune SHALL report only independently observable projection substages and label
fused regions that cannot be decomposed without additional instrumentation.

#### Scenario: Q4_K native dot kernel

- **GIVEN** activation conversion followed by a fused Q4_K/Q8_K vector dot
- **WHEN** profiling runs
- **THEN** conversion, synchronization, and fused decode/dot time are separate
- **AND** weight load, unpack, and accumulation are not falsely reported as independent.

### Requirement: Portfolio Ranking

Candidates SHALL be ranked by a declared workload portfolio with per-workload floors.

#### Scenario: Aggregate gain with interactive regression

- **GIVEN** a positive weighted score and a violated interactive floor
- **WHEN** ranking runs
- **THEN** the candidate is rejected.
