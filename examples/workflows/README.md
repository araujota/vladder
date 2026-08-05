# Agent Workflow Examples

Create a release-candidate workflow manifest with:

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
