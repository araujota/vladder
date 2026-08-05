## ADDED Requirements

### Requirement: Bounded Zig region capture

The system SHALL capture exact Zig compiler identity, source/build hashes, safety mode, target, the
selected function, native compiler diagnostics, LLVM IR, and assembly for one bounded region.

#### Scenario: Unsupported Zig effect

- **WHEN** the selected region uses allocator ownership, error propagation, `defer`, atomics,
  volatile I/O, inline assembly, or an unresolved external effect
- **THEN** the system SHALL name the boundary and SHALL NOT claim automatic closure

### Requirement: Native Zig regeneration and proof

The system SHALL regenerate legal Zig source, parse its realized schedule, prove exact reduction
equivalence with Z3, compile it with the captured safety policy, differentially execute it, and rank
it physically in one native harness.

#### Scenario: Regenerated Zig schedule

- **WHEN** a Z1 region is synthesized
- **THEN** every candidate schedule SHALL be derived back from generated Zig source
- **AND** only candidates passing proof and native differential execution may be ranked
