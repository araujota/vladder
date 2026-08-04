## Purpose

Define the fully automatic extraction-to-proof workflow for explicitly supported bounded regions.

## ADDED Requirements

### Requirement: Finite support classification
vLadder SHALL classify a requested function against a versioned support matrix before synthesis.

#### Scenario: Supported ordered scan
- **WHEN** a canonical single-loop prefix scan is inspected
- **THEN** the report identifies exact automatic lowering and its proof requirements

### Requirement: Honest adapter requirements
Unsupported code SHALL return structured adapter requirements and SHALL NOT claim that source
synthesis was attempted.

#### Scenario: External call in loop
- **WHEN** the target loop invokes an external function
- **THEN** vLadder requests an external-call semantic adapter and emits no replacement

### Requirement: Exact structural regeneration
The automatic lowerer SHALL preserve the admitted loop's logical iteration order, body statement
order, boundaries, prefix, suffix, and scalar tail.

#### Scenario: Recurrence unrolling
- **WHEN** a bounded exact recurrence is lowered by factor four
- **THEN** iterations execute in original order and no floating-point reassociation occurs

### Requirement: Layered proof orchestration
Automatic replacements SHALL require structural legality, Z3 loop and memory proofs, canonical
LLVM IR identity or Alive2 translation validation, differential execution, and applied-source
identity. Reports SHALL distinguish pre-solver IR identity from an invoked Alive2 result.

#### Scenario: Alive2 unsupported
- **WHEN** Alive2 cannot validate a generated candidate
- **THEN** strict promotion is blocked even if differential tests pass

### Requirement: Automatic public workflow
Library and CLI users SHALL be able to inspect support and run the complete automatic workflow.

#### Scenario: Supported fixture
- **WHEN** `vladder region optimize` receives a supported fixture
- **THEN** it extracts, transforms, regenerates, proves, benchmarks, and reports without manual candidate code
