# Contribution Endpoint Contract rc30

## Why

vLadder `1.0.0rc29` emits `vladder-model-training-bundle-v3` records to
`/api/training/v3`, while the configured production contribution deployment still advertises v2
and does not expose that route. Existing release readiness accepts any healthy capability-scoped
service, so it failed to detect this client/service incompatibility.

## What Changes

- Publish a versioned contribution endpoint contract from `/api/health`.
- Validate the advertised review/training schemas and route map before client submission.
- Make contribution diagnostics identify incompatible deployments without storing records.
- Make online release readiness fail unless the live service implements the package contract.
- Deploy the matching Convex backend and publish vLadder `1.0.0rc30`.

## Non-Goals

- No contribution is made without the existing explicit consent gates.
- The health check does not create credentials or contribution records.
- Contributor capabilities do not gain read, moderation, deployment, or administrative authority.
