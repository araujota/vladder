## ADDED Requirements

### Requirement: Fail-Closed Active Path Manifest

SiliconTune SHALL rank no Q4_K candidate unless runtime capture matches the declared
decode kernel, repack, activation type, row grouping, dimensions, and hardware manifest.

#### Scenario: Unexpected runtime dispatch

- **GIVEN** a manifest declaring `ggml_gemv_q4_K_8x8_q8_K`
- **WHEN** a representative one-row projection selects another symbol
- **THEN** capture fails before reconstruction or benchmarking.

### Requirement: Source and Model Provenance

The manifest SHALL retain the pinned commit, source ranges and hashes, compiler command,
binary symbols and hashes, model hash, and tensor categories.

#### Scenario: Reproducible capture

- **GIVEN** a successful Qwen capture
- **WHEN** its manifest is audited
- **THEN** the active source, model, build, and target configuration are identifiable.
