# Agent Workflow Examples

Start new work through the evidence orchestrator:

```bash
vladder can-optimize transform --source src/transform.cpp --project . --out-dir vladder-transform
vladder optimize src/transform.cpp --function transform --project . --out-dir vladder-transform
```

The first command predicts the reachable evidence states, expected cost, external authorities,
grammar coverage, and first blocker. The second delegates to the applicable specialist workflow
and writes one `disposition.json`. Edit only the scaffold named by `next_action`, then continue with
`vladder resume --out-dir vladder-transform`.

For a repository inventory with semantic-root deduplication and parallel planning:

```bash
vladder optimize --portfolio --project . --max-regions 50 --workers 4 --out-dir vladder-portfolio
```

The older explicit workflow interface remains available for controlled or scripted investigations.
Create its manifest with:

```bash
vladder workflow init --kind cpp --out workflow.yaml
```

Fill every `TODO`, then run `vladder workflow run --manifest workflow.yaml`. The output's
`promotion-summary.json` is the decision surface; stage reports remain available through its
artifact lineage. A matching rerun is reported as revalidation and does not repeat deterministic
extraction. Use `--force` for fresh physical evidence.

`vladder cpp adapter` generates application-boundary skeletons. These skeletons intentionally
return failure until the workload and complete observable oracle are implemented.

Use `vladder benchmark paired` for same-executable baseline/candidate measurements and
`vladder benchmark compose` to reject overlapping regional speedup arithmetic. Use
`vladder shader synthesize` for portable SPIR-V candidates; structural validation is not output
equivalence and no shader candidate is promotable without a runner manifest.
