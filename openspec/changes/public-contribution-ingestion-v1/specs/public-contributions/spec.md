## ADDED Requirements

### Requirement: Explicit Public Contribution

The package SHALL permit an ordinary installation to submit a validated review or source-free
training bundle to the release service without possessing a shared secret.

#### Scenario: No implicit network

- **WHEN** a user runs optimization, proof, benchmark, template, or local validation commands
- **THEN** no contribution request occurs.

#### Scenario: Public submission

- **WHEN** a valid record has record-level consent and the user passes `--confirm-upload`
- **THEN** the release endpoint accepts it for private moderation
- **AND** no credential is required.

### Requirement: Source-Free Training Contract

Training intake SHALL accept only the stable bounded derived-feature schema.

#### Scenario: Source or raw artifact declaration

- **WHEN** a bundle declares source, raw artifacts, prompts, or personal data
- **THEN** local validation fails before network access.

### Requirement: Safe Public Service

The service SHALL bound payload size and request frequency, preserve idempotency, and expose no
unapproved record.

#### Scenario: Remote validation

- **WHEN** a user submits with `--validate-only`
- **THEN** the service validates the exact payload without storing it.
