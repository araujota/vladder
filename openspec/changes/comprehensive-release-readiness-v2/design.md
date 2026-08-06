# Design

## Readiness Targets

The system reports independent targets: `local_development`, `release_candidate`, `github_release`,
`pypi`, `homebrew`, and `formal_release`. A target is ready only when all checks that block it pass.
An external channel cannot compensate for failed semantics or artifacts.

## Status Vocabulary

- `pass`: evidence was collected and the requirement holds.
- `fail`: collected evidence contradicts the requirement.
- `not_run`: executable evidence was requested but not collected.
- `setup_required`: an external account, environment, trusted publisher, tap, secret name, or
  protection rule must be configured.
- `unavailable`: the current host cannot run the check; another declared runner must do so.
- `warning`: non-blocking quality or ergonomics debt.

Every check records the targets it blocks, evidence, and a concrete remediation.

## Channel Authority

`release/channels.toml` declares intended public identifiers and explicit setup attestations but
contains no secret. Online checks corroborate public and GitHub-visible state. Trusted Publisher
configuration is not publicly queryable, so readiness requires both an attestation and a successful
channel exercise where one can exist before production. PyPI publication remains GitHub OIDC-based;
API tokens are forbidden.

## Artifact And Access Validation

The gate builds one wheel and one sdist in an isolated output directory, validates metadata,
audits contents, installs each in a clean virtual environment, and exercises version, schema,
grammar, skill, and doctor entry points. Homebrew rendering uses the same sdist and all Python
runtime resources. A macOS release job performs formula audit, build-from-source install, and test
before updating the tap.

## Functional Evidence

The complete test suite is the primary aggregate functionality gate. Additional checks make major
surfaces visible: canonical C/C++, Rust, Zig, Julia, deep/lifetime/dataflow grammars, GPU/protocol
workflows, learned prior, release contribution privacy, and bounded proof/promotion behavior.
