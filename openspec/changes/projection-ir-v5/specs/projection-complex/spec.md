## ADDED Requirements

### Requirement: ProjectionComplexGraph

SiliconTune SHALL represent shared-input quantized projection complexes as immutable
typed graphs between PipelineGraph and OperatorGraph.

#### Scenario: Shared-input FFN

- **GIVEN** gate and up projections sharing one activation
- **WHEN** the complex is constructed
- **THEN** activation preparation, both weight streams, accumulator banks, consumers,
  dimensions, quantization, token count, and sequence count are explicit.

### Requirement: Projection Cost Vector

Every complex SHALL retain weight, activation, metadata, temporary, MAC, arithmetic
intensity, materialization, synchronization, reuse, and measured-share fields.

#### Scenario: Missing physical metadata

- **GIVEN** an edge with unknown quantization or incompatible tile dimensions
- **WHEN** validation runs
- **THEN** synthesis is rejected before costing.
