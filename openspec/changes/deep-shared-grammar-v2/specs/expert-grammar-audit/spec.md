## ADDED Requirements

### Requirement: Five-stage expert coverage audit
For each declared scalar/expert pair, the system SHALL independently classify representation,
derivation, lowering, proof, and physical-performance coverage.

#### Scenario: Expert graph is representable but unreachable
- **WHEN** baseline and expert graphs are valid but no grammar path connects them
- **THEN** the audit SHALL classify `grammar_failure` and identify the missing transition class.

#### Scenario: Derivation exists but source cannot be emitted
- **WHEN** a target graph is reachable but no emitter supports its contract
- **THEN** the audit SHALL classify `lowering_failure` rather than representation or proof failure.

### Requirement: External validation is read-only
The audit SHALL fingerprint external repositories before and after inspection and write no source,
build, skill, or report artifacts into them.

#### Scenario: NeuralFusion inspection
- **WHEN** NeuralFusion evidence is used to test representability
- **THEN** its revision and worktree fingerprint SHALL be unchanged and no full optimization
  workflow SHALL be run.
