## ADDED Requirements

### Requirement: Ordered Claim Gates

SiliconTune SHALL not report a production or model-level win before semantic parity,
performance parity, production grammar execution, and regional promotion pass in order.

#### Scenario: Valid negative transfer

- **GIVEN** production reconstruction passes but all transformed candidates tie or regress
- **WHEN** V7 completes
- **THEN** the report calls reconstruction successful, transfer negative, and model-level value not run.

### Requirement: No Hidden Workload Claim

Baseline model equivalence SHALL not be represented as candidate throughput improvement.

#### Scenario: Regenerated baseline model pass

- **GIVEN** the regenerated native-equivalent symbol produces identical Qwen output
- **WHEN** no transformed candidate clears the regional gate
- **THEN** no candidate tokens/sec or model-level optimization claim is emitted.
