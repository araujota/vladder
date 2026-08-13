# Contextual Best-First Search Requirements

## ADDED Requirements

### Requirement: Learned ordering cannot delete

The learned policy SHALL assign expansion priority only and SHALL NOT establish semantic pruning,
dominance, equivalence, or contract impossibility.

#### Scenario: Low-ranked branch in exhaustive mode

- **GIVEN** a legal branch with the lowest learned score
- **WHEN** exhaustive search runs
- **THEN** the branch is eventually expanded unless a deterministic or formally verified authority closes it.

### Requirement: Joint frontier context

The policy SHALL score every legal sibling action relative to the same parent state, history, and
frontier snapshot.

#### Scenario: Same action under different history

- **GIVEN** two locally identical actions reached by different transformation histories
- **WHEN** the policy scores their frontiers
- **THEN** history is represented explicitly and may change their relative priority.

### Requirement: Outcome isolation

Distance to utility, descendant outcomes, exhaustive subtree cost, and redundancy outcomes SHALL be
supervision only.

#### Scenario: Tensorize an inference decision

- **GIVEN** identical parent/frontier contexts with different post-search outcomes
- **WHEN** inference tensors are built
- **THEN** those tensors are identical.

### Requirement: Exact transposition precedence

Exact canonical state identity and formally verified equivalence SHALL be applied before learned
ordering and SHALL be reported separately from budget savings.

#### Scenario: Commutative actions reach one state

- **GIVEN** two action sequences with one canonical semantic-state hash
- **WHEN** the second state is generated
- **THEN** it aliases the first state without invoking an ML deletion decision.

### Requirement: Recovery-curve evaluation

Held-project evaluation SHALL replay online frontier creation and report useful discovery at fixed
fractions of exhaustive direct work.

#### Scenario: Thirty-percent budget

- **GIVEN** an exhaustive held-project trace
- **WHEN** guided replay consumes 30% of its direct work
- **THEN** the report states useful-terminal and retained-terminal recovery, tool calls, and maximum frontier size.
