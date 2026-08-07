## ADDED Requirements

### Requirement: Universal bounded plan graph

The system SHALL represent GPU algorithms, queue schedules, sparse-update policies, and presentation
policies in one deterministic semantic graph with typed dependencies, physical placement,
observables, provenance, and explicit search bounds.

#### Scenario: Same semantic operation across bindings
- **WHEN** a scan or publication operation is realized in CUDA, Vulkan orchestration, or generated C++
- **THEN** the semantic node kind remains shared while native API details are recorded as bindings

#### Scenario: Unbounded recursion
- **WHEN** a candidate graph contains a recursive SCC without a declared finite bound
- **THEN** synthesis fails closed and emits a bounded-adapter requirement

### Requirement: Executable realization classification

Every candidate SHALL distinguish generated source, executable runtime plan, model-only hypothesis,
and external adapter requirements.

#### Scenario: Queue plan generated
- **WHEN** queue assignment and synchronization are synthesized
- **THEN** the system emits a verified runtime-plan manifest but does not call it a source rewrite

### Requirement: GraphML ranking interface

The system SHALL export deterministic GraphML containing graph topology, semantic node classes,
candidate parameters, and declared bounds.

#### Scenario: Learned prior is configured
- **WHEN** an external model scores GraphML candidates
- **THEN** scores may rank search order but cannot replace legality or proof
