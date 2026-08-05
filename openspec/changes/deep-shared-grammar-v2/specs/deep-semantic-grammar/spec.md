## ADDED Requirements

### Requirement: Shared physical realization vocabulary
The system SHALL represent scalar lanes, packed words, SIMD vectors, masks, population counts,
horizontal reductions, traversal, tails, dispatch, materialization, fusion, tables, constants, and
complexity bounds in one language-neutral graph vocabulary.

#### Scenario: Native Rust SIMD
- **WHEN** a Rust adapter emits an AVX2 byte-count realization
- **THEN** vector, mask, reduction, and traversal nodes SHALL use the same kinds as an equivalent C
  realization, with Rust unsafe and panic obligations attached as contracts and provenance.

### Requirement: Executable deep grammar families
The deep grammar SHALL provide typed, deterministic, proof-backed rules for scalar-to-word and
scalar-to-SIMD decomposition; lane packing, mask extraction, and population reduction; algebraic
and bit-vector identities; reduction topology; alignment and tails; vector width and ISA dispatch;
load shape and traversal; table and constant synthesis; producer-consumer fusion and intermediate
elimination; and algorithmic representation changes with explicit complexity bounds.

#### Scenario: Coverage declaration
- **WHEN** a rule is reported executable
- **THEN** it SHALL identify a target graph constructor, native source emitters for declared
  languages, proof generators, differential observables, and a physical benchmark binding.

### Requirement: Derivation provenance
Search SHALL retain every applied rule, precondition, parameter, source graph hash, target graph
hash, proof obligation, complexity delta, and extraction classification.

#### Scenario: Search budget ends before saturation
- **WHEN** the configured state or time budget is exhausted
- **THEN** the result SHALL be `best_verified_found`, not bounded optimal.

### Requirement: Complexity-bounded algorithmic changes
Every algorithmic representation rule SHALL record baseline and candidate work, pass, byte, and
temporary-materialization models under declared input bounds.

#### Scenario: Better complexity with changed observables
- **WHEN** a candidate has a better complexity model but changes an observable
- **THEN** it SHALL be rejected before physical ranking.
