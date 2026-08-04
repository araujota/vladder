## ADDED Requirements

### Requirement: KernelGraph

SiliconTune SHALL represent quantized projection realization as an immutable typed graph
below ProjectionComplexGraph.

#### Scenario: Shared-input FFN lowering

- **GIVEN** a gate/up ProjectionComplexGraph
- **WHEN** kernel lowering runs
- **THEN** activation, weight, dot, consumer, physical metadata, and source graph hash are retained.

### Requirement: Hierarchical Search

Search SHALL compose only admitted and legal rules, retain all rejection reasons, and
report either a saturated local region or `best_verified_found`.

#### Scenario: Exact accumulation contract

- **GIVEN** a rule that changes accumulation order under an exact contract
- **WHEN** legality runs
- **THEN** the rule is rejected before generation.

#### Scenario: Bounded beam

- **GIVEN** a Pareto frontier larger than the beam
- **WHEN** composition proceeds
- **THEN** the result is classified `best_verified_found`, not saturated.

### Requirement: Executable Kernel Realizations

Retained physical candidates SHALL compile and execute under a standalone verifier before
they may receive measured status.

#### Scenario: Synthetic exact kernel

- **GIVEN** packed signed nibbles and bounded int8 activations
- **WHEN** decode, accumulator, and sibling traversal variants run
- **THEN** every int64 output matches the reference before timing.
