## Why

vLadder already has rigorous extraction, proof, benchmark, lifetime, GPU, and contribution
subsystems, but agents still have to reconstruct the evidence state and choose among those
subsystems manually. A technically successful command can stop before proof or physical evidence,
and the actionable blocker may only become clear after expensive work. This makes the agent spend
more effort operating vLadder than evaluating the optimization.

## What Changes

- Make `vladder optimize` the authoritative front door for supported languages and region classes,
  while preserving the existing bounded-C invocation and every specialist command.
- Add `vladder can-optimize` for an early region, authority-boundary, grammar-coverage,
  representativeness, reachability, dependency, artifact-volume, and runtime forecast.
- Add content-addressed orchestration stages, `vladder resume`, structured progress events, and a
  repository-wide portfolio mode.
- Discover project tests, benchmarks, output hashes, timing fields, and build metadata, then emit a
  project-evidence manifest whose unresolved facts are explicit.
- Generate typed adapter, benchmark, device-runner, and remote-executor scaffolds with directly
  executable next commands.
- Normalize all terminal results into evidence badges, a failure taxonomy, a concise five-fact
  summary, and an economic `CONTINUE`, `STOP`, or `ESCALATE` recommendation.
- Add grammar-coverage and capsule-representativeness accounting so a measured negative is not
  confused with an incomplete search vocabulary or an unrepresentative proof unit.
- Prepopulate objective review evidence and support campaign reviews spanning multiple workflows.

## Compatibility

This is an orchestration and ergonomics layer. It does not weaken semantic contracts, proof
requirements, measurement policy, contribution consent, source-promotion gates, or external
protocol boundaries. Existing expert subcommands, manifests, schemas, and bounded-C command-line
arguments remain supported.
