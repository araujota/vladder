## ADDED Requirements

### Requirement: Advisory search ordering
The learned prior SHALL only order already enumerated candidates and SHALL NOT establish legality,
equivalence, physical speed, or promotion.

#### Scenario: High score with failed proof
- **WHEN** a top-ranked candidate fails deterministic proof
- **THEN** it is rejected exactly as it would be without the model

### Requirement: Baseline and exploration guarantees
Every budgeted selection SHALL include the baseline and reserve a configured fraction for random,
underrepresented, high-uncertainty, or OOD candidates.

#### Scenario: Baseline ranks last
- **WHEN** the model assigns the baseline the lowest score
- **THEN** the baseline remains in the selected physical set

#### Scenario: Model abstains
- **WHEN** abstention is required
- **THEN** the existing exhaustive or heuristic search executes and the observation is retained

### Requirement: Immutable decision audit
Each model-guided decision SHALL record model/dataset hashes, inputs, full ranking, selected and
deferred candidates, exploration reasons, budget, abstention, and deterministic fallback.

#### Scenario: Repeated decision
- **WHEN** the same model, root, candidates, budget, and seed are evaluated twice
- **THEN** the decision records have the same content hash and selection order
