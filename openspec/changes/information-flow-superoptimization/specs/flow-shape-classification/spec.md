## ADDED Requirements

### Requirement: Flow Shape Classifier

SiliconTune SHALL classify each target graph into an information-flow family.

Supported initial families:

- `pointwise_map`
- `guarded_pointwise_map`
- `stencil`
- `scan`
- `recurrence`
- `indirect_memory`
- `unknown`

#### Scenario: Clamp classification

- **GIVEN** a clamp kernel
- **WHEN** classification runs
- **THEN** the family is `guarded_pointwise_map`
- **AND** the report names the guard predicates and pointwise independence.

#### Scenario: Prefix sum classification

- **GIVEN** a prefix sum kernel
- **WHEN** classification runs
- **THEN** the family is `scan`
- **AND** the report identifies the loop-carried accumulation dependence.
