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
lineage. The `useful-descendant-v2` labeler requires proof plus distinct-realization evidence for a
local candidate to become a survival positive; proof-only terminals remain uncertain, while proved
compiler-identical terminals can become complete-tree negatives. Standalone learning examples include
the accumulated ancestor action path.
`missing_contract` is an explicit incomplete coverage reason, not a sound closure, and therefore
fails open to `KEEP_UNCERTAIN` unless a separate deterministic contract proof closes the branch.

Candidate-dense searches are emitted as a deterministic packet set rather than one oversized JSON
document. A packet is one of `full_trace`, `complete_subtree`, or `partial_snapshot`:

* `full_trace` contains the whole bounded search when it fits.
* `complete_subtree` contains a locally complete subtree and names its
  `external_parent_branch_id`; its terminal and descendant labels retain the same authority as the
  unfragmented trace.
* `partial_snapshot` preserves an oversized residual spine or unresolved frontier and therefore
  fails open to `KEEP_UNCERTAIN` wherever completeness is unavailable.

Consumers must load every bundle in a campaign record's `bundles` array. The legacy singular
`bundle` field is present only when one packet represents the complete record. Packetization is a
transport operation: it must not truncate branches, weaken terminal observations, or manufacture
negative authority.

`vladder-model-training-bundle-v2` remains locally valid for historical flat candidate evidence but
cannot be enqueued or submitted. It lacks search lineage and negative-label authority and therefore
must not be used as primary supervision for a live pruning oracle.

`vladder-search-decision-bundle-v1` is the contextual best-first interchange. One `SearchDecision`
contains the canonical parent semantic state, complete prior action sequence, grammar state, and
every legal sibling action visible before expansion. Each sibling's distance-to-useful,
useful/retained descendants, exhaustive subtree cost, and redundancy class are stored only under
`descendant_outcomes`; `inference_view` excludes them. Future source-search traces also preserve
canonical state hashes, exact transpositions, proof/compiler invocation counts, and frontier
history. RC24 migrations explicitly mark unavailable evidence rather than manufacturing it. This
schema trains ordering and verifier proposals, not deletion.

`vladder-composition-native-search-trace-v1` is the authoritative composition-search training
artifact. It is emitted directly by exhaustive enumeration rather than reconstructed from v3 branch
packets. It includes exact parent/child semantic states, canonical hashes, complete frontiers,
structural deltas, typed interaction graphs, factor nodes, transpositions, terminal U0-U4 outcomes,
backward utility lineage, and measured search cost. `labels` and `terminals` are supervision only;
the packaged `inference_view` excludes them. ML may rank its actions or propose a verifier call, but
the schema grants no deletion, merge, proof, benchmark, or promotion authority.
Terminal records are keyed to the canonical owner state, never to a transposed duplicate sharing
the same semantic hash. Singleton frontiers remain part of the trace and online replay even though
they provide no pairwise/listwise ranking target. The corpus audit also verifies the trace hash and,
for decisive-retention roots, every compressed artifact hash recorded by the summary.

Current emitters also attach `vladder-search-policy-training-contract-v1`. It declares ML's role as
ordering and verified-proposal generation only, marks exact/formal mechanisms as the sole hard
reduction authority, and reports frontier, canonical-identity, terminal, and search-cost readiness.
Emission fails if state lineage, canonical ownership, sibling cardinality, action labels, terminal
ownership, summary counts, or the content hash disagree. `future_policy_training_eligible` requires
an exhaustive search, complete frontier context, canonical identities, and terminal outcomes;
partial cost capture is reported separately rather than silently discarding an otherwise valid
ordering trace. The inference projection intentionally omits the completed state set,
transpositions, selected actions, outcomes, labels, and timing evidence.

`vladder-canonical-state-dag-v1` is the exact composition-search artifact. It stores one
collision-validated record per canonical semantic state, all incoming transformation edges,
minimum/maximum discovery depth, canonical/observable/contract and layered component hashes,
enabled actions, memoized semantic summaries, exact terminal hashes, and non-overlapping reduction
metrics. A digest is an index only; canonical bytes remain authoritative. The artifact distinguishes
transposition, alpha, symmetry, dependency, POR, dominance, macro, and e-class effects and grants no
authority to a learned score.

`vladder-production-canonical-search-v1` wraps the DAG with requested/effective mode, versioned
source/grammar/target identity, adaptive reduction decisions, grammar-family footprint coverage,
state-analysis cache statistics, rolling search-cost evidence, memory policy, checkpoint state,
production defaults, and explicitly disabled experimental authorities.

`vladder-production-search-checkpoint-v1` stores runtime state needed to resume a bounded search.
Resume cleanly rematerializes canonical bytes and rejects source, grammar, target, or schema
identity changes before exploration.

`vladder-production-canonical-search-smoke-v1` is the release-blocking eight-stage regression
artifact. It records every boolean assertion and physical/search metric for canonical identity, POR
safety, incremental fallback, real proof/compiler reduction, cost gating, concurrency, resume, and
mini scaling. Aggregate `PASS` requires all eight stages.

`vladder-canonical-search-release-artifact-v1` is a stable, compact qualification record bundled
inside the Python distribution. It binds the package version to the production engine, authority
model, defaults, terminal-preservation evidence, measured expensive-fixture savings, smoke stages,
and policy-training contract. Read it with `vladder release canonical-search-evidence`; the command
loads the installed package resource and validates it against the registered schema before output.
