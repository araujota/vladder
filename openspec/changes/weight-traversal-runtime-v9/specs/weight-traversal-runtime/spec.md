## ADDED Requirements

### Requirement: Guarded Runtime Dispatch

Every synthesized runtime plan SHALL include explicit phase and lane guards and SHALL end in
an unconditional pinned-native fallback.

#### Scenario: No specialized guard matches

- **GIVEN** an unsupported queue or phase state
- **WHEN** dispatch executes
- **THEN** the native baseline is selected.

### Requirement: Implementation Identity Deduplication

Binary-and-argument-identical plans SHALL be classified as one implementation and SHALL NOT
be promoted from sampling noise.

#### Scenario: Search rediscovers default llama.cpp batching

- **GIVEN** identical executable hashes and runtime arguments
- **WHEN** physical samples differ randomly
- **THEN** effective improvement is zero and novelty acceptance fails.
