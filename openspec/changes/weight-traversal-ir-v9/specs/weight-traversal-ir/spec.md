## ADDED Requirements

### Requirement: Complete Weight Traversal Graph

The system SHALL represent every required V9 node kind and SHALL terminate each traversal at
`WeightTraversalEnd` only after its consumer barrier.

#### Scenario: Build a pinned production graph

- **GIVEN** a valid E1 Q4_K x Q8_K manifest
- **WHEN** the graph is constructed
- **THEN** all required nodes, exactness obligations, lane ownership, and provenance are emitted.

### Requirement: Deterministic Graph Identity

Equivalent manifests SHALL produce the same graph hash.

#### Scenario: Repeat graph construction

- **GIVEN** unchanged model, target, contract, and grammar data
- **WHEN** construction is repeated
- **THEN** graph content and identity are stable.
