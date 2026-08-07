## ADDED Requirements

### Requirement: Private immutable v2 ingestion
The contribution service SHALL validate and idempotently store model-ready bundles as private,
moderation-pending records using only a scope-specific append capability.

#### Scenario: Contributor attempts read
- **WHEN** a training contributor sends a GET request to the v2 route
- **THEN** no private training data is returned

#### Scenario: Reused bundle identity
- **WHEN** the same bundle ID is submitted with different content
- **THEN** the service rejects the submission
