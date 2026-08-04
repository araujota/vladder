## ADDED Requirements

### Requirement: Output-Producing Slice Extraction

SiliconTune SHALL extract a semantic slice rooted at stores to the target output
buffer.

#### Scenario: Pointwise map slice

- **GIVEN** `dst[i] = src[i] * a + b`
- **WHEN** the slice extractor runs
- **THEN** the slice contains the source load, constants, multiply, add, index,
  and output store
- **AND** excludes benchmark harness code.

### Requirement: Dependence-Aware Slice Boundaries

The slice extractor SHALL preserve loop-carried phis, guards, and memory
dependence edges needed for correctness.

#### Scenario: Recurrence slice

- **GIVEN** an IIR-style recurrence
- **WHEN** the slice extractor runs
- **THEN** the graph includes the carried state edge from iteration `i-1` to `i`.
