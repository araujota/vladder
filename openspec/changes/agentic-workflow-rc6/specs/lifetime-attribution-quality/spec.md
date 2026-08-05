## ADDED Requirements

### Requirement: Trace sufficiency gate
vLadder SHALL score lifetime traces before grammar expansion and SHALL emit no candidates when the
trace cannot support meaningful cost or reuse attribution.

#### Scenario: One construct event only
- **WHEN** an item has no consumer, invalidator, scope diversity, or residency evidence
- **THEN** synthesis SHALL return `insufficient_attribution` with missing evidence listed

### Requirement: Semantic authority separation
Trace sufficiency SHALL never convert observed non-mutation into a semantic invariant.

#### Scenario: Many repeated reads without mutation
- **WHEN** a trace shows stable values but the manifest omits mutation classification
- **THEN** lifetime extension SHALL remain illegal regardless of trace score
