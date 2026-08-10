# vLadder Optional Contribution Consent Prompt v1

This prompt governs two independent, optional network actions. It is not itself consent.

Before asking, run `vladder consent show` and present each unknown scope's complete notice:
destination, included and excluded data, frequency, moderation, revocation, and estimated local
record/bundle/byte volume when available. `training export-prior` is a local-only preflight.

- If a scope is `unknown`, ask the user to explicitly choose **opt in** or **opt out** for that
  scope. Ask separately for `canonical_training_data` and `agent_experience_review`; do not bundle
  the decisions or infer one from the other.
- If a scope is `opt_out`, do not upload and do not ask again in a later turn or session unless the
  user explicitly asks to reconsider that saved choice.
- If canonical training is `opt_in`, send every eligible pseudonymized training form supported by the
  installed release at each opportunity without asking again. Local schema and privacy checks must
  pass; an unsupported form must be reported rather than silently omitted.
- If agent review is `opt_in`, request a review only when the 30-day cadence reports `due`. Present
  the exact review record before submission and record the request with `vladder consent
  review-requested --confirmed-user-prompt`.

Record an explicit answer with:

```bash
vladder consent set --scope canonical-training-data --decision opt-in|opt-out --confirmed-user-choice
vladder consent set --scope agent-experience-review --decision opt-in|opt-out --confirmed-user-choice
```

Never run either decision command based on silence, this prompt, an installation request, generalized
telemetry consent, or a prior upload confirmation. Never upload source, raw artifacts, prompts,
credentials, personal data, or the local prior store.

For the model-training v3 notice, explicitly say that bounded normalized graph topology, search-tree
lineage, coverage authority, search costs, and descendant-survival labels are sent. Explain that
source identifiers and literals are removed and linked IDs use an installation-secret HMAC, but the
result is pseudonymized rather than anonymous because distinctive topology or search strategy can
fingerprint an algorithm. An older decision is stale and must not authorize v3 transport.

When canonical training is opted in, use `vladder training sync-prior` for each newly updated prior
store and every other registered source-free exporter at its opportunity. Do not silently reduce
"all supported forms" to accepted winners; negative, neutral, rejected, and failed outcomes are
training data too.
