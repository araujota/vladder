# Composition-Native Search Requirements

## ADDED Requirements

### Requirement: Native state and frontier capture

Every exhaustive composition decision SHALL record the exact parent state, ordered history, complete
legal sibling set, child-state preview or exact delta, and canonical state hash at enumeration time.

#### Scenario: Sibling interaction trace

- **GIVEN** a parent with four legal composition actions
- **WHEN** the frontier is scored
- **THEN** one native record contains all four actions and their deltas before any action is expanded.

### Requirement: Explicit interaction semantics

Symbolically known enable, disable, conflict, commutativity, contract, lifetime, authority,
materialization, memory, owner, and cross-TU relations SHALL be encoded explicitly.

#### Scenario: Three-action enablement

- **GIVEN** a realization enabled only by three prior transformations
- **WHEN** its interaction graph is emitted
- **THEN** a factor node connects all three transformations to the enabled realization.

### Requirement: Outcome isolation

Terminal status, descendant utility, distance, retained status, and actual subtree cost SHALL be
unavailable to inference tensorization.

#### Scenario: Relabel identical frontier

- **GIVEN** two copies of one inference record with different post-search outcomes
- **WHEN** model inputs are constructed
- **THEN** their inference tensors are identical.

### Requirement: Exact authority precedes ML

Exact canonicalization, deterministic impossibility, and formally verified equivalence or dominance
SHALL precede learned ordering and SHALL be reported separately.

#### Scenario: Commutative paths converge

- **GIVEN** two action sequences with the same canonical semantic state
- **WHEN** the second child is generated
- **THEN** it is collapsed as a transposition without an ML deletion decision.

### Requirement: Tiered contextual labels

Completed traces SHALL propagate U0-U4 descendant utility, distance, discovery cost, redundancy,
and sibling-relative advantage from terminals to every ancestor action.

#### Scenario: Unhelpful ancestor reaches winner

- **GIVEN** an action with no direct utility whose descendant is retained
- **WHEN** labels are generated
- **THEN** the action receives U4 descendant utility and is preferred to exhausted siblings.

### Requirement: Canonical terminal ownership

Terminal outcomes SHALL attach to the unique canonical owner of their semantic state, and a corpus
audit SHALL reject outcomes attached to an exact transposition duplicate.

#### Scenario: Terminal reached through two action orders

- **GIVEN** two action sequences converge on one terminal semantic state
- **WHEN** the terminal is evaluated once by semantic identity
- **THEN** its proof, compiler, benchmark, and cost evidence is attached to the canonical owner and
  both ancestor paths receive descendant utility through canonical lineage.

### Requirement: Faithful online replay

Online replay SHALL retain every native frontier, including singleton frontiers that provide no
pairwise or listwise training example.

#### Scenario: Ranked action followed by mandatory transition

- **GIVEN** a scored composition action whose child has exactly one legal successor
- **WHEN** replay expands that child
- **THEN** the successor inherits the active branch priority and remains reachable before the next
  ranked frontier or terminal.

### Requirement: Composition-native evaluation

Evaluation SHALL use project-held-out online replay and SHALL report terminal recovery against actual
search cost at 1, 5, 10, 20, 30, 50, and 100 percent.

#### Scenario: Gate A

- **GIVEN** a held-project composition corpus
- **WHEN** the full model consumes 30 percent of exhaustive work
- **THEN** composition recovery is compared to the 80 percent gate and Phase-A GPS baseline.

### Requirement: Learned ordering only

Learned outputs SHALL rank, defer, propose checks, and allocate finite budgets but SHALL NOT prove or
permanently delete semantic possibilities.

#### Scenario: Exhaustive fallback

- **GIVEN** a lowest-ranked legal branch
- **WHEN** exhaustive mode runs without an exact closure
- **THEN** the branch remains reachable and is eventually explored.
