## ADDED Requirements

### Requirement: First-class lifetime graph
vLadder SHALL represent semantic authority, realization policy, physical placement, consumers,
invalidators, final use, ownership, consistency, fallback, and partial-order scope relations in a
deterministically hashed `LifetimeFlowGraph`.

#### Scenario: Peer scopes are not interchangeable
- **WHEN** two frame instances share a process but not a frame identity
- **THEN** a frame-scoped realization cannot be reused between them

### Requirement: Contract-bounded attribution
Runtime traces SHALL measure construction, consumption, mutation, invalidation, retirement, and
transfer without inferring semantic validity from observed non-mutation.

#### Scenario: Repeated but mutable derivation
- **WHEN** a value is repeatedly reconstructed but its contract lists an uncovered mutation
- **THEN** discovery reports the redundancy but rejects lifetime extension

### Requirement: Bounded lifetime grammar
The system SHALL enumerate repeated-derivation retention, serialization-body reuse,
immutable/mutable splitting, intermediate elimination or final-use retirement, and placement
residency with deterministic candidate identities and explicit fallback.

#### Scenario: Unobserved intermediate
- **WHEN** an intermediate has no independent observer and one compatible consumer
- **THEN** the grammar enumerates direct consumer placement with zero intermediate lifetime

### Requirement: Layered lifecycle verification
Accepted lifetime candidates SHALL pass structural legality, bounded Z3 state-transition
obligations, stateful differential traces, fallback checks, and applicable local-helper proof
requirements.

#### Scenario: Missing invalidation
- **WHEN** a candidate omits one source mutation that affects its represented projection
- **THEN** verification fails and emits a counterexample or explicit failed obligation

### Requirement: Honest realization adapter
Repository-level candidates SHALL emit an agent realization contract and SHALL NOT claim generic
source generation for unsupported architecture, ownership, GPU, transport, or concurrency regions.

#### Scenario: Concurrent publication
- **WHEN** the contract is not single-owner or immutable publication
- **THEN** the plan requires a protocol adapter such as CBMC or TLA+ before implementation

### Requirement: Composed optimization
Lifetime plans SHALL expose generated hot helpers to the existing lowering registry while
preserving the architectural lifetime and proof envelope.

#### Scenario: Serialized-body patch helper
- **WHEN** record-level reuse creates a fragment-header patch helper
- **THEN** the plan names applicable expression, memory, and loop grammar families separately

### Requirement: Reproducible evaluation
The package SHALL include an isolated corpus that measures discovery quality, seeded lifecycle
failures, deterministic hashes, grammar coverage, proof status, and physical microbenchmark deltas.

#### Scenario: Release validation
- **WHEN** the lifetime corpus is evaluated twice with the same manifests and traces
- **THEN** graph and candidate identities match and all negative lifecycle cases remain rejected
