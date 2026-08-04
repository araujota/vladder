## ADDED Requirements

### Requirement: C Reconstruction From Selected Graph

SiliconTune SHALL generate human-readable C from the selected graph and schedule,
not only from hand-written templates.

#### Scenario: Pointwise C lift

- **GIVEN** a selected pointwise graph
- **WHEN** C lifting runs
- **THEN** `optimized.c` preserves the original function signature
- **AND** emits a loop implementing the selected graph
- **AND** records any assumptions such as no-alias or target ISA.

### Requirement: Readability Guard

Generated C SHALL prefer readable scalar C unless the selected grammar rule
requires intrinsics for performance.

#### Scenario: Intrinsic winner

- **GIVEN** an AVX2 candidate wins
- **WHEN** C lifting emits source
- **THEN** the output includes required headers and reports target ISA
  preconditions.

### Requirement: Zero-Trust LLM Reconstruction

SiliconTune MAY use an LLM to propose readable C from a selected graph or
bounded SMT semantic relation, but SHALL treat the proposal as untrusted input.

#### Scenario: LLM proposal admitted

- **GIVEN** a DeepSeek proposal with the required function signature
- **WHEN** zero-trust reconstruction runs
- **THEN** the proposal is syntax checked and screened for forbidden operations
- **AND** its canonical graph and constants match the selected semantic graph
- **AND** its registered SMT obligation passes before runtime verification
- **AND** differential testing still runs before ranking.

#### Scenario: LLM proposal rejected with feedback

- **GIVEN** a proposal that fails parsing, compilation, graph matching, or proof
- **WHEN** verifier feedback is available and the retry budget remains
- **THEN** diagnostics are sent to the next proposal round
- **AND** the rejected source is never benchmarked or emitted as the patch.

#### Scenario: Provider credential unavailable

- **GIVEN** `DEEPSEEK_API_KEY` is absent
- **WHEN** LLM reconstruction is requested
- **THEN** the report records `unavailable` without exposing credentials
- **AND** deterministic graph-AST lifting continues.
