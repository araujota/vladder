## ADDED Requirements

### Requirement: Reproducible Pipeline Workflow

The V4 CLI SHALL analyze, search, verify, benchmark, integrate, and report using
content-addressed inputs and resumable stages.

#### Scenario: Completed Qwen run

- **GIVEN** a pinned Qwen model, llama.cpp build, pipeline manifest, grammar, and target
- **WHEN** `silicontune pipeline optimize-v4` completes
- **THEN** graph, derivation, proofs, raw measurements, attribution, patch, and report
  artifacts are emitted.

### Requirement: Evidence-Bounded Language

Reports SHALL distinguish implemented functionality, verified candidates, research
milestones, commercial milestones, and long-term targets.

#### Scenario: Confidence interval crosses zero

- **GIVEN** a positive point estimate whose interval includes zero
- **WHEN** acceptance is evaluated
- **THEN** the result is a statistical tie and no speedup milestone is claimed.

### Requirement: Information-Flow Visualization

Reports SHALL emit machine-readable and visual before/after graphs with materialized,
streamed, state, and external edges visibly distinct.

#### Scenario: Fused pipeline

- **GIVEN** a selected candidate removes a temporary
- **WHEN** visualization is emitted
- **THEN** the derivation and removed edge remain auditable rather than disappearing.
