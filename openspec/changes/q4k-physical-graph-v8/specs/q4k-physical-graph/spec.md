## ADDED Requirements

### Requirement: Physical Instruction Provenance

SiliconTune SHALL map each classified hot-loop operation to source, LLVM IR, assembly,
stage, physical node class, and E1 semantic obligation.

#### Scenario: Auditing a bottleneck

- **GIVEN** the pinned regenerated production kernel
- **WHEN** its physical graph is emitted
- **THEN** a reviewer can trace each mapped instruction through all available provenance.

### Requirement: Graph Completeness Gate

The workflow SHALL fail graph completeness below 95% and SHALL list all unmapped hot-loop
instructions.

#### Scenario: Unrecognized lowering

- **GIVEN** a compiler change introducing unclassified hot-loop instructions
- **WHEN** physical extraction runs
- **THEN** the graph is not accepted silently.
