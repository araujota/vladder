## ADDED Requirements

### Requirement: Exact Rust build capture
The Rust adapter SHALL record Cargo metadata, lockfile hash, package/target, enabled features,
edition, profile, target triple, panic strategy, rustc version/commit/LLVM version, source hash, and
artifact hashes.

#### Scenario: Toolchain-coupled MIR
- **WHEN** a MIR artifact is parsed
- **THEN** the report SHALL bind parser support and proof reuse to the exact rustc identity.

### Requirement: MIR-confirmed semantic closure
The Rust adapter SHALL resolve the requested function, map source to MIR and LLVM artifacts, and
classify ownership, allocation, panic, drop, unsafe, calls, concurrency, and external effects.

#### Scenario: Unknown MIR operation
- **WHEN** the selected function contains an unmodeled MIR operation or terminator
- **THEN** semantic proof SHALL be unavailable with a named operation and recovery path.

### Requirement: Deterministic Rust information-flow graph
The adapter SHALL emit a graph containing parameters, borrowed regions, loads, predicates,
reductions/transforms, control edges, panic edges, outputs, and source/MIR/LLVM provenance.

#### Scenario: Repeated capture
- **WHEN** identical source and toolchain inputs are captured twice
- **THEN** graph and semantic hashes SHALL be identical.
