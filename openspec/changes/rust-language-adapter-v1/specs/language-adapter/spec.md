## ADDED Requirements

### Requirement: Versioned language adapter protocol
The system SHALL expose a language-neutral adapter protocol for build capture, semantic region
resolution, effect classification, information-flow lowering, native source regeneration, proof,
and physical evidence.

#### Scenario: Adapter evidence remains language-specific
- **WHEN** an adapter emits a common information-flow graph
- **THEN** it SHALL retain source language, compiler identity, semantic IR identity, and excluded
  proof claims rather than erasing those obligations into LLVM.

### Requirement: Shared semantic vocabulary
All language adapters SHALL lower values, state, control, memory, materialization, transfer,
ownership, and lifetime into one common semantic vocabulary. Language-specific facts SHALL be
represented as provenance, contracts, or proof obligations unless they express a semantic concept
that the common model cannot represent.

#### Scenario: Rust borrow semantics
- **WHEN** Rust MIR contributes a shared or mutable borrow
- **THEN** the adapter SHALL use common ownership/lifetime edges with Rust provenance and borrow
  obligations rather than creating a separate Rust-only flow graph.

### Requirement: Capability vectors replace binary support
Each language adapter SHALL report semantic capture, closure, candidate generation, semantic proof,
backend refinement, differential execution, physical benchmark, source rewrite, and protocol proof
as independent capabilities.

#### Scenario: External protocol does not erase local closure
- **WHEN** a function contains an independently closed region and an unsupported external boundary
- **THEN** the adapter SHALL expose the local region and separately name the blocked whole-function
  claim and required adapter.
