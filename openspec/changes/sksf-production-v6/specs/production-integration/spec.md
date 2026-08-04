## ADDED Requirements

### Requirement: Pinned Production Integration

Production claims SHALL bind the active llama.cpp kernel path, commit, model hash,
compiler, target manifest, graph hash, grammar hash, and runtime plan.

#### Scenario: Synthetic winner

- **GIVEN** a verified standalone low-bit kernel win
- **WHEN** no pinned model integration exists
- **THEN** the report makes no Q4_K or tokens/sec claim.

### Requirement: Guarded Runtime Plan

Every specialized realization SHALL have an exhaustive checked guard and verified
fallback for unsupported regimes.

#### Scenario: Token tile changes

- **GIVEN** token count outside a specialized tile bucket
- **WHEN** dispatch executes
- **THEN** the verified fallback runs without semantic or state change.

### Requirement: KV Attribution Gate

KV-pressure grammar SHALL not enter default search until measured context/KV attribution
identifies a material target bottleneck.

#### Scenario: KV memory reduction only

- **GIVEN** a candidate that reduces cache capacity but lacks throughput attribution
- **WHEN** production admission runs
- **THEN** the candidate is not accepted.
