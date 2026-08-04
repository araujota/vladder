## ADDED Requirements

### Requirement: Attribution Before Grammar

SiliconTune SHALL require every grammar family to cite a content-addressed attribution
study and one or more measured bottlenecks before default search may use its rules.

#### Scenario: Material measured bottleneck

- **GIVEN** a family whose target metric occurs in a cited bottleneck above the admission threshold
- **WHEN** grammar registration runs
- **THEN** the family is admitted with its evidence hash retained.

#### Scenario: Interesting but low-share rule

- **GIVEN** a rule targeting a region below the materiality threshold
- **WHEN** grammar registration runs
- **THEN** the family is exploratory and disabled by default.

#### Scenario: Metric mismatch

- **GIVEN** a rule targeting temporary bytes when the cited study measured only fused time
- **WHEN** grammar registration runs
- **THEN** the family is rejected.

### Requirement: Attribution Provenance

Every study SHALL identify target, workload, source artifact hash, measurement class,
causal resolution, confidence, and limitations.

#### Scenario: Stale source artifact

- **GIVEN** an attribution file whose source content no longer matches its hash
- **WHEN** validation runs
- **THEN** validation fails before search.
