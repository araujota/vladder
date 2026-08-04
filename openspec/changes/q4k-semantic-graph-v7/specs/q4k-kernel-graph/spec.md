## ADDED Requirements

### Requirement: Production Block Semantics

SiliconTune SHALL model Q4_K packed values, scales, minima, sub-blocks, Q8_K values and
block sums, correction terms, output rows, block order, and tails.

#### Scenario: Metadata boundary values

- **GIVEN** all six-bit scale and minimum boundary combinations
- **WHEN** packing and decoding are composed
- **THEN** every value is reconstructed exactly.

### Requirement: Exact Layout Audit

Every admitted Q4_K layout SHALL have a deterministic inverse and preserve all source
bytes except explicitly uninterpreted padding.

#### Scenario: Native eight-row repack

- **GIVEN** eight native Q4_K blocks
- **WHEN** they are repacked and inversely reconstructed
- **THEN** the canonical source stream and hash are identical.

### Requirement: Graph Provenance

Every node SHALL reference a baseline source expression, baseline intrinsic, baseline
assembly region, generated grammar rule, or verified helper.

#### Scenario: Candidate audit

- **GIVEN** a generated sibling graph
- **WHEN** a reviewer inspects its operations
- **THEN** every node has one valid provenance class and exactness obligation.
