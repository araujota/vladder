## ADDED Requirements

### Requirement: Stable compaction algorithm grammar

The system SHALL enumerate bounded GPU stable-compaction realizations preserving predicate identity,
stable order, exact extent, output capacity behavior, and caller-visible output.

#### Scenario: Capacity is insufficient
- **WHEN** selected elements exceed output capacity
- **THEN** the generated realization reports failure and leaves committed output/state unchanged

#### Scenario: Executable candidate
- **WHEN** the declared extent fits one workgroup or a bounded local-scan/group-scan/scatter hierarchy
- **THEN** the system emits compilable CUDA source, launch topology, and proof artifacts for each executable plan

### Requirement: GPU algorithm proof

The system SHALL prove lane coverage, unique output position, stable order, scan extent, scratch
bounds, and uniform barrier participation for the bounded source-lowered family.

#### Scenario: Invalid workgroup
- **WHEN** logical extent or scratch demand exceeds the declared architecture limit
- **THEN** the candidate is rejected before compilation or benchmarking
