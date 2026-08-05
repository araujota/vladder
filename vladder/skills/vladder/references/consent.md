# Optional Contribution Consent

Training-data contribution and an agent-experience review are independent, optional terminal
stages. They are never part of optimization, proof, benchmarking, or promotion.

Run `vladder consent show` before discussing either contribution. For every `unknown` scope, ask
the user to explicitly choose opt in or opt out. Do not infer an answer from silence, installation,
ordinary use, prior payload approval, generalized telemetry language, or consent for the other
scope.

Record the user's explicit answer only with:

```bash
vladder consent set --scope canonical-training-data --decision opt-in|opt-out --confirmed-user-choice
vladder consent set --scope agent-experience-review --decision opt-in|opt-out --confirmed-user-choice
```

An opt-out persists across sessions and updates. Do not upload and do not ask again unless the
user explicitly requests reconsideration. An opt-in only makes submission available. Preview the
exact source-free record, set its record-level consent only with user approval, validate it, and
require `--confirm-upload`. `--validate-only` also sends bytes and therefore requires opt-in.

Never transmit source, raw artifacts, prompts, credentials, personal data, compilation databases,
IR, patches, traces, or a local prior store.
