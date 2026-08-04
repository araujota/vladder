## ADDED Requirements

### Requirement: Comparable Physical Bounds

Memory bounds SHALL use sustainable bandwidth measured with a comparable access pattern,
and all ISA and dependency assumptions SHALL be retained in the report.

#### Scenario: Warm production region

- **GIVEN** a 14 MB gate/up weight region resident in the target LLC
- **WHEN** its memory floor is calculated
- **THEN** the result is identified as a warm LLC-pattern bound rather than peak DRAM.

### Requirement: Qualified Bottleneck Classification

SiliconTune SHALL not label a kernel physically optimal from a single analytical bound.

#### Scenario: Mixed execution

- **GIVEN** no applicable floor accounts for most observed runtime
- **WHEN** bounds are compared
- **THEN** the report classifies mixed execution and retains uncertainty.
