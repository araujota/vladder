## Purpose

Provide a stable library and command-line surface for reproducible information-flow optimization of bounded C and C++ regions.

## ADDED Requirements

### Requirement: vLadder identity and entry points
The distributable project SHALL identify as `vladder`, expose a `vladder` command, and expose a documented Python library entry point.

#### Scenario: Import and invoke the release
- **WHEN** a user installs the package in a clean Python environment
- **THEN** `import vladder` and `vladder --help` succeed and report the same release version

### Requirement: Stable optimization request
The library SHALL accept a source path, target function, semantic assumptions, search limits, verification policy, benchmark policy, and artifact directory as structured input.

#### Scenario: Run from Python
- **WHEN** a caller submits a valid optimization request
- **THEN** the library returns a structured result and writes deterministic analysis, candidate, proof, benchmark, and patch artifacts

### Requirement: Fail-closed artifact status
The result SHALL distinguish analyzed, verified, benchmarked, selected, unproved, failed, and unavailable-tool states without representing an unverified candidate as promotable.

#### Scenario: Required prover is unavailable
- **WHEN** the verification policy requires Alive2 and `alive-tv` is unavailable
- **THEN** the run fails closed before source promotion and records the missing dependency
