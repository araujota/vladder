## ADDED Requirements

### Requirement: Complete native emitter matrix
Every terminal `deep-v2` realization SHALL have deterministic native emitters for C, C++, Rust,
Zig, and Julia.

#### Scenario: One terminal lacks a language route
- **WHEN** grammar coverage is validated
- **THEN** the grammar SHALL fail if any terminal lacks one of the five required native emitters.

### Requirement: Source-bound proof and execution
Each generated candidate SHALL be reconstructed from source, match the requested physical
realization, pass registered Z3 and Alive2-compatible obligations, and execute against a scalar
baseline in one physical harness.

#### Scenario: Compiler collapses two candidates
- **WHEN** different source realizations lower to the same normalized assembly
- **THEN** ranking SHALL classify them as assembly duplicates rather than independent evidence.

### Requirement: Language-specific obligations do not fork the graph
C++, Zig, and Julia emitters SHALL attach object-bound, safety, world, allocation, and deployment
facts as typed obligations without changing the common semantic shape.

#### Scenario: Julia uses deployment ISA specialization
- **WHEN** a Julia realization depends on the pinned CPU target rather than runtime CPUID
- **THEN** the proof envelope SHALL identify a deployment guard and exclude portability beyond that
  target.
