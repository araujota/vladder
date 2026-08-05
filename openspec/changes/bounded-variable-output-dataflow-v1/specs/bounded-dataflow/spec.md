## ADDED Requirements

### Requirement: Variable-output semantics are first class
The system SHALL represent output capacity, exact output extent, output order, selected indices and
values, and overflow behavior in SemanticFlowGraph v2.

#### Scenario: Stable index/value compaction
- **WHEN** a bounded predicate selects input elements
- **THEN** every accepted realization emits the same ordered index/value sequence and exact extent
- **AND** capacity failure follows the declared all-or-nothing policy

### Requirement: C++ container closure is contract bounded
The system SHALL close contiguous no-growth C++ regions only when capacity, trivial lifetime,
aliasing, and exception obligations are established.

#### Scenario: Vector output has insufficient capacity
- **WHEN** the maximum output exceeds available capacity
- **THEN** automatic no-growth lowering is rejected or guarded
- **AND** no allocation-free or no-throw claim is emitted for the owning wrapper

### Requirement: Stateful output and publication compose
The system SHALL model candidate state, output, commit, and rollback as distinct semantic effects.

#### Scenario: Delta buffer exhaustion
- **WHEN** a bounded delta cannot fit in caller-owned output
- **THEN** the observable state and output extent remain at their pre-transition values

### Requirement: Exact codecs use bitvector obligations
The system SHALL prove field placement, endian conversion, bounds, and malformed-input behavior for
fixed-width codecs with bounded bitvector obligations.

#### Scenario: Endian-aware field packing
- **WHEN** declared fixed-width fields are packed into a wire word
- **THEN** unpacking the declared bit ranges reproduces every admitted field value
- **AND** the emitted byte order matches the contract

### Requirement: Quality contracts remain distinct
The system SHALL report exact encoded identity, exact decoded identity, and bounded quality as
different proof classes.

#### Scenario: Bounded-quality block candidate
- **WHEN** a packed block candidate changes encoded bytes but remains within a declared quality metric
- **THEN** the result is classified as bounded quality only
- **AND** it is not reported as exact encoded or exact decoded identity

### Requirement: Repository audit is no-write
The system SHALL hash tracked source before and after a repository audit and fail if production
source changes.

#### Scenario: Read-only C++ acceptance audit
- **WHEN** a manifest is audited against a production compilation database
- **THEN** tracked source identity before and after is identical
- **AND** any identity difference produces a failing `source_changed` disposition
