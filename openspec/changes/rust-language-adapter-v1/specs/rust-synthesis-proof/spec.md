## ADDED Requirements

### Requirement: Native Rust candidate regeneration
The R1 grammar SHALL emit deterministic Rust source candidates for admitted information-flow
regions without translating production code through C.

#### Scenario: Candidate compilation
- **WHEN** a candidate is generated
- **THEN** rustfmt and captured rustc/Cargo compilation SHALL succeed before proof or ranking.

### Requirement: Bounded MIR semantic equivalence
The system SHALL derive a bounded symbolic model from recognized MIR operations and prove baseline
and candidate observables equal for the declared bounds, panic policy, and integer semantics.

#### Scenario: Counterexample
- **WHEN** a candidate changes an output, panic condition, or ordered-overflow behavior within bounds
- **THEN** Z3 SHALL return a counterexample and the candidate SHALL be rejected.

### Requirement: LLVM refinement is separate evidence
The system SHALL emit candidate LLVM IR and invoke Alive2 on compatible local units, recording
PASS, FAIL, UNAVAILABLE, or UNSUPPORTED independently of MIR proof.

#### Scenario: Strict promotion
- **WHEN** the contract requires LLVM refinement and Alive2 is not PASS
- **THEN** the candidate SHALL not be promoted even if differential and MIR tests pass.
