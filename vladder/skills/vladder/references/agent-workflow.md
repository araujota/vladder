# Agent Workflow Decision Tree

## One Entry Point

Run `vladder can-optimize SYMBOL --source SOURCE --project . --out-dir OUT` first. It classifies the
region, discovers candidate project oracles, maps external authorities, infers only code-supported
contract facts, accounts for grammar coverage and proof-unit representativeness, forecasts the
first unreachable evidence state and cost, and emits all missing scaffolds. Then run `vladder
optimize SOURCE --function SYMBOL --project . --out-dir OUT`. Read `disposition.json` before any
detailed artifact.

The default terminal report has five facts: coverage, candidate, proof, measurement, and
integration. `terminal_status` distinguishes `NO_COVERAGE`, `NO_CANDIDATE`, `NO_PROOF`,
`NO_BENCHMARK`, `INTEGRATION_REQUIRED`, `VERIFIED_REJECTION`, and `PROMOTABLE`. Follow the argv-form
`next_action.command`; after editing a named scaffold, use `vladder resume --out-dir OUT`.

Use `workflow init|run` directly only for specialist manifest authoring or imported evidence. It
remains a supported delegated executor, not the preferred agent entry.

## Mandatory Optional-Contribution Decision

Before the first canonical workflow run, run `vladder consent show`. The two scopes
are independent: `canonical_training_data` and `agent_experience_review`. If either is `unknown`,
the agent must present its complete informed-decision notice, ask the user to explicitly opt in or
opt out for that scope, and persist the answer
with `vladder consent set --scope ... --decision ... --confirmed-user-choice`. Do not infer consent
from use of vLadder, prior uploads, this workflow, or silence.

A durable opt-out suppresses both upload and repeated prompts in future sessions until the user
explicitly requests a change. Training opt-in directs the agent to submit every supported
pseudonymized training form at each eligible opportunity without a new question. Review opt-in allows
a request at most once per 30 days; exact-review submission remains separately approved. Prior
workflows sync registered training exporters only under training opt-in, and schema/privacy checks
remain mandatory.

The ubiquitous contribution trigger is terminal promotion-summary creation. Both `workflow run`
and `workflow summarize` automatically invoke the registered source-free exporter after the summary
contains the final semantic, candidate, proof, physical, disposition, blocker, and lineage states.
The contribution result is recorded under `optional_contributions.canonical_training_data`.
Submission failure is non-fatal to local evidence and is surfaced for retry; unknown or opt-out
consent never performs a network request.
Every locally valid record is written to the owner-only persistent training outbox before network
access. A later opted-in terminal workflow retries queued records; opt-out never flushes them.

## Evidence States

The states are independent and ordered:

1. `workflow_completed`: a command produced a report.
2. `meaningful_semantic_coverage`: the selected information and observables are nontrivial.
3. `candidate_generated`: a concrete alternative exists.
4. `candidate_proved`: the strongest applicable bounded proof passed.
5. `physically_benchmarked`: representative paired evidence exists.
6. `application_integrated`: the repository and project tests accept the realization.
7. `production_promoted`: all declared promotion gates passed.
8. `production_retained`: an already accepted candidate was revalidated under matching identity.

Never infer a later state from an earlier one. Use `workflow query` to traverse source-to-decision
lineage. A matching resumable key reports `revalidated`; it is not a new optimization.

## Recovery Routes

- Selection ambiguity: select the exact compilation command and mangled overload/template symbol.
- Local C++ closure only: run `cpp isolate`, then generate an application adapter.
- Multi-function path: compose native inspection reports with `system closure`; search only closed
  attributed components and keep protocol summaries out of the candidate count.
- Rust closure failure: inspect the named unsafe, ownership, destruction, panic, async,
  concurrency, FFI, call, or operation boundary. Isolate a safe borrowed region or add a
  compositional contract; do not translate it through C merely to make the frontend accept it.
- Object state: define a finite observable projection; use the built-in versioned-cache or
  transactional-publication verifier when semantics match exactly.
- External call, callback, coroutine, syscall, or driver: define input, output, ordering, failure,
  and state observables in a protocol plugin or application oracle. Do not summarize it as Alive2.
- Weak lifetime trace: add stable identities plus construct/transfer, consume, and repeated-use or
  complete residency events. Traces measure cost; manifests authorize invariants.
- No local rewrite: preserve an architectural information-volume finding with its measured bytes,
  lifetime, and boundary. It is a valid outcome, not a promoted source candidate.

## Physical Promotion

Use one executable for baseline and candidate, randomized process pairs, bootstrap intervals,
complete observable hashes, and composed-system confirmation. Do not compound overlapping region
effects without an interaction run. Report retained revalidation separately from discovery.

## Learned Search Recovery

The learned prior has a separate authority boundary. Run `vladder prior init` and `prior run`, then
read `prior-summary.json`. `model_trained` means only that a model artifact exists.
`shadow_evaluation_completed` is counterfactual. `production_model_status` is a corpus gate.
`live_search_pruned` is the only state saying the prior affected an executed search, and even then
all selected candidates still require the ordinary proof and physical-promotion workflow.
`optional_canonical_training_contribution` reports consent and sync state. Unknown or opt-out never
uses the network. A prior workflow with continuous training opt-in automatically runs every
registered de-identified prior exporter; inspect its bundle count and export gaps. For other workflow
kinds, terminal promotion-summary creation automatically runs the generic disposition exporter;
run additional registered exporters for richer canonical candidate stores and report missing
adapters explicitly.
