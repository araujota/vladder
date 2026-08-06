# Cross-TU Semantic Closure Requirements

## ADDED Requirements

### Requirement: Build-Wide Definition Identity

The system SHALL index exact translation-unit commands, source files, output objects, definitions,
and references and SHALL fail closed on ambiguous definition identity.

#### Scenario: Unique project helper

- **WHEN** a selected function directly calls a symbol with one project definition
- **THEN** the call is represented as a cross-TU definition edge with hash-bound provenance

#### Scenario: Ambiguous ODR definition

- **WHEN** multiple definitions cannot be shown equivalent
- **THEN** the edge remains an explicit non-crossable boundary

### Requirement: Demand-Driven Closure

The system SHALL materialize summaries only for a bounded slice and SHALL NOT add summaries or
protocol states to computational candidate cardinality.

#### Scenario: Large build

- **WHEN** a seed is analyzed in a build containing unrelated translation units
- **THEN** only units required by configured upstream/downstream budgets are materialized

### Requirement: Bidirectional Information Flow

The system SHALL represent both downstream consumers/callees and upstream producers/callers,
including explicit approximation provenance for object-level caller candidates.

#### Scenario: Caller and callee neighborhood

- **WHEN** bounded upstream and downstream depths are requested
- **THEN** direct caller and callee edges are emitted with precision and depth provenance

### Requirement: Ownership Closure

The system SHALL classify construction, borrowing, mutation, publication, transfer, invalidation,
retirement, and unknown ownership boundaries and SHALL not claim local ownership closure when an
owner or retirement action is absent.

#### Scenario: Allocation leaves the selected slice

- **WHEN** a resource is constructed but its transfer or retirement is outside the slice
- **THEN** an explicit ownership contract boundary is emitted

### Requirement: Compositional Proof

The system SHALL emit machine-checkable obligations for definition resolution, summary provenance,
edge disposition, transitive effects, ownership closure, and search-space separation.

#### Scenario: Proved closed slice

- **WHEN** all finite composition obligations are valid
- **THEN** Z3 artifacts and a passing bounded-closure report are emitted

### Requirement: Honest Boundaries

The system SHALL preserve arbitrary callbacks, unresolved virtual dispatch, third-party APIs,
syscalls, driver/runtime behavior, and undeclared concurrent protocols as explicit boundaries while
allowing neighboring closed subgraphs to proceed.

#### Scenario: Indirect callback

- **WHEN** a finite callback target set is unavailable
- **THEN** the callback remains non-crossable while other closed functions remain usable

### Requirement: Read-Only Evaluation

The NeuralFusion acceptance run SHALL place all generated artifacts outside the project and SHALL
not modify source, build metadata, or tracked worktree state.

#### Scenario: External project audit

- **WHEN** a closure run targets NeuralFusion
- **THEN** all generated artifacts are written outside its repository and source changes are false
