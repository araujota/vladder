# Design

## Boundary

Contribution is an explicit terminal workflow, not telemetry. The client validates one registered
artifact, checks record-level and command-level consent, enforces HTTPS and a 128 KiB bound, then
sends exactly those bytes. Endpoint defaults are public configuration; trusted tokens are optional.

## Review Intake

`vladder-agent-review-v1` remains source-free and moderation-only. Public records are stored with
`approved=false`; only approved records are returned by the public query.

## Training Intake

`vladder-training-bundle-v1` contains hashes, bounded numerical/categorical features, grammar
actions, proof outcomes, benchmark labels, and privacy declarations. It cannot encode arbitrary
attachments or raw artifacts. It is separate from vLadder's richer local immutable prior store.

## Abuse And Privacy

The Convex action hashes a proxy-provided client address and user agent with a deployment-only
pepper, then applies a per-kind daily limit transactionally. It never persists the raw address.
IDs are idempotent; reuse with a different payload hash fails. A validate-only request runs server
validation without storage. Moderation tokens remain private and are never shipped in the package.
