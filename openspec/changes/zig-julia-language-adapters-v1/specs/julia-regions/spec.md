## ADDED Requirements

### Requirement: Concrete Julia specialization capture

The system SHALL key capture to an exact module, method, tuple signature, Julia version, active
project and manifest, source hash, CPU target, and world counter, and SHALL retain lowered, typed,
LLVM, and native artifacts.

#### Scenario: Dynamic or allocating Julia region

- **WHEN** typed IR contains dynamic dispatch, unstable `Any` values, GC allocation, exceptions,
  global mutation, tasks, `ccall`, or unresolved external effects
- **THEN** the system SHALL report an explicit adapter boundary and SHALL NOT claim closure

### Requirement: Native Julia regeneration and proof

The system SHALL regenerate Julia methods for the same concrete signature, prove the realized
schedule with Z3, use bounded LLVM refinement where compatible, run adversarial differential tests,
and rank steady-state execution in independent warmed Julia processes.

#### Scenario: Regenerated Julia specialization

- **WHEN** a J1 specialization is synthesized
- **THEN** every candidate SHALL be recaptured as typed and LLVM IR for the same tuple signature
- **AND** physical ranking SHALL exclude JIT compilation time after an explicit warm-up
