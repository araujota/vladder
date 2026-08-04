## ADDED Requirements

### Requirement: Typed OperatorGraph

SiliconTune SHALL represent fused streaming operators using the required node
classes and typed edge metadata from the V3 architecture.

#### Scenario: Stateful multi-output graph

- **GIVEN** decode, state update, change-mask, and top-of-book outputs
- **WHEN** OperatorGraph extraction completes
- **THEN** state reads/writes form an annotated SCC
- **AND** both output dependencies and ordering edges are serialized.

### Requirement: Materialization And Fusion Regions

OperatorGraph SHALL identify temporary materializations and maximal regions that
may legally fuse under the contract.

#### Scenario: Externally observed temporary

- **GIVEN** a stage output declared as an external output
- **WHEN** fusion regions are computed
- **THEN** the output remains a barrier and cannot be eliminated.

### Requirement: Deterministic Provenance

Every graph SHALL name contract hash, source hash, extraction stage, target
function or manifest entry, and graph schema version.

#### Scenario: Repeated extraction

- **GIVEN** identical source, contract, and toolchain configuration
- **WHEN** extraction runs twice
- **THEN** canonical graph content and graph hash are identical.
