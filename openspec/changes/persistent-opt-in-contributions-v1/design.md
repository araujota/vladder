# Design

## Authority

The local consent ledger is the durable authority for whether an optional contribution workflow
may begin. It is not embedded in the installation and is never inferred from ordinary vLadder
use. Training and review decisions are separate.

## Three Gates

Submission requires: durable scope opt-in, consent inside the exact validated record, and
`--confirm-upload` for the exact operation. Remote validate-only requests also require opt-in
because they transmit payload bytes.

## Agent Behavior

Unknown state causes a machine-readable request for user clarification. Opt-out causes a durable
disabled state and suppresses repeated prompts. Opt-in makes a terminal contribution stage
available but never executes it automatically. Workflow summaries expose these states.

## Persistence

The ledger uses an atomically replaced, owner-only JSON file under the user configuration
directory. Package updates do not own or reset it. An explicit later user decision may replace an
earlier decision.
