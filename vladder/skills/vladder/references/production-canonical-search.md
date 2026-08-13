# Production Canonical Search

Use the public modes as follows:

```bash
vladder source-search run --manifest MANIFEST --out-dir OUT --search-mode exhaustive
```

- `fast`: canonical search under explicit work/time limits.
- `guided`: larger budget with optional ordering.
- `exhaustive`: every unique canonical state after qualified exact reduction.
- `exhaustive_canonical`: no-POR terminal-set oracle.
- `exhaustive_reduced`: force qualified POR for controlled comparison.
- `legacy_path_debug`: historical path search only.

Read artifacts in this order:

1. `executable-closure.json` for semantic reachability;
2. `production-canonical-search.json` for effective mode, cost gate, footprint, cache, resource,
   checkpoint, and disabled-authority evidence;
3. `canonical-state-dag.json` for exact states, edges, terminals, and reduction attribution;
4. `executable-search.json` for proof and compiler dispositions.

POR requires complete conservative footprints and state-scoped byte-identical AB/BA outcomes.
Unknown means dependent. A cost-gate rejection does not reduce completeness; it only spends more
search work. A memory, work, or time stop means the run is incomplete and must not train dead-subtree
labels or support exhaustive claims.

For long runs, set `search_checkpoint`, then use `search_resume` with the same file. Resume must
reject changed source semantic hash, grammar semantics, target, or canonical schema. Identity data
must remain authoritative even when recomputable analyses are evicted.

ML may order surviving states only. Never enable learned deletion, unqualified dominance/macros,
coarse optimization-equivalence collapse, or global ownership/protocol e-graphs from a score.

Before publishing a vLadder build, run:

```bash
vladder release smoke-canonical-search \
  --out build/production-canonical-search-smoke.json
vladder release canonical-search-evidence
```

All eight stages are release-blocking. Read the failed stage's assertions and metrics; do not rerun
away canonical mismatch, unsafe POR, identity bypass, or silent incremental divergence. A noisy
timing failure may be investigated and repeated, but the expensive Z3/Clang fixture must ultimately
show positive measured net savings.

For model-data collection, treat `composition-native-search-trace.json` as the authoritative
frontier artifact and v3 packets as auxiliary encoder/branch supervision. A policy-ready native
trace carries `vladder-search-policy-training-contract-v1` and must pass emitter integrity for
canonical ownership, complete sibling cardinality, ordered history, action deltas, terminal
lineage, labels, costs, and summary/hash consistency. Never tensorize the completed trace directly;
use `inference_view`, which strips all future states, selected actions, transpositions, outcomes,
labels, and measured timing. ML orders surviving actions or proposes exact checks only.
