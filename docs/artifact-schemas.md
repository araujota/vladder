# Stable Artifact Schemas

Public artifact schemas live in `vladder/schemas` and are listed by:

```bash
vladder schema list
vladder schema validate --kind promotion-summary --artifact promotion-summary.json
```

The registered set also includes optimization plans, portfolio campaign summaries, concise agent
dispositions, discovered project-evidence manifests, physical-runner envelopes, and signed remote
result bundles. These orchestration artifacts describe routing and evidence state; they do not
widen the semantic claim of any proof artifact.

The initial stable set covers `SemanticFlowGraph v2`, promotion summaries, paired benchmark
results, agent reviews, and source-free training bundles. Within one schema major version, producers may add optional fields but
may not remove required fields, change required field types, or reinterpret enums. Incompatible
changes receive a new schema ID and file. Schema stability describes serialization compatibility;
it does not widen a proof claim.

Every public artifact includes its own `schema_version`. Consumers must reject unknown required
versions rather than guessing from file names. Internal research artifacts may remain experimental
and must not be presented as stable API unless registered.

`vladder-training-bundle-v1` is a historical, validation-only artifact. Current package producers,
outbox enqueue, and submission APIs do not emit or accept it for transport. This preserves access
to old local evidence without allowing flattened telemetry to enter the graph-learning corpus.

`vladder-model-training-bundle-v3` is the search-pruner interchange. It stores linked bounded roots,
search executions, parented branches, branch coverage authority, search costs, observations, direct
utility, descendant utility, and fail-open survival labels. A negative branch is trainable as
`PRUNE_HIGH_CONFIDENCE` only when its subtree is exhaustive or soundly closed; partial and truncated
evidence remains `KEEP_UNCERTAIN`. It is classified as pseudonymized structural data rather than
anonymous data and is the exclusive output of current training producers and append service.
Both local validation and service ingestion recompute labels from observations and complete
lineage. Standalone learning examples include the accumulated ancestor action path.

`vladder-model-training-bundle-v2` remains locally valid for historical flat candidate evidence but
cannot be enqueued or submitted. It lacks search lineage and negative-label authority and therefore
must not be used as primary supervision for a live pruning oracle.
