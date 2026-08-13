# Production Canonical Search Smoke Specification

## ADDED Requirements

### Requirement: One release-blocking battery

The system SHALL execute canonical identity, POR safety, incremental recovery, expensive-terminal
reduction, cheap-region cost gating, concurrent registration, checkpoint/resume, and mini-scaling
checks from one command and SHALL emit one stable JSON report.

#### Scenario: Any stage fails

- **WHEN** any stage reports a failed assertion or raises an unexpected exception
- **THEN** the battery SHALL return nonzero and the release-candidate gate SHALL fail

### Requirement: Exact semantic preservation

Identity, POR, resume, and scaling checks SHALL compare canonical terminal sets against an
unreduced authority and require exact equality.

#### Scenario: Reduction omits one terminal

- **WHEN** a reduced terminal set differs from its authority
- **THEN** the stage SHALL fail unconditionally

### Requirement: Fail-open uncertainty

Alias overlap and incomplete footprints SHALL remain dependent and SHALL not authorize POR skips.
Incremental hash disagreement SHALL reject the incremental result and return clean rematerialization.

#### Scenario: Incomplete action footprint

- **WHEN** one action lacks a complete footprint
- **THEN** both applicable orderings SHALL remain represented

### Requirement: Physical search-cost evidence

The expensive fixture SHALL invoke one real Z3 proof and one optimized C++ object compilation per
terminal and SHALL require fewer calls and lower measured wall time under reduced search.

#### Scenario: Reduced search preserves semantics but loses time

- **WHEN** proof/compiler counts decrease but measured wall time does not
- **THEN** the stage SHALL fail as a release-blocking performance regression

### Requirement: Durable release integration

CI, tag release, and release readiness SHALL invoke the battery. The artifact schema SHALL be
packaged and registered.

#### Scenario: Packaged release is checked

- **WHEN** release readiness executes
- **THEN** the canonical smoke report SHALL validate and have aggregate status `PASS`
