## ADDED Requirements

### Requirement: Operator Optimization CLI

SiliconTune SHALL expose operator analysis/optimization using source, contract,
target, grammar, and objective inputs.

#### Scenario: Complete operator run

- **GIVEN** valid source, contract, target, and grammar
- **WHEN** `silicontune operator optimize` runs
- **THEN** it emits optimized source/patch, before/after graphs, grammar
  derivation, proof/test artifacts, IR/assembly, performance data, search audit,
  confidence intervals, and a source-level explanation.

### Requirement: Pipeline Replay CLI

SiliconTune SHALL expose manifest-driven pipeline optimization with separate
tuning and held-out traces.

#### Scenario: Missing held-out replay

- **GIVEN** an HFT pipeline manifest and tuning trace only
- **WHEN** `pipeline optimize` runs
- **THEN** it may search but cannot emit an accepted winner.

### Requirement: Bounded Report Claim

Reports SHALL distinguish saturated and unsaturated regions and SHALL NOT claim
global optimality.

#### Scenario: Mixed search completion

- **GIVEN** saturated region X and budget-exhausted regions Y and Z
- **WHEN** the report is generated
- **THEN** it says best measured verified in X and best-found in Y/Z for named
  target, workload, contract, grammar, and proof policy.

### Requirement: Acceptance Evidence Matrix

System completion, standalone performance, production integration, and domain
acceptance SHALL be reported as separate statuses.

#### Scenario: Standalone token win only

- **GIVEN** two standalone operators improve without llama.cpp model integration
- **WHEN** acceptance is evaluated
- **THEN** standalone criteria may pass but production token acceptance remains open.
