## ADDED Requirements

### Requirement: Target-Only LLVM IR Emission

SiliconTune SHALL emit LLVM IR for the target function independently from the
benchmark harness.

#### Scenario: Emit source and normalized IR

- **GIVEN** a C file containing `transform`
- **WHEN** `silicontune optimize` runs with graph-superoptimization enabled
- **THEN** the output directory contains raw target IR and normalized target IR
- **AND** the IR metadata records compiler path, version, flags, target triple,
  and target CPU.

### Requirement: Preserve Analysis Provenance

Every lowered IR artifact SHALL be traceable to the input source, function name,
compiler flags, and transformation stage.

#### Scenario: Report provenance

- **GIVEN** a generated candidate
- **WHEN** the report is written
- **THEN** the candidate row names the IR artifact used for graph extraction.
