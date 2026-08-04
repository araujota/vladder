## ADDED Requirements

### Requirement: Portfolio-Gated Promotion

A distinct V9 plan SHALL improve portfolio-weighted tokens per second by at least five percent,
preserve the interactive floor, pass verification, and exclude zero before acceptance.

#### Scenario: Batching helps but is already the baseline

- **GIVEN** a causal ablation showing ready-lane reuse value
- **WHEN** the synthesized plan is identical to production default execution
- **THEN** the useful-work hypothesis is supported but the candidate is not accepted.

### Requirement: Byte-Claim Separation

Logical model-byte accounting SHALL be distinguished from measured external-memory traffic.

#### Scenario: PMU DRAM bytes are unavailable

- **GIVEN** model size and useful MAC counts only
- **WHEN** intensity is reported
- **THEN** it is labeled a logical proxy and no physical bandwidth-reduction claim is made.
