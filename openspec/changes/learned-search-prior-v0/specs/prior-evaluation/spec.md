## ADDED Requirements

### Requirement: Root-grouped shadow evaluation
Shadow mode SHALL score every candidate without changing the executed search and SHALL report
winner recall, benchmark reduction, regret, ranking quality, calibration, abstention, and baseline
suppression.

#### Scenario: Winner omitted by budget
- **WHEN** the best measured candidate is outside the simulated selected set
- **THEN** winner recall decreases and regret records the lost measured effect

### Requirement: Separate generalization views
Evaluation SHALL report semantic-root, project, language, hardware, and temporal holdouts separately.

#### Scenario: Random candidate split requested
- **WHEN** evaluation is configured with a random candidate split
- **THEN** the workflow rejects it as leakage-prone
