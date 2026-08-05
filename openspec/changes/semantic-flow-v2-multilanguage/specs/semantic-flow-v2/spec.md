## ADDED Requirements

### Requirement: Typed shared semantic planes
Every v2 graph SHALL represent proof obligations, observable effects, protocol transitions, and
claims with validated typed records rather than free-form strings.

#### Scenario: Native cleanup mechanisms differ
- **WHEN** Rust `Drop`, C++ destruction, Zig `defer`, or Julia cleanup maps to the graph
- **THEN** each SHALL use the shared cleanup effect/protocol kind with its native mechanism retained
  as a binding.

### Requirement: Deterministic graph identity
Graph hashes SHALL cover typed nodes, edges, obligations, effects, protocols, contracts, claims,
compiler identity, and source provenance in deterministic order.

#### Scenario: Provenance differs but shape is shared
- **WHEN** equivalent C, C++, Rust, Zig, and Julia regions use the same realization
- **THEN** full graph hashes MAY differ while their language-neutral semantic-shape hashes match.

### Requirement: Fail-closed typed references
Every node, effect, and protocol reference to an obligation or graph node SHALL resolve.

#### Scenario: Protocol guard is missing
- **WHEN** a transition names an unknown obligation
- **THEN** graph construction SHALL fail before synthesis.
