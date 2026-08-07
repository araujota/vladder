## 1. Research And Contract

- [x] 1.1 Audit v1 contribution, local prior, model, consent, service, and website boundaries.
- [x] 1.2 Research graph-program representations, learned candidate ranking, and de-identification.
- [x] 1.3 Define model authority, privacy profile, consent migration, and compatibility boundaries.

## 2. Model-Ready Schema

- [x] 2.1 Add bounded root, graph, candidate, hardware/workload, and observation JSON schemas.
- [x] 2.2 Add consent-epoch HMAC identities and structural de-identification.
- [x] 2.3 Add v2 template, prior exporter, sharding, validator, submission, and outbox support.
- [x] 2.4 Add v2 ingestion into root-grouped prior/model input.

## 3. Service

- [x] 3.1 Add strict Convex validators and private immutable v2 bundle storage.
- [x] 3.2 Add capability-scoped `/api/training/v2` validation and append route.
- [x] 3.3 Preserve moderation, payload bounds, idempotency, rate limits, and no public read path.

## 4. Consent And Documentation

- [x] 4.1 Add scope-specific policy migration and invalidate stale training consent.
- [x] 4.2 Update CLI notice, README, privacy policy, skill, prompts, and architecture docs.
- [x] 4.3 Update the release website with accurate topology and pseudonymization disclosure.

## 5. Verification

- [x] 5.1 Test source/name/literal/path removal, HMAC unlinkability, bounds, and stale consent.
- [x] 5.2 Test v2 round-trip into model-ready roots and candidate ranking groups.
- [x] 5.3 Type-check and deploy/validate the Convex route without storing absent renewed consent.
- [x] 5.4 Run Python, schema, skill, website, release, and OpenSpec validation.
