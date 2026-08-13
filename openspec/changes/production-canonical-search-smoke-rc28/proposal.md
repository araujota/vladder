# Production Canonical Search Smoke Battery

## Why

RC28 qualified production canonical search through broad replay and scaling campaigns, but release
validation currently invokes several low-level tests rather than one bounded, machine-readable,
release-blocking smoke contract. Canonical identity, POR fail-open behavior, incremental recovery,
real proof/compiler savings, cost gating, concurrency, checkpoint identity, and scaling must fail a
release from one stable entry point.

## What Changes

- Add a packaged eight-stage production smoke battery and stable JSON artifact.
- Exercise real Z3 and optimized C++ compilation in the expensive-terminal stage.
- Add an explicit incremental-hash clean-rematerialization fallback API.
- Integrate the battery into CI, tag release, release readiness, schemas, and agent documentation.
- Preserve exact terminal sets as the correctness authority; timing only gates the dedicated
  expensive-work fixture.

## Non-Claims

The mini scaling fixture is a regression sentinel, not the three-project RC28 qualification. The
smoke battery does not replace full nightly or release qualification and does not grant POR,
heuristics, or ML any new deletion authority.
