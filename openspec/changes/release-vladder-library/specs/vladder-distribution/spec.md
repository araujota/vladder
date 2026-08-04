## Purpose

Make vLadder installable, diagnosable, and usable by a resident coding agent in a clean supported development environment.

## ADDED Requirements

### Requirement: Reproducible dependency installation
The project SHALL provide an idempotent installer for the Python package, Clang/LLVM, llvm-mca, Z3, performance tooling, and optionally pinned Alive2.

#### Scenario: Install into an isolated prefix
- **WHEN** the installer is run with a user-selected prefix
- **THEN** it installs or validates required components without modifying source-tree artifacts and records component versions

### Requirement: Environment health check
The CLI SHALL provide a machine-readable doctor command that reports required and optional dependency status and returns nonzero when a required release dependency is missing.

#### Scenario: Complete toolchain
- **WHEN** all required tools are available
- **THEN** `vladder doctor --strict` succeeds and emits compiler, LLVM, solver, validator, perf, CPU, and package metadata

### Requirement: Installable coding-agent skill
The release SHALL include a valid `vladder` skill that directs an agent through attribution, contract definition, bounded search, proof-gated source rewriting, physical benchmarking, and reporting.

#### Scenario: Install the skill
- **WHEN** skill installation is enabled
- **THEN** the skill is installed under the configured agent home and passes structural validation

### Requirement: Release hygiene
The release artifact SHALL exclude generated benchmark outputs, caches, model files, vendored application repositories, credentials, and machine-local state.

#### Scenario: Build release distributions
- **WHEN** source and wheel distributions are built
- **THEN** an automated audit confirms excluded residue is absent and required grammars, skill files, examples, and licenses are present

### Requirement: External workspace dry run
The release process SHALL execute the installed CLI and skill workflow against a separate C/C++ workspace and record attribution, proof, benchmark, and promotion outcomes.

#### Scenario: NeuralFusion validation
- **WHEN** the release candidate is dry-run against NeuralFusion
- **THEN** the report names the analyzed path, tools used, proof scope, measured result, and whether a source replacement was justified
