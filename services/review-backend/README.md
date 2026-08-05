# vLadder Review Backend

This optional Convex service accepts `vladder-agent-review-v1` records and strict source-free
`vladder-training-bundle-v1` derived-feature bundles. New records are private until explicitly
approved. Public submission requires no shared secret, is rate-limited through a salted daily
fingerprint, and rejects payloads over 128 KiB. IDs are idempotent and content-addressed.

```bash
npm install
CONVEX_AGENT_MODE=anonymous npx convex dev --once
npm run check
```

Set `VLADDER_SUBMISSION_PEPPER` for public abuse controls and `VLADDER_REVIEW_ADMIN_TOKEN` for
moderation. `VLADDER_REVIEW_TOKEN` is an optional trusted-ingestion credential. Raw IP addresses
are never stored. `POST ...?validate_only=true` validates without retaining a submission.
The local vLadder CLI remains fully functional when this service is absent.

The release candidate is deployed in Convex team `araujota97`, project `vladder-review`. Local
deployment URLs and credentials remain in ignored environment files and are not release artifacts.

Production HTTP base: `https://ceaseless-manatee-888.convex.site`. The Python client derives the
review and training routes from this base; it does not package any deployment secret.
