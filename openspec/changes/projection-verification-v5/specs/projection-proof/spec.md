## ADDED Requirements

### Requirement: Exact Weight Layout Bijection

Every exact transformed weight layout SHALL map each original opaque quantized block
to exactly one destination and define an auditable inverse.

#### Scenario: Sibling interleave

- **GIVEN** equal-format sibling matrices and a deterministic interleave
- **WHEN** verification runs
- **THEN** the map is bijective, inverse bytes equal source bytes, and all hashes are retained.

### Requirement: Exact Track Isolation

Exact and tolerance-gated candidates SHALL be ranked and reported separately.

#### Scenario: Changed accumulation order

- **GIVEN** a zero-error accumulation contract
- **WHEN** a candidate reorders floating-point accumulation
- **THEN** it is rejected from the exact track.
