# Stable Artifact Schemas

Public artifact schemas live in `vladder/schemas` and are listed by:

```bash
vladder schema list
vladder schema validate --kind promotion-summary --artifact promotion-summary.json
```

The initial stable set covers `SemanticFlowGraph v2`, promotion summaries, paired benchmark
results, agent reviews, and source-free training bundles. Within one schema major version, producers may add optional fields but
may not remove required fields, change required field types, or reinterpret enums. Incompatible
changes receive a new schema ID and file. Schema stability describes serialization compatibility;
it does not widen a proof claim.

Every public artifact includes its own `schema_version`. Consumers must reject unknown required
versions rather than guessing from file names. Internal research artifacts may remain experimental
and must not be presented as stable API unless registered.

`vladder-training-bundle-v1` is intentionally not a generic artifact envelope. It accepts bounded
derived features and evidence labels only. This prevents the contribution command from becoming a
back door for source, raw IR, patches, prompts, traces, credentials, or arbitrary attachments.

`vladder-model-training-bundle-v2` is the candidate graph-model interchange. It stores linked,
bounded roots, candidates, and observations, including sanitized graph topology and structured
action/hardware/workload descriptors. It is classified as pseudonymized structural data rather
than anonymous data. Legacy v1 bundles remain valid telemetry but cannot substitute for v2 graph
samples in relational or listwise training.
