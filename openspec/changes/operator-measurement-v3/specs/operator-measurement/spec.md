## ADDED Requirements

### Requirement: Immutable Measurement Identity

Every sample SHALL be keyed by a manifest hash covering material hardware,
software, affinity, workload, source, contract, grammar, and candidate identity.

#### Scenario: Mixed governor data

- **GIVEN** samples collected under `performance` and `powersave`
- **WHEN** aggregation is attempted
- **THEN** aggregation is refused and incompatible hashes are reported.

### Requirement: Tail-Latency Sampling

The low-latency runner SHALL retain raw per-invocation cycle samples and report
p50, p90, p99, p99.9, p99.99, and maximum with independent-process bootstrap
intervals.

#### Scenario: Insufficient tail samples

- **GIVEN** too few held-out samples to estimate p99.99 under configured policy
- **WHEN** ranking runs
- **THEN** no p99.99 acceptance claim is emitted.

### Requirement: Candidate Order And Cache Modes

Candidate order SHALL be randomized reproducibly and warm/cold-cache modes SHALL
be reported separately.

#### Scenario: Cache-mode merge

- **GIVEN** warm and cold samples
- **WHEN** summary generation runs
- **THEN** they remain separate populations.

### Requirement: Objective-Specific Ranking

Token and HFT profiles SHALL enforce different primary metrics and constraints.

#### Scenario: HFT median-tail conflict

- **GIVEN** lower median cycles and a p99.99 regression above 1%
- **WHEN** the HFT acceptance ranker runs
- **THEN** the candidate cannot win.

### Requirement: Held-Out Evaluation

Final performance claims SHALL use traces excluded from search tuning.

#### Scenario: Missing held-out trace

- **GIVEN** only a tuning trace
- **WHEN** optimization finishes
- **THEN** artifacts are emitted as exploratory without an accepted winner.
