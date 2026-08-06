# Contribution Capability Requirements

## ADDED Requirements

### Requirement: Fresh-install credentials

A fresh installation SHALL obtain an opaque credential at first opted-in contribution use without
requiring a packaged shared secret.

#### Scenario: First training contribution

- **GIVEN** canonical training contribution is durably opted in
- **WHEN** no credential exists for the configured endpoint
- **THEN** the client obtains and owner-protects a `training:write` capability before submission

### Requirement: Least privilege

A contributor capability SHALL authorize only its declared append scope and SHALL NOT authorize
private reads, moderation, existing-record mutation, internal Convex functions, or deployment APIs.

#### Scenario: Cross-scope use

- **WHEN** a `training:write` credential is presented to the review endpoint
- **THEN** the request is rejected without storing a record

### Requirement: No embedded secret

Release artifacts SHALL contain the public service URL but SHALL NOT contain contributor, trusted
ingestion, moderation, or Convex deployment credentials.

#### Scenario: Clean installation artifact

- **WHEN** a wheel or source archive is inspected
- **THEN** it contains a public endpoint and no bearer or deployment credential

### Requirement: Independent gates

Credential possession SHALL NOT bypass durable consent, record-level consent, schema/privacy
validation, payload limits, rate limits, idempotency, or moderation.

#### Scenario: Credential without consent

- **GIVEN** an installation has a valid append capability but durable consent is absent
- **WHEN** contribution is attempted through the vLadder client
- **THEN** the client fails before transmitting the record
