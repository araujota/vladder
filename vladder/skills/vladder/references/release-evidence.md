# Release Evidence And Agent Decisions

Use this reference to decide what happened without reading the complete artifact tree first.

## Decisive Files

Read these in order when present:

1. `promotion-summary.json`: independent workflow states, blockers, next action, and disposition.
2. the selected semantic graph: captured information, effects, obligations, protocols, and claims.
3. the proof summary: exact theorem, solver status, excluded behavior, and counterexamples.
4. the paired benchmark summary: raw-sample identity, interval, threshold, and observables.
5. the applied/integration report: source identity, project tests, composed effect, and retention.

Use artifact lineage only to investigate a failed or disputed state. Do not treat artifact volume
as stronger evidence.

## Recovery Matrix

| First incomplete state | Meaning | Next action |
|---|---|---|
| meaningful coverage | selection or capture did not include the valuable semantics | narrow the region, select an overload/specialization, inline a modeled helper, or write an explicit adapter |
| candidate generated | graph is captured but no executable grammar/emitter covers it | add an attribution-justified bounded grammar/lowerer or report a grammar gap |
| candidate proved | candidate exists but required equivalence is open | close Z3/Alive2/local adapter obligations or reject the candidate |
| physically benchmarked | proof exists but no valid hardware comparison exists | add paired same-executable measurements and exact observables |
| application integrated | regional evidence exists but production composition is unknown | apply behind a guard, run project oracles, and measure the complete workload |
| production promoted | evidence is complete but thresholds or regressions reject retention | retain the baseline and record a verified negative result |

## Review Record

First run `vladder consent show`. When a scope is `unknown`, ask the user to choose opt in or opt
out and persist the explicit answer. Never treat generation of a record as permission to submit
it. Never ask again for a saved opt-out unless the user explicitly requests reconsideration.

Generate a source-free agent review only after reading the decisive files:

```bash
vladder review template --promotion-summary promotion-summary.json \
  --project PROJECT --revision GIT_SHA --out agent-review.json
vladder review validate --review agent-review.json
```

Follow the bundled canonical review prompt. Report hashes and bounded claims, not source or raw
artifacts. Remote submission is optional and requires durable `agent_experience_review` opt-in,
explicit user consent at both CLI and record levels, and exact-payload preview.

For separately consented search-prior evidence, create `vladder-training-bundle-v1` with
`vladder training template|validate`. It contains only bounded derived features and evidence labels.
Never place source, IR, patches, prompts, raw traces, personal data, or a local prior store in it.
Both contribution paths default to the moderated release service and require their independent
durable opt-in plus `--confirm-upload`;
use `--validate-only` when testing the endpoint without retaining a submission.

## Release Gate

For vLadder itself, run `python3 scripts/public_release_gate.py --execute`. A local pass and an
external deployment gate are different states. Never report Sonar, Snyk, Convex, Vercel, or other
hosted evidence as passing until the authenticated service run is visible.
