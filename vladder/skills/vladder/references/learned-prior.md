# Learned Search Prior

Use the prior only to order already legal grammar actions. It cannot introduce a precondition,
change a contract, declare equivalence, suppress the baseline, replace physical measurement, or
authorize promotion.

## Agent Route

```bash
vladder prior init --out prior.yaml
vladder prior run --manifest prior.yaml --out-dir prior-out
```

Read `prior-summary.json` before detailed artifacts. Keep `dataset_valid`, `model_trained`,
`shadow_evaluation_completed`, `production_model_status`, and `live_search_pruned` separate. The
controlled corpus is Grade C and exists only to validate mechanics. A successful pilot is not a
production model. Production accounting accepts only non-synthetic Grade A/B physical evidence.

For a new grammar family, start with `vladder prior template`. Keep semantic additions in typed
graph fields and action additions in `primitives`, nested `parameters`, or namespaced `extensions`.
Run `vladder prior materialize`; never hand-author content hashes. Unknown typed fields participate
in canonical identity and model features rather than being silently discarded.

## Search Decision

1. Enumerate and legality-filter candidates with the ordinary grammar.
2. Run `prior recommend` over structured candidate descriptors.
3. If `abstention.required` is true, use exhaustive or current heuristic search.
4. Otherwise run `prior select`; verify `baseline_retained` and the exploration reserve.
5. Send selected candidates through unchanged proof, compile, differential, benchmark, and
   composition gates.
6. Append failures, ties, compiler identities, wins, and composed regressions as immutable
   experience.

Never report a rank score as correctness, speed, or production safety. Use it only as search
priority. Read `docs/learned-search-prior-v0.md` for schema, calibration, split, and scale gates.
Contributed v2 records preserve bounded sanitized topology, structured action, hardware/workload,
and observation sequences. Treat candidates sharing one root/hardware/workload as a ranking group;
do not flatten them into independent examples or train a graph model from legacy v1 telemetry.
Before budgeted deployment, run `vladder prior evaluate-matrix` and inspect every root, project,
language, hardware, and temporal view separately; an aggregate score may not hide a weak holdout.
