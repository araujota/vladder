## ADDED Requirements

### Requirement: Authoritative optimization entry point
The system SHALL provide one `vladder optimize` entry point that classifies a production region,
emits an authoritative plan, delegates to existing specialized executors, and preserves all proof
and promotion gates.

#### Scenario: Existing bounded C invocation
- **WHEN** a user invokes the existing C source and function form
- **THEN** the orchestrator delegates to the existing bounded-C optimizer
- **AND** preserves its candidate, proof, benchmark, and patch artifacts
- **AND** adds a concise terminal disposition without weakening exit compatibility

#### Scenario: Plan-only inspection
- **WHEN** the user requests plan-only operation
- **THEN** no candidate compilation, proof, benchmark, contribution, or source write occurs
- **AND** the plan names every delegated command and required evidence input

### Requirement: Early reachability and cost forecast
Before expensive execution, the system SHALL estimate the first unreachable evidence state,
required dependencies, runtime range, artifact volume, and probability of reaching each evidence
state.

#### Scenario: Missing application oracle
- **WHEN** local extraction and proof are reachable but no complete application observable exists
- **THEN** the forecast identifies application integration as the first unreachable state
- **AND** emits an oracle scaffold and executable next command

### Requirement: Resumable content-addressed stages
The system SHALL key discovery, classification, feasibility, execution, and disposition stages by
their actual inputs and resume from the first invalid stage.

#### Scenario: Workload-only change
- **WHEN** source and extraction inputs are unchanged but the workload manifest changes
- **THEN** semantic capture is reused
- **AND** physical and composed evidence stages are invalidated

### Requirement: Repository portfolio mode
The system SHALL inventory, prioritize, deduplicate, and execute multiple regions with one campaign
summary.

#### Scenario: Duplicate semantic owners
- **WHEN** multiple source selections canonicalize to the same semantic root
- **THEN** the campaign evaluates the root once
- **AND** records every owning source region in lineage

### Requirement: Structured progress and stopping policy
Long-running orchestration SHALL emit structured phase, percent, elapsed time, estimated remaining
time, current blocker, and artifact events, and SHALL terminate with `CONTINUE`, `STOP`, or
`ESCALATE` guidance.

#### Scenario: Low expected value
- **WHEN** the forecasted recoverable composed effect is below the declared floor and proof cost is high
- **THEN** the recommendation is `STOP`
- **AND** the system records the negative evidence instead of silently abandoning the region
