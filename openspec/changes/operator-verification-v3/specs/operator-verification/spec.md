## ADDED Requirements

### Requirement: Layered Candidate Admission

Every ranked candidate SHALL pass structural legality, applicable formal
obligations, and contract-specific differential tests.

#### Scenario: Structural failure precedes benchmark

- **GIVEN** a layout candidate with an unadapted external consumer
- **WHEN** admission runs
- **THEN** it is rejected before compilation or physical benchmarking.

### Requirement: Multi-Output Transition Equivalence

Verification SHALL compare every output and all persistent state after each
transition, not only final memory.

#### Scenario: Book update sequence

- **GIVEN** two implementations and a bounded event sequence
- **WHEN** SMT or differential verification runs
- **THEN** top-of-book, changed mask, level state, and error status match after
  every event.

### Requirement: Explicit Floating-Point Class

Every floating-point candidate SHALL be labeled bitwise equivalent,
IEEE-order equivalent, deterministically tolerance-bounded, distributionally
tolerance-bounded, or disallowed.

#### Scenario: Exact RMSNorm contract

- **GIVEN** a multiple-accumulator reduction that changes association
- **WHEN** the contract requires bitwise equality
- **THEN** the candidate is rejected even if ordinary random tests pass.

#### Scenario: Tolerance RMSNorm contract

- **GIVEN** declared absolute, relative, and long-run drift bounds
- **WHEN** adversarial and held-out tests remain inside every bound
- **THEN** the report labels the candidate tolerance-bounded, not equivalent.

### Requirement: Stateful Counterexample

Sequence failures SHALL retain a deterministic replay and minimize it where
possible.

#### Scenario: Risk reservation mismatch

- **GIVEN** a candidate reserves exposure before a later failed check
- **WHEN** sequence testing detects changed state on rejection
- **THEN** the candidate is rejected with the shortest known replay.

### Requirement: Restricted SPSC Verification

SiliconTune SHALL admit only one fixed-capacity, one-producer/one-consumer ring
contract.

#### Scenario: Relaxed publication rejected

- **GIVEN** a producer publishes its index using relaxed ordering without an
  equivalent synchronization proof
- **WHEN** memory-order admission runs
- **THEN** the candidate is rejected regardless of stress-test outcome.
