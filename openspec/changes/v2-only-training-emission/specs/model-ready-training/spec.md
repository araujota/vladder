## MODIFIED Requirements

### Requirement: All training emission is graph-ready

The packaged vLadder runtime SHALL emit only `vladder-model-training-bundle-v2` for canonical
training contributions.

#### Scenario: Terminal workflow contribution

- **WHEN** an opted-in workflow reaches a terminal promotion summary
- **THEN** vLadder SHALL emit roots with bounded topology, structured candidates, and typed
  observations
- **AND** SHALL submit the record to `/api/training/v2`.

#### Scenario: Historical v1 artifact

- **WHEN** a v1 artifact is inspected
- **THEN** schema validation MAY identify it as a historical valid artifact
- **BUT** enqueue and submission SHALL reject it.

### Requirement: Baseline preservation

Every terminal model-training bundle SHALL contain a baseline candidate and SHALL not imply that a
generated candidate exists when candidate generation did not occur.

#### Scenario: Workflow ends before candidate generation

- **WHEN** semantic capture terminates without generating an alternative
- **THEN** the v2 bundle SHALL contain the existing implementation as its baseline candidate
- **AND** SHALL contain no fabricated non-baseline candidate.
