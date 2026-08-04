## ADDED Requirements

### Requirement: Three Traffic Classes

Reports SHALL distinguish logical tensor bytes, modeled memory-level transfers, and
measured hardware events.

#### Scenario: Materialization eliminated without counters

- **GIVEN** a graph removes a logical temporary
- **WHEN** hardware counters are unavailable
- **THEN** the report may claim fewer logical materialized bytes
- **AND** SHALL NOT claim measured DRAM or cache-traffic reduction.

### Requirement: Decode Attribution

Every candidate SHALL report the baseline fraction of decode affected and its Amdahl
upper bound before model-level performance acceptance.

#### Scenario: Small optimized region

- **GIVEN** a region accounts for less than 25 percent of decode
- **WHEN** it improves in isolation
- **THEN** the report preserves the result but leaves the V4 research milestone open.

### Requirement: Reproducible Physical Ranking

Ranking SHALL use randomized independent processes, immutable model/workload/target
identities, bootstrap intervals, and statistical-tie classification.

#### Scenario: Configuration drift

- **GIVEN** pre/post hardware manifests differ materially
- **WHEN** ranking completes
- **THEN** measurements are rejected rather than combined.
