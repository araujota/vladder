## ADDED Requirements

### Requirement: Ceiling Epistemic Status

The report SHALL distinguish measured cost, elimination envelopes, reducibility
hypotheses, demonstrated recoverability, and candidate speedup.

#### Scenario: Large optimistic envelope

- **GIVEN** overlapping diagnostics whose optimistic composition exceeds ten percent
- **WHEN** no schedule-preserving candidate has reduced those stages
- **THEN** ten-percent headroom is reported as uncertain, not established.

### Requirement: Evidence-Gated Grammar

A production grammar family SHALL be admitted only when attribution, plausible value,
semantic tractability, and distinctness criteria pass.

#### Scenario: Activation reuse after V7

- **GIVEN** less than two percent activation-side marginal cost and a rejected V7 transfer
- **WHEN** V8 makes its grammar decision
- **THEN** sibling activation reuse remains rejected.
