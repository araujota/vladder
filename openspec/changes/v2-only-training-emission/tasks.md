## 1. Producer migration

- [x] 1.1 Replace the manual training template with a graph-ready v2 template.
- [x] 1.2 Convert terminal promotion summaries into v2 roots, candidates, and observations.
- [x] 1.3 Preserve actual captured semantic graphs when available and type fallback evidence graphs.

## 2. Runtime enforcement

- [x] 2.1 Reject legacy records in enqueue and submit APIs.
- [x] 2.2 Quarantine legacy outbox entries during flush.
- [x] 2.3 Remove all runtime selection of the legacy endpoint.

## 3. Service enforcement

- [x] 3.1 Return `410 Gone` from the legacy training route.
- [x] 3.2 Advertise v2-only model training in service health and documentation.

## 4. Agent and release surfaces

- [x] 4.1 Update README, privacy, skill, and agent workflow guidance.
- [x] 4.2 Bump the release candidate and synchronize the release site.

## 5. Validation

- [x] 5.1 Test template, promotion, outbox, endpoint, privacy, and relationship invariants.
- [x] 5.2 Run strict OpenSpec, repository, package, skill, backend, and release checks.
- [x] 5.3 Install locally and submit a consented v2 smoke record to production moderation.
