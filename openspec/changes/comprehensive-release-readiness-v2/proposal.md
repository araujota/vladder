# Comprehensive Release Readiness v2

## Why

The existing public release gate validates a useful subset of the repository but collapses account
setup, package correctness, functional coverage, clean-install usability, and hosted services into
coarse local or external states. PyPI and Homebrew can therefore appear nominally configured even
when Trusted Publishing, tap access, formula dependency closure, or clean installation is absent.

## What Changes

- Introduce one target-aware readiness report for local development, release candidate, PyPI,
  Homebrew, and formal public release.
- Validate semantic/proof workflows, full tests, artifacts, clean wheel/sdist installs, CLI and
  skill accessibility, privacy/credential boundaries, and documentation.
- Inspect GitHub, PyPI/TestPyPI, Convex, and Homebrew setup without embedding credentials.
- Distinguish defects, unexecuted checks, unavailable host tooling, and required account setup.
- Add a declarative channel manifest and exact remediation for every unresolved gate.
- Exercise formula generation and dependency closure before a tag can publish it.
