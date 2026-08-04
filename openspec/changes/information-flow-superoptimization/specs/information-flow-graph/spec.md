## ADDED Requirements

### Requirement: Typed Information-Flow Graph

SiliconTune SHALL represent target semantics as a typed graph.

The graph SHALL include:

- scalar and vector value nodes
- constants and arguments
- load and store nodes
- arithmetic, compare, select, and phi nodes
- loop/index-domain nodes
- data, control, memory, and dependence edges

#### Scenario: Serialize graph

- **GIVEN** a target function with a recognized slice
- **WHEN** graph extraction completes
- **THEN** a JSON graph artifact is written
- **AND** every node has a stable id, opcode, type, and source provenance when
  available.

### Requirement: Information-Flow Invariants

The graph SHALL expose invariants used by search.

#### Scenario: Pointwise independence

- **GIVEN** a pointwise map
- **WHEN** invariants are computed
- **THEN** the graph records that `dst[i]` depends on `src[i]` and constants only
- **AND** records no loop-carried data dependence.
