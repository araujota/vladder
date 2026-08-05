## ADDED Requirements

### Requirement: Immutable canonical experience schema
The system SHALL store semantic roots, structured grammar actions, candidates, and evaluation
observations with deterministic identities, schema/grammar/compiler/hardware/workload provenance,
artifact hashes, exactness, and evidence quality.

#### Scenario: Source-language clones
- **WHEN** equivalent C, C++, Rust, Zig, and Julia regions normalize to the same semantic graph and contract
- **THEN** they share one semantic root identity while retaining distinct provenance records

#### Scenario: Weak physical evidence
- **WHEN** an observation lacks physical measurement or has quality grade D
- **THEN** it is excluded from physical-ranker labels but remains available to semantic recognizers

### Requirement: Leakage-safe grouping
The system SHALL group all candidates and observations of one root together and SHALL reject
candidate-level splits or overlapping root/project holdouts.

#### Scenario: Candidate leakage
- **WHEN** two candidates from one root occur in different partitions
- **THEN** dataset validation fails with the root and partitions identified

### Requirement: Open grammar vocabulary
The training-data boundary SHALL preserve unknown typed semantic node/edge fields and structured
grammar actions without requiring a core schema change. Action descriptors SHALL identify family,
family version, primitives, parameters, and namespaced extensions. Canonical outcome labels SHALL
remain stable across grammar expansion.

#### Scenario: Future grammar family
- **WHEN** a template contains a previously unseen node class, edge relation, action primitive, or namespaced parameter payload
- **THEN** materialization retains it in deterministic identity and model features without treating it as proof or accepting a new outcome class
