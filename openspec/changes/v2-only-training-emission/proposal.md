# Change: Require graph-ready v2 training emission

## Why

vLadder 1.0.0rc20 introduced `vladder-model-training-bundle-v2`, but canonical terminal
workflows continued to emit flattened `vladder-training-bundle-v1` records. This created active
telemetry without the normalized graph topology, structured action, and relationship data needed
by the learned search prior.

## What Changes

- Make every packaged training producer emit `vladder-model-training-bundle-v2`.
- Materialize a bounded semantic graph, baseline/candidate actions, and typed observations from
  every terminal promotion summary.
- Reject v1 records at local queue and submission boundaries.
- Quarantine pre-upgrade v1 outbox records without transmitting them.
- Retire the production v1 HTTP ingestion route with `410 Gone` while retaining historical data.
- Verify that all default and explicit submission paths target `/api/training/v2`.

## Impact

Existing v1 records remain available for historical analysis but are not graph-model-ready.
Upgraded clients never submit them. Older clients receive an actionable upgrade response instead
of adding more flattened records.

