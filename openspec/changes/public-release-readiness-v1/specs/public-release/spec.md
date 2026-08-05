## ADDED Requirements

### Requirement: Local-First Distribution

The project SHALL provide a one-command Linux install path and SHALL process source, traces,
proofs, and measurements locally unless a user explicitly invokes an upload command.

#### Scenario: Default local workflow

- **WHEN** a user runs any inspect, synthesize, prove, benchmark, or workflow command
- **THEN** no project data is sent to a remote service
- **AND** artifacts are written only to declared local paths.

#### Scenario: Review upload

- **WHEN** a user submits an agent review
- **THEN** the command requires a confirmation flag and record-level consent
- **AND** uses a packaged HTTPS release endpoint unless the user explicitly overrides it
- **AND** validates the payload against the stable review schema before transmission.

### Requirement: Stable Evidence Artifacts

Public evidence artifacts SHALL have versioned JSON Schemas and a compatibility policy.

#### Scenario: Validate artifact

- **WHEN** a user runs schema validation for a registered artifact kind
- **THEN** unknown required fields, missing required fields, invalid enums, and incompatible schema
  versions fail with a nonzero exit status.

### Requirement: Reproducible Release Evidence

The repository SHALL include three small demos, a substantial real-project case study, proof and
benchmark methodology, and a deterministic release-gate report.

#### Scenario: Release gate

- **WHEN** maintainers run the public release gate
- **THEN** each explicit release requirement receives pass, fail, external-gate, or not-run status
- **AND** no aggregate pass conceals a missing requirement.

### Requirement: Quality And Security CI

CI SHALL execute seeded accepted and rejected transformations plus static and security analysis.

#### Scenario: Seeded rejection

- **WHEN** a seeded transformation violates semantics, bounds, or proof requirements
- **THEN** CI passes only if vLadder rejects the transformation with the expected disposition.

### Requirement: Review And Download Surfaces

The project SHALL provide a canonical agent-review format, an optional review backend, and a
simple public website explaining the actual capability and offering release downloads.

#### Scenario: Backend unavailable

- **WHEN** the review backend is not configured
- **THEN** local optimization, local review generation, documentation, and release downloads remain
  functional.
