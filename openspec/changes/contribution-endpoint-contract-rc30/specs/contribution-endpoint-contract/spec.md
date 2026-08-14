# Contribution Endpoint Contract

## ADDED Requirements

### Requirement: Side-effect-free compatibility descriptor

The contribution service SHALL expose a health descriptor containing a versioned endpoint
contract, accepted contribution schemas, and canonical submission routes.

#### Scenario: Compatible deployed service

- **WHEN** a client requests `/api/health`
- **THEN** the service returns the endpoint-contract version, review schema, training schema,
  review submission route, training submission route, and capability status
- **AND** the request creates no capability or contribution record.

### Requirement: Client compatibility gate

The client SHALL validate the deployed endpoint contract before registering a capability or
submitting a contribution.

#### Scenario: Stale deployment

- **WHEN** the service advertises an older training schema or omits the required route
- **THEN** the client fails before payload upload with an actionable incompatibility error
- **AND** it does not report the contribution as submitted or remotely validated.

### Requirement: Release compatibility gate

Online release readiness SHALL require the configured production service to match the package's
endpoint contract.

#### Scenario: Healthy but incompatible service

- **WHEN** the health endpoint returns status `ok` but advertises a different schema or route
- **THEN** formal release readiness fails and identifies the expected and observed contract.

### Requirement: Deployed route verification

Release verification SHALL test route presence and scoped authorization against the deployed
service without storing a schema-valid contribution.

#### Scenario: Matching deployment

- **WHEN** the contribution doctor runs against a compatible service
- **THEN** required v3 and review routes reach authorization/schema handling
- **AND** retired routes retain their declared 410 behavior
- **AND** the report records zero stored contributions.
