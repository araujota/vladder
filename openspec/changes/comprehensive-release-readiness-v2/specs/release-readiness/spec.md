# Release Readiness Requirements

## ADDED Requirements

### Requirement: Target-aware release decisions

The system SHALL calculate independent readiness for local development, a release candidate,
GitHub release, PyPI, Homebrew, and formal public release.

#### Scenario: PyPI is not configured

- **GIVEN** local functionality and artifacts pass
- **WHEN** the PyPI Trusted Publisher is not configured
- **THEN** local and candidate readiness may pass while PyPI and formal readiness remain blocked by
  `setup_required`

### Requirement: Clean distribution access

The release candidate SHALL install from both its wheel and sdist in clean environments and expose
the documented CLI, schemas, grammars, and agent skill.

#### Scenario: Missing packaged skill resource

- **WHEN** the wheel omits the bundled skill
- **THEN** clean-install readiness fails before publication

### Requirement: Account-side corroboration

The online gate SHALL inspect repository environments, current CI, project-index state, tap state,
and named configuration without reading or exposing secret values.

#### Scenario: Homebrew token absent

- **WHEN** `HOMEBREW_TAP_TOKEN` is not present in the configured environment
- **THEN** Homebrew readiness is `setup_required` with exact remediation

### Requirement: One build per release

GitHub, PyPI, and Homebrew SHALL consume artifacts derived from one audited build.

#### Scenario: Formula publication

- **WHEN** a tag release produces an sdist and formula
- **THEN** macOS verifies the formula against that exact local sdist before GitHub, PyPI, or tap
  publication consumes the audited build

### Requirement: No static publishing secret

PyPI publication SHALL use OIDC Trusted Publishing and release files SHALL not contain a PyPI API
token or credential.

#### Scenario: Workflow audit

- **WHEN** release workflows are inspected
- **THEN** the publish job has `id-token: write`, uses a protected environment, and contains no
  username, password, or `PYPI_API_TOKEN`
