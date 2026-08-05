# Public Contribution Ingestion v1

## Why

The release CLI can create an agent review but currently requires a private shared token, and it
has no bounded training-data contribution path. A public release must let an ordinary installation
exercise both paths without embedding credentials or weakening vLadder's local-first policy.

## What Changes

- Add stable source-free training-bundle schema and CLI workflow.
- Ship moderated production endpoints for reviews and training bundles.
- Accept anonymous explicit-consent records under strict limits, idempotency, and abuse controls.
- Preserve offline-by-default behavior for all optimization workflows.
- Add remote validate-only checks and clean-install end-to-end verification.
