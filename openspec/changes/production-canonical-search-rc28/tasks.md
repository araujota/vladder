# Tasks

## Specification And Audit

- [x] Audit RC27 against every production invariant and authority boundary.
- [x] Define versioned runtime, checkpoint, footprint, telemetry, and qualification schemas.
- [x] Validate this OpenSpec change strictly before implementation.

## Production Runtime

- [x] Add versioned canonical IDs, collision-safe concurrent interning, and deterministic state ownership.
- [x] Add state-keyed memoization with hit/miss and memory telemetry.
- [x] Add adaptive exact-reduction selection and empirical search-cost estimates.
- [x] Add checkpoint/resume with source, grammar, schema, and target compatibility checks.
- [x] Add memory ceilings, recomputable-cache eviction, and identity-preserving spill behavior.
- [x] Add fail-open incremental canonicalization incidents and clean-rematerialization fallback.

## Search Integration

- [x] Make canonical DAG search the default fast, guided, and exhaustive architecture.
- [x] Retain raw sequence search only as an explicit qualification/debug mode.
- [x] Emit production canonical DAG, reduction waterfall, cache, footprint, resource, and policy evidence.
- [x] Audit and expand action footprints for high-branching executable grammars.

## Qualification

- [x] Reproduce RC26 and RC27 terminal-preservation baselines.
- [x] Add permanent scaling curves across at least three independent systems.
- [x] Measure expensive source-search roots with real proof and compiler work.
- [x] Add concurrency, deterministic identity, checkpoint, and memory-ceiling stress tests.
- [x] Add all required adversarial fail-open and unsound-reduction counterexamples.
- [x] Produce the production disposition report and machine-readable qualification summary.

## Release

- [x] Update public schemas, CLI/API, README, architecture, and artifact documentation.
- [x] Update and reinstall the bundled vLadder agent skill.
- [x] Run focused, full, release, package-build, doctor, and strict OpenSpec verification.
- [x] Record exact production defaults and disabled experimental mechanisms.
