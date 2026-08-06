## ADDED Requirements

### Requirement: Consent-Directed Workflow Stage

Canonical agent and learned-search workflows SHALL report the contribution decision and next
action. Unknown and opted-out scopes SHALL NOT transmit data. Training opt-in SHALL execute all
registered anonymized exporters at each eligible opportunity. Review opt-in SHALL only surface a
periodic request when due.

#### Scenario: Opted in

- **WHEN** a workflow completes with saved opt-in
- **THEN** its summary records whether all registered anonymized training exporters completed
- **AND** the agent runs every registered anonymized training exporter without re-prompting
- **AND** exact-record approval remains required only for qualitative review submission.

#### Scenario: Opted out

- **WHEN** a workflow completes with saved opt-out
- **THEN** its summary classifies contribution as disabled by the user
- **AND** the agent does not ask again unless the user explicitly requests reconsideration.
