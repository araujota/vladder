## ADDED Requirements

### Requirement: Seven Pipeline Grammar Families

The V4 grammar SHALL include fusion, materialization, traversal, layout, state,
reduction, and scratch-lifetime transformations with explicit proof obligations.

#### Scenario: Tile-and-fuse

- **GIVEN** compatible producer and consumer iteration domains
- **WHEN** tile-and-fuse is proposed
- **THEN** the rule records tile shape, live working set, boundary handling, and
  observer/alias/numerical obligations.

### Requirement: Hierarchical Bounded Search

Pipeline search SHALL allocate and report finite budgets for pipeline regions and
child operator/expression searches.

#### Scenario: Unsaturated child region

- **GIVEN** a child search exhausts its beam or time budget
- **WHEN** the parent selects a candidate containing that child
- **THEN** the result is labeled best-found in that region and not grammar-optimal.

### Requirement: Vector Cost Preservation

The search SHALL retain compute, critical path, memory-level traffic,
synchronization, code size, and scratch estimates independently.

#### Scenario: Weighted extraction

- **GIVEN** a hardware profile weights DRAM traffic heavily
- **WHEN** plans are ranked
- **THEN** the scalar score is reproducible from the retained cost vector and weights.
