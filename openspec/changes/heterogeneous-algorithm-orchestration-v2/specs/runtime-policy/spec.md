## ADDED Requirements

### Requirement: Queue-overlap synthesis

The system SHALL enumerate legal queue assignments over a finite dependency DAG, synthesize required
cross-queue synchronization, verify resource hazards, and estimate critical-path makespan.

#### Scenario: Independent operations
- **WHEN** two operations have no semantic/resource dependency and compatible queues exist
- **THEN** a candidate may overlap them without weakening either operation's observables

### Requirement: Sparse-update policy synthesis

The system SHALL enumerate exact sparse/dense dispatch and representation choices from declared
density, capacity, generation, and reconstruction contracts.

#### Scenario: Policy guard changes realization
- **WHEN** observed density crosses a generated threshold
- **THEN** sparse and dense paths reconstruct identical candidate state and publish one atomic extent

### Requirement: Presentation policy synthesis

The system SHALL enumerate only present modes and image/flight counts supported by the bound device
contract and SHALL verify acquire-render-present-release lifecycle safety.

#### Scenario: Physical display unavailable
- **WHEN** no representative presentation runner or visible-stage timestamps exist
- **THEN** the plan remains non-promotable regardless of modeled latency

### Requirement: External runner evidence

Physical promotion SHALL require randomized clean runs, exact observable hashes, matching hardware,
and an evidence class appropriate to the claimed boundary.

#### Scenario: Simulated runner
- **WHEN** a runner reports modeled or simulated timing
- **THEN** the result may validate workflow mechanics but cannot promote a candidate
