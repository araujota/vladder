## ADDED Requirements

### Requirement: Concise evidence disposition
Every terminal workflow SHALL report semantic coverage, candidate generation, proof, physical
measurement, and application integration, plus one explicit terminal status.

#### Scenario: Command succeeds without proof
- **WHEN** extraction succeeds and a candidate exists but no applicable proof passes
- **THEN** the terminal status is `NO_PROOF`
- **AND** successful process execution is not described as an optimization success

### Requirement: Standardized proof badges
Proof evidence SHALL use stable badges with a one-sentence claim boundary and artifact reference.

#### Scenario: Local Alive2 refinement only
- **WHEN** Alive2 proves a bounded local helper but application ownership remains outside the unit
- **THEN** the badge states `LLVM_REFINEMENT_LOCAL`
- **AND** explicitly excludes wrapper and external-protocol equivalence

### Requirement: Normalized actionable failures
Failures SHALL distinguish environment, selection, missing contract, unsupported semantics,
verification rejection, physical regression, and integration failure, and SHALL provide an
argv-form remediation or scaffold-generation action.

#### Scenario: Invalid contract field
- **WHEN** a contract is closest to a known valid schema form
- **THEN** the diagnostic includes a mechanical patch and validation command

### Requirement: Grammar and representativeness qualification
Negative results SHALL include grammar coverage and proof-unit representativeness dimensions.

#### Scenario: Baseline wins in incomplete grammar
- **WHEN** known expert implementation families are not executable in the current grammar
- **THEN** the result is `grammar_limited_negative`
- **AND** no bounded-optimality claim is emitted

### Requirement: Context-sensitive guidance
The default summary SHALL include only applicable mandatory rules, a stable glossary for terms in
the current result, and no unrelated specialist documentation.

#### Scenario: GPU external boundary
- **WHEN** a GPU workflow stops at a driver or output-oracle boundary
- **THEN** the guidance contains the device-runner recipe and proof limitation
- **AND** omits unrelated CPU or lifetime recipes

### Requirement: Campaign reviews
The review workflow SHALL prepopulate objective fields from one or more promotion summaries and ask
the agent only for qualitative assessment fields.

#### Scenario: Multi-workflow campaign
- **WHEN** a campaign review is created from multiple summaries
- **THEN** it records outcomes, proofs, measurements, retained and rejected candidates, and unresolved boundaries across the campaign
- **AND** review submission remains separately consented and explicitly approved
