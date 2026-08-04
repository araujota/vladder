## ADDED Requirements

### Requirement: Hierarchical PipelineGraph

SiliconTune SHALL represent a pipeline as typed nodes referencing immutable
OperatorGraph children and typed edges describing inter-operator information flow.

#### Scenario: Transformer block extraction

- **GIVEN** norm, attention, residual, norm, MLP, and residual operators
- **WHEN** PipelineGraph extraction completes
- **THEN** child graph hashes and complete tensor dependencies are serialized
- **AND** topological stages and stateful edges are preserved.

### Requirement: Physical Edge Metadata

Every pipeline edge SHALL record shape, element type, layout, lifetime, alias set,
ownership, observers, materialization policy, reuse distance, and cache target.

#### Scenario: Unknown observer

- **GIVEN** an intermediate whose observer set is unresolved
- **WHEN** a non-materialized realization is requested
- **THEN** the transformation is rejected as structurally illegal.

### Requirement: Deterministic Hierarchical Provenance

Pipeline graphs SHALL content-address the manifest, child graphs, grammar, model,
workload, source, and target configuration.

#### Scenario: Repeated graph construction

- **GIVEN** identical inputs and tool versions
- **WHEN** graph construction runs twice
- **THEN** canonical content and graph hashes are identical.
