# Canonical Multilanguage Extraction

## ADDED Requirements

### Requirement: Shared canonical region model

The system SHALL represent bounded Rust, Zig, and Julia regions using one language-neutral model
and SHALL lower that model to `SemanticFlowGraph v2` without language-specific semantic node
kinds.

#### Scenario: Equivalent native spellings

- **WHEN** equivalent bounded regions are selected from Rust, Zig, and Julia
- **THEN** their canonical region hashes are identical
- **AND** language-specific facts occur only in contracts, obligations, and provenance

### Requirement: Broad bounded-family recognition

The system SHALL recognize exact predicate reduction, pointwise map, guarded pointwise map,
stencil, scan, recurrence, and bounded indirect-memory families for concrete allocation-free
native regions.

#### Scenario: Seven-family matrix

- **WHEN** each registered family is compiled by each native frontend
- **THEN** semantic capture succeeds with the expected canonical family

### Requirement: Compiler-corroborated capture

The system SHALL retain native compiler IR and SHALL reject source classifications whose required
operation structure is absent from the selected compiler representation.

#### Scenario: Missing compiler evidence

- **WHEN** source classification proposes a memory map but compiler evidence contains no memory operation
- **THEN** extraction fails with `compiler-shape-mismatch`

### Requirement: Typed language obligations

The system SHALL record ownership, bounds, panic/exception, safety mode, concrete specialization,
world identity, and allocation assumptions as typed obligations or contracts.

#### Scenario: Runtime semantics remain explicit

- **WHEN** a canonical region is emitted from a native frontend
- **THEN** its graph retains the language runtime facts required by that concrete compilation

### Requirement: Honest lowering coverage

The system SHALL independently report semantic capture, candidate generation, local proof,
physical benchmark, and source rewrite capabilities. Semantic capture SHALL NOT cause a
family-specific candidate generator to run for an unsupported family.

#### Scenario: Captured family lacks a physical lowerer

- **WHEN** a pointwise region has semantic closure but no native family lowerer
- **THEN** synthesis returns `lowerer_required` with zero candidates

### Requirement: Fail-closed unsupported behavior

Allocation, unsafe or external effects, concurrency, dynamic dispatch, ambiguous specialization,
and multiple unmodeled loops SHALL produce named boundaries while retaining any independently
closed local graph.

#### Scenario: Multiple loops require a larger graph

- **WHEN** a selected local region contains two unmodeled loops
- **THEN** canonical extraction returns a `loop-shape` boundary
