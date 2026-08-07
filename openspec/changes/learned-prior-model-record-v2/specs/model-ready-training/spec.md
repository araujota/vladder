## ADDED Requirements

### Requirement: Model-ready graph records
The system SHALL preserve bounded sanitized semantic graph topology, structured grammar actions,
hardware/workload context, and append-only observations as separate linked entities.

#### Scenario: Candidate ranking group
- **WHEN** several legal candidates share a semantic root, hardware target, and workload
- **THEN** the exported records preserve that grouping and their independent outcomes

#### Scenario: Telemetry-only workflow
- **WHEN** a terminal workflow lacks an extracted semantic graph or structured candidate action
- **THEN** it remains v1 telemetry and is not counted as a model-ready graph root

### Requirement: Search-prior authority
The model-ready dataset SHALL support grammar applicability, candidate ranking, proof-risk,
outcome, and uncertainty heads without bypassing deterministic enumeration or verification.

#### Scenario: Prior ranks baseline last
- **WHEN** a model ranks the baseline below every alternative
- **THEN** search still retains the baseline and configured exploration reserve
