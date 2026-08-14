# vLadder Review Backend

This optional Convex service accepts `vladder-agent-review-v1` records and strict graph-ready
`vladder-model-training-bundle-v3` search-trace records. New records are private until explicitly
approved. A public, rate-limited registration action issues random scope-specific append
capabilities; only token hashes are retained. Capability registration is rate-limited through a
salted network fingerprint. Submissions are rate-limited independently by the authorized,
scope-specific installation capability, so unrelated agents behind one host or NAT do not consume
one another's contribution budget. Payloads over 768 KiB are rejected. IDs are idempotent and
content-addressed.

```bash
npm install
CONVEX_AGENT_MODE=anonymous npx convex dev --once
npm run check
```

Set `VLADDER_SUBMISSION_PEPPER` for public abuse controls and `VLADDER_REVIEW_ADMIN_TOKEN` for
moderation. `VLADDER_REVIEW_TOKEN` is an optional trusted-ingestion credential. Raw IP addresses
are never stored. `POST ...?validate_only=true` validates without retaining a submission.
The local vLadder CLI remains fully functional when this service is absent.

The historical `POST /api/training` v1 and `POST /api/training/v2` routes return `410 Gone` without
storing a payload. All current clients register and submit through `POST /api/training/v3`.
`GET /api/health` publishes `vladder-contribution-endpoint-contract-v2`, including the accepted
schemas and canonical routes. Clients and online release readiness fail before credential creation
or payload upload when this descriptor does not match the installed package.

The client enforces a durable informed-consent policy before this service is contacted. Canonical
training opt-in continuously submits every registered source-free anonymized record form;
agent-review opt-in only enables a request once per 30-day cadence and exact-review approval remains
required. The service independently enforces the record-level consent literal, schema bounds,
private moderation, and separate review/training rate limits. Training uses bounded trace fragments;
only complete subtrees or sound closures can provide negative pruning labels. The
service never receives the local consent ledger.

Contributor capabilities are not Convex deployment credentials. They are checked only inside the
two HTTP append actions, cannot call internal mutations, cannot list pending data, and cannot reach
moderation. Convex clients have no direct table access, so this registered-function boundary is the
service's row-level access-control mechanism. `searchTrainingSubmissions` has no public query;
`reviews.listApproved` returns only moderated records.

The release candidate is deployed in Convex team `araujota97`, project `vladder-review`. Local
deployment URLs and credentials remain in ignored environment files and are not release artifacts.

Production HTTP base: `https://ceaseless-manatee-888.convex.site`. The Python client derives the
registration, review, and training routes from this base; it does not package any deployment or
contributor secret.
