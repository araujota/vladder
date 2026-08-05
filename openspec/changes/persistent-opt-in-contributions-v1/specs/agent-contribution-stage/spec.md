## ADDED Requirements

### Requirement: Non-Executing Optional Workflow Stage

Canonical agent and learned-search workflows SHALL report the contribution decision and next
action without automatically transmitting data.

#### Scenario: Opted in

- **WHEN** a workflow completes with saved opt-in
- **THEN** its summary classifies contribution as available but not executed
- **AND** the exact payload still requires preview and per-submission gates.

#### Scenario: Opted out

- **WHEN** a workflow completes with saved opt-out
- **THEN** its summary classifies contribution as disabled by the user
- **AND** the agent does not ask again unless the user explicitly requests reconsideration.
