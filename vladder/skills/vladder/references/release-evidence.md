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

First run `vladder consent show`. When a scope is `unknown`, present the complete notice and local
volume estimate, ask the user to choose opt in or opt out, and persist the explicit answer. Never
ask again for a saved opt-out unless the user explicitly requests reconsideration.

Generate a source-free agent review only after reading the decisive files:

```bash
vladder review template --promotion-summary promotion-summary.json \
  --project PROJECT --revision GIT_SHA --out agent-review.json
vladder review validate --review agent-review.json
```

Follow the bundled canonical review prompt. Report hashes and bounded claims, not source or raw
artifacts. Remote submission is optional and requires durable `agent_experience_review` opt-in,
explicit user consent at both CLI and record levels, and exact-payload preview.

For continuously consented search-prior evidence, use `vladder training sync-prior`; it shards all
supported flat forms into partial `vladder-model-training-bundle-v3` searches; authoritative search
engines should use `training from-search-trace` to preserve parent/child lineage, coverage, costs,
and useful-descendant labels.
Use `export-prior` first for local-only volume inspection. The records contain bounded normalized
topology, search lineage, structured actions/context, coverage authority, and evidence labels and
are classified as pseudonymized structural data, not anonymous data. Legacy v1 and flat v2 records
are historical evidence, not primary pruning supervision.
Never place source, IR, patches, prompts, raw traces, personal data, or a local prior store in it.
Both contribution paths default to the moderated release service and require their independent
durable opt-in plus `--confirm-upload`; training sync applies the latter mechanically without a
new user question, while review submission remains exact-record approved.
use `--validate-only` when testing the endpoint without retaining a submission.
Fresh hosts bootstrap separate `training:write` and `review:write` capabilities after opt-in; no
shared or deployment secret is distributed. `vladder contribution doctor` verifies endpoint
resolution and negative authorization boundaries without storing records.

## Release Gate

For vLadder itself, run `vladder release check --execute --require-target release_candidate`.
Before a tag, run it again with `--online --require-target formal_release`. Read
`build/release-readiness.json`; do not infer readiness from command completion alone. A local pass,
a publication-channel setup requirement, and an unavailable external check are different states.
Never report GitHub, PyPI, Homebrew, Convex, or another hosted channel as ready until its named
check is `pass`.
