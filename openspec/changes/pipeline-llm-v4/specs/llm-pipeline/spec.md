## ADDED Requirements

### Requirement: Authoritative Production Graph

LLM PipelineGraph extraction SHALL use the exact pinned llama.cpp model graph and
record model, commit, build, backend, quantization, and workload identities.

#### Scenario: Existing production fusion

- **GIVEN** pinned llama.cpp already fuses a region
- **WHEN** SiliconTune evaluates that region
- **THEN** the production fusion remains enabled in the baseline.

### Requirement: Progressive Decode Coverage

V4 SHALL attribute residual/norm, projection, RoPE, attention, and sampling regions
separately before composing broader decode candidates.

#### Scenario: Research milestone

- **GIVEN** verified integrated regions
- **WHEN** inclusive baseline attribution is computed without double counting
- **THEN** at least 25 percent decode coverage is required to close the milestone.

### Requirement: Model-Level Acceptance

A V4 commercial milestone claim SHALL require at least five percent verified
end-to-end token-generation improvement with a confidence interval excluding zero.

#### Scenario: Standalone win only

- **GIVEN** pipeline microbenchmarks improve but model tokens per second do not
- **WHEN** the report is emitted
- **THEN** model-level acceptance remains open.
