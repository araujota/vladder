## ADDED Requirements

### Requirement: Canonical agent workflow manifest
vLadder SHALL accept one manifest describing the region, semantic contract, attribution evidence,
workload, proof policy, and external adapters, and SHALL route it to the applicable bounded workflow.

#### Scenario: C++ region with a protocol boundary
- **WHEN** an agent runs the workflow for a C++ method containing local loops and external calls
- **THEN** the result SHALL preserve both local opportunities and unresolved protocol obligations

### Requirement: Unified promotion summary
Every workflow SHALL distinguish completion, capture, generation, proof, benchmark, integration,
promotion, and retained-production states in one machine-readable summary.

#### Scenario: Locally proved candidate without application benchmark
- **WHEN** a candidate passes local proof but has no application workload adapter
- **THEN** `candidate_proved` SHALL be true while `benchmarked` and `production_retained` remain false

### Requirement: Queryable artifact lineage
The summary SHALL expose source-to-disposition artifact edges and the five decisive artifacts.

#### Scenario: Agent asks what to do next
- **WHEN** a workflow is incomplete
- **THEN** one `next_action` and the exact blocking evidence SHALL be available without inspecting
  unrelated JSON files

### Requirement: Content-addressed resumability
Stages SHALL be resumable only when source, compiler, grammar, contract, workload, and tool hashes
match, and SHALL report reused versus newly computed evidence.

#### Scenario: Revalidation after no semantic input changed
- **WHEN** a completed stage is rerun with an identical cache key
- **THEN** the summary SHALL classify it as `revalidated` rather than `newly_discovered`

### Requirement: Architectural findings
Measured information-volume or lifetime findings SHALL be reportable without a generated source
candidate.

#### Scenario: External protocol dominates cost
- **WHEN** attribution identifies repeated transfer but generic equivalence is unavailable
- **THEN** the workflow SHALL emit an architectural finding and a protocol adapter requirement
