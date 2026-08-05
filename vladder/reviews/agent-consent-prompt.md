# vLadder Optional Contribution Consent Prompt v1

This prompt governs two independent, optional network actions. It is not itself consent.

Before asking, run `vladder consent show` and inspect each scope.

- If a scope is `unknown`, ask the user to explicitly choose **opt in** or **opt out** for that
  scope. Ask separately for `canonical_training_data` and `agent_experience_review`; do not bundle
  the decisions or infer one from the other.
- If a scope is `opt_out`, do not upload and do not ask again in a later turn or session unless the
  user explicitly asks to reconsider that saved choice.
- If a scope is `opt_in`, do not ask again merely because a new session started. Preview the exact
  source-free record and retain the record-level consent and `--confirm-upload` gates.

Record an explicit answer with:

```bash
vladder consent set --scope canonical-training-data --decision opt-in|opt-out --confirmed-user-choice
vladder consent set --scope agent-experience-review --decision opt-in|opt-out --confirmed-user-choice
```

Never run either command based on silence, this prompt, an installation request, generalized
telemetry consent, or a prior upload confirmation. Never upload source, raw artifacts, prompts,
credentials, personal data, or the local prior store.
