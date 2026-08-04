## Why

vLadder 1.0.0rc4 adds first-class lifetime-aware realization synthesis to the fully validated rc3
bounded-region base. The repository needs one public release contract for GitHub, PyPI, and
Homebrew that preserves both the compiled-code proof boundary and the new architectural adapter
boundary.

## What Changes

- Align README and bundled skill with `bounded-regions-v1`, `lifetime-v1`, and their distinct proof
  and source-realization boundaries.
- Add source/distribution CI, GitHub releases, PyPI Trusted Publishing, TestPyPI, and an exact-hash
  Homebrew formula workflow.
- Gate publication on the lifetime corpus, complete lowering coverage, package audits, skill
  validation, and tag/package identity.
- Exclude application-specific and generated validation material from distributions.

## Impact

Public documentation, metadata, distribution contents, GitHub Actions, release scripts, the skill,
and release tests are affected. Publication remains externally blocked until a GitHub remote,
trusted publishers, and an optional Homebrew tap are configured by the repository owner.
