## ADDED Requirements

### Requirement: Reproducible Projection Workflow

SiliconTune SHALL expose profile, synthesis, proof, production integration, and
portfolio ranking as content-addressed resumable stages.

#### Scenario: Static synthesis only

- **GIVEN** a verified static projection plan with no compiled realization
- **WHEN** reporting completes
- **THEN** the report states `best_verified_found`, physical measurement `NOT_RUN`,
  and makes no throughput claim.

### Requirement: Bounded V5 Claim

A V5 winner claim SHALL identify model, hardware, grammar, workload portfolio,
numerical contract, baselines, confidence interval, and all regression floors.

#### Scenario: Incomplete portfolio

- **GIVEN** missing concurrent or prompt evidence
- **WHEN** acceptance is evaluated
- **THEN** end-to-end V5 success remains open.
