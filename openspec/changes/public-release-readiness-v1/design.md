# Design

## Release Gate

`scripts/public_release_gate.py` emits one deterministic report covering install, frontends,
demos, case study, privacy, schemas, documentation, CI, roadmap, contribution guidance, review
format, backend, and website. A missing external deployment is reported separately from source
readiness and cannot be hidden by a passing local test.

## Artifact Stability

Stable public artifacts use JSON Schema Draft 2020-12 under `vladder/schemas/v1`. A registry maps
artifact kinds to schema IDs, file names, compatibility policy, and producer commands. Additive
optional fields are compatible within v1; removing or changing required fields requires a new
major schema directory. The CLI validates both known files and explicit kind selections.

## Privacy And Reviews

Optimization, proof, benchmark, and trace processing is local-only. No import-time telemetry,
background network calls, or implicit review upload is permitted. `vladder review submit` requires
an endpoint, a token, and `--confirm-upload`. The submitted payload is a strict agent-review record
and cannot contain source text, arbitrary attachments, credentials, or raw proof bundles.

The Convex service stores review records with indexed project/release/disposition fields. Public
reads expose only explicitly approved records. A reserved ML bundle table records metadata and
storage IDs for a future separately consented upload path; no ML upload command is part of v1.

## Website

The Next.js release site is a static-first technical surface. It presents the actual workflow,
support/claim matrix, local-only privacy posture, install commands, documentation, and GitHub
release downloads. Convex is optional at build time; approved review summaries are an enhancement,
not a dependency for docs or downloads.

## CI

Core CI runs Linux install smoke, unit/integration tests, seeded accepted/rejected transformation
checks, Ruff, and Bandit without secrets. SonarCloud and Snyk jobs are configured with least-privilege
tokens and fail visibly when enabled; fork pull requests do not receive secrets. The release gate
reports external scanner configuration separately from local source checks.
