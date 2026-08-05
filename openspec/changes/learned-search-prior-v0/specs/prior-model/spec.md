## ADDED Requirements

### Requirement: Shared semantic prior
The model SHALL consume canonical graph, structured action, hardware, and workload features. Source
language SHALL be excluded from the primary feature path and retained only for diagnostics.

#### Scenario: Language-independent inference
- **WHEN** two language frontends emit the same canonical root/action/hardware/workload
- **THEN** the primary model produces identical recommendations

### Requirement: Calibrated uncertainty and abstention
The model SHALL report ensemble uncertainty, graph-distance OOD status, calibration identity, and
an abstention decision.

#### Scenario: Unseen hardware capability
- **WHEN** the target requires an ISA or device class absent from training
- **THEN** the model abstains and directs search to the existing heuristic or exhaustive policy

### Requirement: Production-scale gate
The trainer SHALL distinguish pilot readiness from production acceptance and SHALL not claim the
specified winner-recall goals without the minimum declared roots, projects, languages, hardware
targets, and physical observations.

#### Scenario: Pilot corpus
- **WHEN** a valid corpus contains fewer than 2,500 roots
- **THEN** training may produce a pilot model but production acceptance is `insufficient_dataset`
