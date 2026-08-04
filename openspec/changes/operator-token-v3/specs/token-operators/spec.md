## ADDED Requirements

### Requirement: Pinned Production Baseline

Token-generation claims SHALL name an exact llama.cpp commit, build options,
kernel source, model/tensor contract, and benchmark adapter.

#### Scenario: Upstream fused baseline exists

- **GIVEN** pinned llama.cpp provides fused RMSNorm+multiply
- **WHEN** residual/RMSNorm optimization is evaluated
- **THEN** the upstream fused path is included where semantically comparable
- **AND** an unfused toy baseline is not labeled production.

### Requirement: Five Decode Operator Families

SiliconTune SHALL support RMSNorm fusion, RoPE Q/K, bounded quantized GEMV
epilogue, restricted decode attention, and logit/sampling operators.

#### Scenario: Operator artifact completeness

- **GIVEN** a token operator optimization
- **WHEN** it completes
- **THEN** tensor metadata, graph, derivation, proof/error report, assembly,
  counters, and traffic delta are emitted.

### Requirement: Numerical Adversaries

Token verification SHALL cover extreme finite values, declared NaN/Inf policy,
quantization boundaries, context buckets, and long-run error drift.

#### Scenario: Approximate reciprocal square root

- **GIVEN** an approximate RMSNorm candidate
- **WHEN** exact mode is selected
- **THEN** the candidate is disallowed before benchmarking.

### Requirement: Sampling Reproducibility

Stochastic sampling candidates SHALL preserve the declared seed, random-number
consumption order, and selected-token semantics.

#### Scenario: Early-rejection RNG change

- **GIVEN** a fast path that consumes fewer random values
- **WHEN** the contract requires exact seed semantics
- **THEN** the candidate is rejected even if output distributions look similar.

### Requirement: Integrated Evidence Boundary

Synthetic wins SHALL NOT satisfy production acceptance without a pinned
llama.cpp integration and contract-compliant outputs.

#### Scenario: Model artifact unavailable

- **GIVEN** no model checksum is configured
- **WHEN** standalone operators improve
- **THEN** the report labels results standalone and leaves model-level criteria open.

#### Scenario: Model artifact available

- **GIVEN** a compatible local model artifact exists
- **WHEN** an integrated token candidate is evaluated
- **THEN** SiliconTune records the model format, parameter count, byte size, and SHA-256
- **AND** measures prompt and decode tokens per second in randomized independent processes
- **AND** compares deterministic generated output under the declared seed semantics
- **AND** classifies effects whose confidence interval includes zero as statistical ties.
