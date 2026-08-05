# Persistent Opt-In Contributions v1

## Why

Record consent and `--confirm-upload` protect one command but do not preserve whether a user was
never asked, opted out, or opted in across agent sessions and package updates. Agent workflows
also need a visible optional contribution stage without turning optimization into telemetry.

## What Changes

- Add a durable local ledger with independent canonical-training and agent-review scopes.
- Fail closed on unknown or opted-out state before every contribution network request.
- Surface contribution state in canonical workflow summaries without automatically uploading.
- Require agent skills to ask for an explicit opt-in or opt-out and honor the saved choice.
- Retain exact-record consent, schema validation, and explicit command confirmation.
