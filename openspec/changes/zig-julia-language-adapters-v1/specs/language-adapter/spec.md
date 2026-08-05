## ADDED Requirements

### Requirement: Zig and Julia use the shared information-flow vocabulary

The system SHALL represent Zig and Julia regions with `SemanticFlowGraph` nodes and edges shared by
all supported languages. Language semantics SHALL be captured as provenance, contracts, and proof
obligations unless a genuinely new cross-language information concept is required.

#### Scenario: Equivalent byte reductions in different languages

- **WHEN** equivalent C, Rust, Zig, and Julia byte-count regions are captured
- **THEN** their load, compare, reduce, control, and output concepts use the same node kinds
- **AND** language differences appear in build identity and semantic obligations

### Requirement: Evidence remains language-semantic before LLVM

The system SHALL capture the selected Zig declaration or Julia method specialization and its native
semantic evidence before using LLVM refinement.

#### Scenario: Julia method selection

- **WHEN** a Julia generic function has more than one applicable method or no exact signature
- **THEN** the adapter SHALL require a concrete signature or fail closed
- **AND** SHALL NOT infer whole-generic-function equivalence from one compiled specialization
