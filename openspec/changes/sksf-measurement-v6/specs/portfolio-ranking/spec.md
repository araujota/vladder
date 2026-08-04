## ADDED Requirements

### Requirement: Independent-Process Ranking

Production ranking SHALL use randomized candidate interleaving, at least ten independent
processes, and bootstrap confidence intervals over process-level results.

#### Scenario: Instrumented profile

- **GIVEN** a run with projection instrumentation enabled
- **WHEN** ranking is requested
- **THEN** the run is attribution evidence only and is excluded from ranking.

### Requirement: Workload Floors

The portfolio ranker SHALL report every workload and SHALL reject any candidate below a
declared minimum even when the weighted aggregate improves.

#### Scenario: Hidden KV regression

- **GIVEN** aggregate improvement above five percent and KV performance below its floor
- **WHEN** ranking runs
- **THEN** the candidate is rejected.

### Requirement: Missing Counters

Unavailable hardware counters SHALL be reported as unavailable rather than zero.

#### Scenario: perf security policy blocks PMU access

- **GIVEN** `perf_event_open` is denied
- **WHEN** counters are collected
- **THEN** timing may continue but counter-dependent claims remain unavailable.
