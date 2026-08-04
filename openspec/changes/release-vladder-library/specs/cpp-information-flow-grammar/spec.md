## Purpose

Define a versioned and auditable optimization vocabulary that covers broad, bounded information-flow concerns in performance-sensitive C and C++ code.

## ADDED Requirements

### Requirement: Broad grammar registry
The release SHALL publish machine-readable grammar families for expressions, control flow, loops, memory and aliasing, reductions and scans, layouts, state, concurrency, specialization, fusion, and hardware scheduling.

#### Scenario: Inspect supported transformations
- **WHEN** a caller lists the release grammar
- **THEN** every family reports its rules, prerequisites, semantic risks, proof strategy, cost signals, and implementation status

### Requirement: Contract-gated legality
Every rewrite rule SHALL declare the language, overflow, floating-point, alias, bounds, side-effect, ordering, concurrency, and hardware facts it requires.

#### Scenario: Missing non-aliasing fact
- **WHEN** a candidate requires non-overlapping pointer regions but the contract does not establish that fact
- **THEN** the candidate is rejected before benchmarking

### Requirement: Honest capability status
The registry SHALL distinguish operational rules from modeled, experimental, and research-only rules.

#### Scenario: Request a modeled-only rule
- **WHEN** a caller requests a family that has no executable lowering
- **THEN** vLadder emits an unsupported-capability result rather than claiming that the family was searched

### Requirement: Versioned derivations
Every candidate SHALL record the grammar version, grammar hash, ordered derivation, and target contract used to generate it.

#### Scenario: Reproduce a derivation
- **WHEN** the same source, contract, target, and grammar hash are supplied
- **THEN** the candidate derivation is reproducible or the report identifies the nondeterministic input
