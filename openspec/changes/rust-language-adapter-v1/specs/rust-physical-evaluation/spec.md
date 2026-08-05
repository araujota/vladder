## ADDED Requirements

### Requirement: Same-executable Rust differential benchmark
The system SHALL compile baseline and candidate into one Rust harness, verify deterministic and
adversarial observables, randomize timed order, and report independent-process confidence intervals.

#### Scenario: Local speedup without parity
- **WHEN** any differential observable differs
- **THEN** the candidate SHALL be classified verification_failed and excluded from ranking.

### Requirement: Project serviceability study
The release SHALL pin an open-source Rust systems project, run its normal build/tests, inspect a
measured region, and execute at least one complete Rust adapter workflow.

#### Scenario: No project winner
- **WHEN** all verified candidates tie or regress
- **THEN** the study SHALL report the negative result and still distinguish adapter serviceability
  from optimization success.
