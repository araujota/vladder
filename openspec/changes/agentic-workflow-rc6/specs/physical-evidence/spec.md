## ADDED Requirements

### Requirement: Randomized paired measurement
vLadder SHALL measure baseline and candidate in randomized order over independent process pairs and
bootstrap the paired effect.

#### Scenario: Lower-is-better latency metric
- **WHEN** a manifest supplies one executable and baseline/candidate arguments
- **THEN** the report SHALL include raw pair order, process samples, median effect, confidence
  interval, minimum effect threshold, and disposition

### Requirement: Overlap-safe composition
vLadder SHALL reject compounded speedup claims for overlapping or ambiguously nested region sets.

#### Scenario: Parent and child benchmarks both improve
- **WHEN** the parent measurement already contains the child runtime
- **THEN** their improvements SHALL not be multiplied or summed without an explicit interaction run

### Requirement: Promotion evidence class
The physical report SHALL identify newly discovered, retained-and-revalidated, regressed, tied, and
insufficient evidence separately.

#### Scenario: Existing patch is rerun
- **WHEN** candidate source identity matches a retained baseline record
- **THEN** the outcome SHALL be `retained_revalidated`, not a newly discovered optimization
