## Purpose

Prevent generated source rewrites from being promoted unless their semantics and measured behavior satisfy an explicit, auditable verification contract.

## ADDED Requirements

### Requirement: Layered verification policy
The system SHALL support structural legality, undefined-behavior screening, differential tests, SMT obligations, LLVM translation validation, and performance confirmation as distinct gates.

#### Scenario: Candidate fails one required layer
- **WHEN** any verification layer required by the contract fails, times out, or is unavailable
- **THEN** the candidate is not eligible for selection or source replacement

### Requirement: Source and IR correspondence
The system SHALL compile regenerated source and validate the resulting candidate IR against the declared reference IR before treating the source rewrite as equivalent.

#### Scenario: Source reconstruction changes lowering
- **WHEN** regenerated source compiles to IR that fails Alive2 translation validation
- **THEN** the source rewrite is rejected even if bounded differential tests passed

### Requirement: Explicit proof scope
Every proof artifact SHALL state its modeled domain, assumptions, timeout, solver or validator version, result, and unsupported semantics.

#### Scenario: Bounded SMT proof
- **WHEN** Z3 proves a fixed-width or bounded-memory obligation
- **THEN** the report labels it as bounded and does not generalize the result beyond the encoded domain

### Requirement: Patch promotion gate
The system SHALL emit a promotable patch only when the winner satisfies the selected proof policy and a statistically supported performance threshold.

#### Scenario: Baseline remains fastest
- **WHEN** no fully verified candidate exceeds the minimum effect threshold
- **THEN** the result reports no promoted replacement and preserves the original source
