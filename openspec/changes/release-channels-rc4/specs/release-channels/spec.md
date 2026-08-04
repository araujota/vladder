## ADDED Requirements

### Requirement: Tag and package identity
Release publication SHALL fail when the Git tag, project metadata, runtime package, README, and
changelog versions do not agree.

#### Scenario: Mismatched tag
- **WHEN** `v1.0.0rc5` attempts to publish package version `1.0.0rc4`
- **THEN** the build fails before GitHub or PyPI publication

### Requirement: Single-source distributions
GitHub and PyPI SHALL receive the same audited wheel and source distribution built by the release
job.

#### Scenario: Tagged release
- **WHEN** a matching tag passes all gates
- **THEN** checksummed distributions are transferred to publishing jobs without rebuilding

### Requirement: Trusted PyPI publication
PyPI publication SHALL use GitHub OIDC and SHALL NOT require a stored PyPI API token.

#### Scenario: Missing publisher configuration
- **WHEN** PyPI does not trust the workflow identity
- **THEN** publication fails without credential fallback

### Requirement: Reproducible Homebrew formula
The release workflow SHALL generate a formula with exact source and dependency URLs and SHA-256
values.

#### Scenario: Formula handoff
- **WHEN** the sdist and dependency metadata are available
- **THEN** the rendered formula passes Ruby syntax and is emitted as a release artifact

### Requirement: Lifetime release gate
The release SHALL execute the isolated lifetime discovery, proof, deterministic replay, and
microbenchmark workflow while preserving its non-application claim.

#### Scenario: Lifecycle regression
- **WHEN** a seeded stale-read or premature-retirement case is accepted
- **THEN** CI and release publication fail

### Requirement: Accurate documentation
README and skill SHALL distinguish automatic bounded-C source regeneration, architectural lifetime
agent realization, specialist routes, external tool installation, and proof scope.

#### Scenario: Alive2 scope
- **WHEN** a lifetime plan emits a local helper
- **THEN** documentation assigns Alive2 to the helper and not to the lifecycle protocol
