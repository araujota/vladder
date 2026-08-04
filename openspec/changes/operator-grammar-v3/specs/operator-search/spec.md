## ADDED Requirements

### Requirement: Staged Bounded Search

SiliconTune SHALL normalize, saturate regions, compose regional alternatives,
statically filter, compile, benchmark, locally refine, and finally verify.

#### Scenario: Unsaturated region

- **GIVEN** a region whose node or time budget is exhausted
- **WHEN** reporting completes
- **THEN** that region is labeled `best_found`
- **AND** no global or saturated optimality claim is emitted.

### Requirement: Multi-Objective Dominance

Search SHALL retain nondominated candidates across objective cost, traffic,
code, stack, and numerical error before physical benchmarking.

#### Scenario: Tail objective candidate

- **GIVEN** an HFT profile
- **WHEN** a candidate has lower estimated median but exceeds stack or code limits
- **THEN** it is pruned with the violated constraint recorded.

### Requirement: Held-Out Ranking

Candidates SHALL NOT be finally ranked on the same traces used to fit or tune a
surrogate or search policy.

#### Scenario: Training trace reuse

- **GIVEN** a candidate tuned on trace A
- **WHEN** no held-out trace is supplied
- **THEN** the result is exploratory and cannot become the emitted winner.
