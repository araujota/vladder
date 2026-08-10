## ADDED Requirements

### Requirement: Project evidence discovery
The system SHALL discover candidate build, test, benchmark, output-hash, timing, and counter
interfaces from common project metadata without treating discovery as semantic proof.

#### Scenario: Existing test and benchmark commands
- **WHEN** project metadata exposes tests and benchmark executables
- **THEN** the generated project-evidence manifest records the commands, provenance, and confidence
- **AND** marks observable completeness as unresolved until bound by the user or agent

### Requirement: Generated adapter and manifest scaffolds
Every unresolved boundary SHALL produce a typed scaffold or an exact manifest patch with explicit
observables, ownership, error behavior, and integration points.

#### Scenario: Ownership-heavy C++ wrapper
- **WHEN** the local proof unit excludes allocation and publication behavior
- **THEN** the adapter contains production entry points, state projection, exact observable hook,
  fallback, and same-executable benchmark interface
- **AND** remains non-promotable until all TODO obligations are resolved

### Requirement: Physical runner protocol
The system SHALL represent CPU, GPU, network, presentation, and remote execution results in one
integrity-checked protocol containing hardware, workload, timing domain, exact observables,
counters, and provenance.

#### Scenario: Remote result tampering
- **WHEN** a returned artifact or workload hash differs from the signed request manifest
- **THEN** the result is rejected before benchmark or promotion evidence is recorded

### Requirement: Composed application evidence
The system SHALL connect regional measurements to invocation frequency, measured runtime share,
overlap, amortization, and an end-to-end confirmation boundary.

#### Scenario: Overlapping regional effects
- **WHEN** two candidate effects cover an overlapping runtime region
- **THEN** the composed model refuses to compound them without an interaction measurement
