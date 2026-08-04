## ADDED Requirements

### Requirement: Diagnostic Isolation

Diagnostic variants SHALL retain declared access or arithmetic structure, expose a
dependency-preserving sink, document distortions, and remain ineligible for ranking.

#### Scenario: Decode-only measurement

- **GIVEN** the unpack-only variant
- **WHEN** it is measured
- **THEN** its altered load ordering and missing dot overlap are reported with the result.

### Requirement: Non-Additive Attribution

SiliconTune SHALL distinguish inclusive runtime, marginal or elimination-envelope cost,
and approximate critical-path contribution.

#### Scenario: Overlapping stages

- **GIVEN** unpack and dot work that overlap in the native schedule
- **WHEN** attribution is reported
- **THEN** their diagnostic runtimes are not summed as physical stage time.
