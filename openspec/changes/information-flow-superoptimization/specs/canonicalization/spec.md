## ADDED Requirements

### Requirement: Canonical Graph Forms

SiliconTune SHALL normalize equivalent surface forms into canonical graph forms
before grammar search.

Initial canonicalizations:

- branch/select normalization where exact
- compare/select clamp normalization
- affine expression normalization
- exact power-of-two division normalization
- loop induction normalization

#### Scenario: Clamp normalization

- **GIVEN** a branchy clamp and a select-based clamp
- **WHEN** canonicalization runs
- **THEN** both normalize to the same saturating projection graph.

### Requirement: Exactness Policy

Canonicalization SHALL preserve exact C/LLVM floating-point behavior unless a
candidate explicitly opts into a relaxed-FP grammar.

#### Scenario: Reject inexact reciprocal

- **GIVEN** `x / 3.0f`
- **WHEN** exact canonicalization runs
- **THEN** it SHALL NOT rewrite the operation as `x * 0.33333334f`.
