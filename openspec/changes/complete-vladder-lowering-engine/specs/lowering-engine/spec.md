## Purpose

Define executable and honest lowering behavior for the complete vLadder C/C++ vocabulary.

## ADDED Requirements

### Requirement: Callable family lowerers
Every grammar family SHALL resolve to an importable callable lowerer whose declared family and
rule coverage match the registry.

#### Scenario: Symbolic or missing lowerer
- **WHEN** registry validation encounters an unimportable lowerer or missing rule implementation
- **THEN** validation fails and identifies the family, entrypoint, and uncovered rules

### Requirement: Complete plan lowering
Every declared rule SHALL deterministically lower into a plan containing legality guards,
information-flow operations, proof obligations, cost signals, backend route, and derivation hash.

#### Scenario: Lower a modeled concurrency rule
- **WHEN** the required SPSC contract facts are supplied for a concurrency rule
- **THEN** vLadder emits a deterministic plan without claiming to emit replacement source

### Requirement: Contract-gated requests
The lowering engine SHALL reject requests missing rule-specific facts or parameters before source
generation or benchmarking.

#### Scenario: Layout conversion without ownership
- **WHEN** an AoS-to-SoA request does not establish layout ownership and complete consumer coverage
- **THEN** the result is rejected with those missing facts

### Requirement: Separate source-emission coverage
The engine SHALL report plan coverage and source-emission coverage independently.

#### Scenario: Plan-only rule requested as source
- **WHEN** a caller requests source emission for a plan-only rule
- **THEN** the result is unsupported and no source artifact is produced

### Requirement: Existing backend routing
Source-capable rules SHALL identify a concrete existing vLadder backend and required input shape.

#### Scenario: Pointwise strength reduction
- **WHEN** a supported pointwise region requests strength reduction
- **THEN** its lowering plan routes to the expression graph candidate backend and records its proof obligations

### Requirement: Public inspection and execution
Library and CLI clients SHALL be able to validate lowering completeness, inspect rule support, and
generate plans.

#### Scenario: Installed package validation
- **WHEN** `vladder lower validate` runs from an installed wheel
- **THEN** all registry lowerers import and every declared rule has exactly one owner
