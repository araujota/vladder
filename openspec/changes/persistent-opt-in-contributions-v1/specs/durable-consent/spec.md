## ADDED Requirements

### Requirement: Durable Independent Decisions

The system SHALL persist independent decisions for canonical training data and agent experience
reviews outside the package installation, with missing state interpreted as unknown.

#### Scenario: Package update or new session

- **WHEN** vLadder or an agent starts after an explicit decision was recorded
- **THEN** the prior decision remains authoritative
- **AND** an opt-out is not reset or repeatedly questioned.

#### Scenario: Unknown state

- **WHEN** no decision exists for one scope
- **THEN** the agent is required to ask the user to explicitly opt in or opt out
- **AND** no network request is made.

### Requirement: Three-Gate Submission

The client SHALL require durable scope opt-in, exact-record consent, and explicit command
confirmation before transmitting a contribution.

#### Scenario: Remote validation

- **WHEN** validate-only is requested without durable opt-in
- **THEN** transmission is rejected because validation still sends payload bytes.
