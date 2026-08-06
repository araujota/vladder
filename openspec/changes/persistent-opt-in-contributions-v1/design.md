# Design

## Authority

The local consent ledger is the durable authority for whether an optional contribution workflow
may begin. It is not embedded in the installation and is never inferred from ordinary vLadder
use. Training and review decisions are separate.

## Training Semantics

Training opt-in is continuous. At every eligible opportunity the attending agent exports all
source-free forms supported by the installed release, applies record consent from the durable
decision, and submits without asking again. Schema/privacy validation and the mechanical command
confirmation remain fail-closed. Missing anonymizers/exporters are reported as coverage gaps.

## Review Semantics

Review opt-in permits a request no more often than once every 30 days. The cadence is stored in the
ledger. The exact review still requires approval before submission.

## Submission Gates

Submission requires durable scope opt-in, consent inside the validated record, and
`--confirm-upload` for the operation. For training, the saved informed opt-in authorizes repeated
record consent and command execution. For reviews, exact-record approval remains required. Remote
validate-only requests also require opt-in because they transmit payload bytes.

## Agent Behavior

Unknown state causes a machine-readable request for user clarification. Opt-out causes a durable
disabled state and suppresses repeated prompts. Training opt-in executes registered anonymized
exporters at eligible terminal stages; review opt-in only makes a bounded periodic request
eligible. Workflow summaries expose execution, failure, and coverage-gap states.

## Persistence

The ledger uses an atomically replaced, owner-only JSON file under the user configuration
directory. Package updates do not own or reset it. An explicit later user decision may replace an
earlier decision.
