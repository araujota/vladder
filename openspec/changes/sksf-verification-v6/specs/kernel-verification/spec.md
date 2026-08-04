## ADDED Requirements

### Requirement: Fail-Closed Verification

SiliconTune SHALL assign every proof obligation an explicit pass, fail, or unsupported
state and SHALL not rank candidates with fail or unsupported required obligations.

#### Scenario: Unsupported LLVM memory proof

- **GIVEN** a transformation outside Alive2's validated boundary
- **WHEN** translation validation runs
- **THEN** the obligation remains unsupported and another required proof layer must discharge it.

### Requirement: Exact and Tolerance Separation

Exact and tolerance-bounded model tracks SHALL remain separate in artifacts and claims.

#### Scenario: Exact generated tokens

- **GIVEN** a fixed model, prompt, seed, and exact contract
- **WHEN** model verification runs
- **THEN** logits follow the declared exact policy and every generated token is identical.

### Requirement: Untrusted Source Reconstruction

LLM-generated C or C++ SHALL have no proof authority.

#### Scenario: LLM proposes a candidate

- **GIVEN** reconstructed human-readable source
- **WHEN** it enters SKSF
- **THEN** the same structural, semantic, model, and stateful gates apply without weakening.
