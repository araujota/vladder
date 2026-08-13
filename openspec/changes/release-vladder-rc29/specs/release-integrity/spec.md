# Release Integrity Specification

## ADDED Requirements

### Requirement: Installed search evidence

The distribution SHALL contain a schema-validated artifact binding its release version to the
production canonical-search engine, authority model, qualification metrics, and training contract.

#### Scenario: Wheel omits qualification evidence

- **WHEN** the built wheel is installed and the evidence command runs
- **THEN** release validation SHALL fail before publication

### Requirement: Training-ready native traces

The native trace emitter SHALL reject inconsistent canonical ownership, lineage, sibling frontier,
action labels, terminal ownership, summary counts, or trace hashes and SHALL state whether the
trace is eligible for future policy training.

#### Scenario: A sibling action is missing

- **WHEN** frontier cardinality differs from the available action set
- **THEN** integrity validation SHALL fail and the trace SHALL NOT enter policy training

### Requirement: No outcome leakage

The inference projection SHALL exclude all facts learned only after the search decision.

#### Scenario: A completed trace is projected for inference

- **WHEN** the inference view is built
- **THEN** future states, transpositions, selected actions, terminal outcomes, labels, and measured
  costs SHALL be absent

### Requirement: Unified release identity

The repository, wheel, agent skill, website, Git tag, GitHub release, and PyPI release SHALL identify
the same rc29 version.

#### Scenario: Publication channel differs

- **WHEN** one channel reports a different version or source identity
- **THEN** the release SHALL remain incomplete
