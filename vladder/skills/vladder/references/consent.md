# Optional Contribution Consent

Training-data contribution and an agent-experience review are independent, optional terminal
stages. They are never part of optimization, proof, benchmarking, or promotion.

Run `vladder consent show` before discussing either contribution. Present its complete notice for
each `unknown` scope, including destination, included and excluded data, frequency, moderation,
revocation, and the locally estimated record/bundle/byte volume when available, then ask the user
to explicitly choose opt in or opt out. Use local `training export-prior` without
`--apply-durable-consent` to estimate canonical contribution volume; this performs no network
request. Do not infer an answer
from silence, installation, ordinary use, prior payload approval, generalized telemetry language,
or consent for the other scope.

The choices mean:

- `canonical_training_data=opt_in`: at every eligible opportunity, contribute all anonymized,
  source-free training forms the installed release can encode: canonical graph features and
  hashes; grammar actions; proof, differential, compile, assembly, cost, counter, benchmark, and
  composition outcomes; rejections; and coarsened hardware/workload descriptors. Do not ask again
  for each send. Never send source, paths, raw artifacts, prompts, personal data, or the local prior
  store. Report any eligible form that lacks an anonymizer/export adapter instead of silently
  omitting it.
- `agent_experience_review=opt_in`: ask for a qualitative review no more than once every 30 days.
  Do not ask after every workflow. Present the exact review record and obtain submission approval;
  review opt-in is permission for periodic requests, not blanket submission approval.

Record the user's explicit answer only with:

```bash
vladder consent set --scope canonical-training-data --decision opt-in|opt-out --confirmed-user-choice
vladder consent set --scope agent-experience-review --decision opt-in|opt-out --confirmed-user-choice
```

An opt-out persists across sessions and updates. Do not upload and do not ask again unless the
user explicitly requests reconsideration. For continuous training contribution, durable opt-in
authorizes the agent to apply record consent and `--confirm-upload` without asking again, after
local anonymization and schema validation. For reviews, exact-record approval remains required.
`--validate-only` also sends bytes and therefore requires the corresponding opt-in.

After opt-in, the first contribution obtains a random append capability for only the requested
scope. It is stored outside the package at
`$XDG_CONFIG_HOME/vladder/contribution-credentials.json` with owner-only permissions. This token is
not a Convex deployment credential and cannot read, approve, update, or delete contribution rows.
Do not print or copy the credential into workflow artifacts. To verify both paths without storing a
record, use `vladder contribution doctor` only when both durable scopes are opted in.

After requesting a periodic review, run:

```bash
vladder consent review-requested --confirmed-user-prompt
```

Do not request another review while `vladder consent show` reports `review_request.status=not_due`.

For every newly updated canonical prior store while training contribution is enabled, run:

```bash
vladder training sync-prior --store EXPERIENCE --project-id PROJECT \
  --agent AGENT --model MODEL --out-dir vladder-training-sync
```

The command hashes the project identifier, shards every supported candidate into bounded bundles,
applies durable record consent, validates locally, and submits to Convex. Run equivalent registered
exporters for non-prior evidence; name any missing exporter in the workflow disposition.

Canonical `workflow run` and `workflow summarize` commands do not require a separate sync command:
after producing a complete terminal promotion summary they automatically anonymize, validate, and
submit its registered disposition record when this scope is opted in. The summary records whether
submission completed or failed. A failed contribution remains retryable and does not weaken or
invalidate local proof and benchmark artifacts.

Before transport, the client stores only the schema-valid, source-free contribution bundle in an
owner-only persistent outbox. Subsequent opted-in terminal workflows replay pending entries.
Unknown and opt-out states perform no upload and do not flush this queue.

Never transmit source, raw artifacts, prompts, credentials, personal data, compilation databases,
IR, patches, traces, or a local prior store.
