## ADDED Requirements

### Requirement: Multi-Layer Cost Model

SiliconTune SHALL evaluate candidates using static and empirical signals.

Signals:

- `llvm-mca` throughput
- code size
- instruction count
- benchmark runtime
- confidence interval
- optional perf counters

#### Scenario: Candidate ranking

- **GIVEN** multiple verified candidates
- **WHEN** ranking runs
- **THEN** runtime is the primary objective
- **AND** code size/instruction count are tie breakers
- **AND** the report includes static and empirical cost data.

### Requirement: Conservative Static Pruning

SiliconTune MAY skip benchmarking candidates whose static cost is clearly worse,
but SHALL record that pruning decision and threshold.

#### Scenario: Static candidate rejected

- **GIVEN** a compiled candidate whose `llvm-mca` throughput estimate exceeds the configured baseline threshold
- **WHEN** static pruning runs
- **THEN** the candidate is not empirically benchmarked
- **AND** its report row records `STATIC_PRUNED`, the estimate, baseline, and threshold.
