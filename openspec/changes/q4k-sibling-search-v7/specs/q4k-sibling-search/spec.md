## ADDED Requirements

### Requirement: E1 Sibling Candidates

Every timed sibling candidate SHALL match both native gate and up outputs bit-for-bit
before its timing sample is retained.

#### Scenario: Shared activation load

- **GIVEN** one Q8_K activation and two production Q4_Kx8 projections
- **WHEN** the fused candidate reuses loaded activation vectors
- **THEN** independent output identities and native float accumulation order are preserved.

### Requirement: Causal Promotion

A composite winner SHALL not promote a grammar family unless an ablation identifies a
measured mechanism and the regional interval clears the declared threshold.

#### Scenario: Statistical tie

- **GIVEN** a candidate whose interval includes zero or whose lower bound is below 3%
- **WHEN** ranking completes
- **THEN** it is classified as a tie and cannot enter production integration.

### Requirement: Attribution-Gated Expansion

New rules SHALL target a measured cycle, byte, cache, or synchronization bottleneck, or
increase useful work per fetched weight byte.

#### Scenario: Hot activation reuse regresses

- **GIVEN** a fused load-sharing candidate that saves hot Q8_K loads but does not save weights
- **WHEN** it fails the regional gate
- **THEN** additional variants of that family are rejected absent new attribution.
