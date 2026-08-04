## ADDED Requirements

### Requirement: Authoritative Projection Binding

Every production projection complex SHALL bind its semantic nodes to authoritative
ggml graph nodes, model hash, llama.cpp commit, quantization, dimensions, and workload.

#### Scenario: Qwen gate/up extraction

- **GIVEN** the pinned Qwen graph
- **WHEN** the FFN complex is bound
- **THEN** all layer gate/up projections and their shared activation dependency are recorded.

### Requirement: End-To-End Acceptance

No production winner SHALL be accepted without exact model verification and
profiler-free portfolio measurement.

#### Scenario: Regional kernel win

- **GIVEN** a projection confidence interval excluding zero
- **WHEN** model tokens per second is a statistical tie
- **THEN** the result remains regional evidence, not a V5 winner.
