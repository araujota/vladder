## ADDED Requirements

### Requirement: Native C and Rust regeneration
One shared realization plan SHALL regenerate deterministic native C and Rust implementations for
every language declared supported by that plan.

#### Scenario: Language contract differs
- **WHEN** C requires object-bound and alias obligations while Rust requires borrow, panic, and
  unsafe obligations
- **THEN** the emitted source and proof envelope SHALL differ without changing the common graph.

### Requirement: Layered exact proof
Exact deep candidates SHALL pass graph legality, Z3 lane/reduction/traversal/tail obligations,
native differential execution, and compatible LLVM refinement required by the contract.

#### Scenario: Core identity passes but tail coverage fails
- **WHEN** the vector core is equivalent but an input length is uncovered or double counted
- **THEN** the candidate SHALL be verification_failed and excluded from ranking.

### Requirement: Physical ranking follows proof
The system SHALL benchmark baseline and proved candidates in the same executable, randomize timed
order, report confidence intervals, and retain regressions and ties.

#### Scenario: Expert-shaped candidate regresses
- **WHEN** an expert-shaped candidate passes proof but does not meet the minimum physical effect
- **THEN** it SHALL not be promoted and the grammar audit SHALL distinguish lowering success from
  performance transfer.
