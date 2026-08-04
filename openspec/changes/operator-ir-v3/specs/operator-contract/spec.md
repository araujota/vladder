## ADDED Requirements

### Requirement: Machine-Readable Semantic Contract

SiliconTune SHALL reject operator analysis or optimization without a valid
contract naming inputs, outputs, state, semantics, distributions, objectives,
constraints, and specialization facts.

#### Scenario: Canonical contract identity

- **GIVEN** a valid YAML or JSON contract
- **WHEN** it is loaded
- **THEN** defaults and field order are canonicalized
- **AND** a stable SHA-256 contract hash is emitted.

#### Scenario: Missing numerical policy

- **GIVEN** a floating-point operator without exactness or tolerance policy
- **WHEN** validation runs
- **THEN** optimization is rejected before candidate generation.

### Requirement: Specialization Authority

Every specialized fact SHALL be enforced by a checked dispatch guard or an
explicit deployment precondition.

#### Scenario: Fixed dimension specialization

- **GIVEN** a candidate specialized for head dimension 128
- **WHEN** the contract does not declare dimension 128 and no guard exists
- **THEN** the candidate is structurally illegal.
