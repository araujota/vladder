## ADDED Requirements

### Requirement: C++ adapter bundle generation
vLadder SHALL generate a deterministic application adapter bundle from a selected C++ closure.

#### Scenario: Ownership-heavy member function
- **WHEN** local proof units exist but object construction and observables are unresolved
- **THEN** the bundle SHALL include typed benchmark, observable, state-projection, and agent-task
  templates with unresolved facts marked as promotion blockers

### Requirement: Bounded retained-state protocols
vLadder SHALL verify finite versioned-cache and transactional-publication contracts with Z3 and
emit counterexamples for stale reads, incomplete invalidation, partial publication, and bad rollback.

#### Scenario: Missing invalidator
- **WHEN** a cache transition mutates an authoritative dependency without changing its version
- **THEN** verification SHALL fail with a concrete state-transition counterexample

### Requirement: Explicit arbitrary-C++ limit
The C++ workflow SHALL distinguish source-selection failures, isolatable local closure,
contract-bounded state, and external protocol state without globally blocking optimization.

#### Scenario: Callback-heavy coroutine wrapper
- **WHEN** control and ownership escape the selected local IR
- **THEN** whole-wrapper proof SHALL remain adapter-bound while closed subregions and physical
  attribution remain available
