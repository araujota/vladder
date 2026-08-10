## 1. Contract

- [x] 1.1 Add the bounded v3 JSON schema for roots, searches, branches, observations, and privacy.
- [x] 1.2 Add deterministic lineage, completeness, and bottom-up survival-label validation.
- [x] 1.3 Ensure incomplete evidence can never produce a high-confidence negative label.

## 2. Producers and consumers

- [x] 2.1 Switch templates, flat-prior exports, and terminal promotion summaries to v3.
- [x] 2.2 Add an authoritative search-trace producer retaining branch lineage and search cost.
- [x] 2.3 Emit branch-oriented GraphML examples with descendant targets and survival classes.
- [x] 2.4 Preserve historical v2 local validation while rejecting v1/v2 enqueue and submission.

## 3. Service

- [x] 3.1 Add private v3 Convex validation and storage without migrating historical v2 rows.
- [x] 3.2 Add `/api/training/v3`, retire `/api/training/v2`, and update capability probes.

## 4. Agent workflow and documentation

- [x] 4.1 Update CLI defaults, README, skill references, schemas, and privacy language.
- [x] 4.2 Document the distinction between positive-path evidence, exhaustive negatives, and partial
  uncertain traces.

## 5. Verification

- [x] 5.1 Test positive ancestor propagation, exhaustive dead subtrees, sound contract closures,
  incomplete fail-open behavior, malformed lineage, and false-negative rejection.
- [x] 5.2 Test prior, terminal, outbox, transport, GraphML, and service contract paths.
- [x] 5.3 Run OpenSpec strict validation, Python tests, service type checks, release checks, and a local
  package install smoke test.
