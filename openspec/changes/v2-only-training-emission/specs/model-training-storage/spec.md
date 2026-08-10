## MODIFIED Requirements

### Requirement: The release service accepts only v2 training records

The production contribution service SHALL retain model-training records only through
`POST /api/training/v2`.

#### Scenario: Legacy client submission

- **WHEN** a client posts to `/api/training`
- **THEN** the service SHALL return `410 Gone`
- **AND** SHALL not store the payload.

#### Scenario: Upgraded outbox contains legacy data

- **WHEN** an upgraded client finds a v1 outbox record
- **THEN** it SHALL quarantine the record locally
- **AND** SHALL not transmit it.

