# Learned Search Prior

Use the learned search policy only after ordinary legality. It cannot introduce a precondition,
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

1. Register a finite lazy action domain and apply deterministic legality and canonicalization.
2. Make automatic grammar-family dispatch a real lazy action, then emit each partial or terminal
   branch state, with its complete ancestor action path, before
   constructing children or concrete source/proof/compile artifacts.
3. Canonicalize exact states, then score all legal siblings jointly. ML controls order, not deletion.
4. If uncertainty or distribution checks fail, preserve stable grammar order or use exhaustive search.
5. Send selected candidates through unchanged proof, compile, differential, benchmark, and
   composition gates.
6. Append failures, ties, compiler identities, wins, and composed regressions as immutable
   experience.

Use the persistent JSON-lines frontier oracle configured by `source-search` for live intervention.
Do not enumerate a Cartesian product and rank it afterward. Exact canonicalization and formal
equivalence can collapse state; a learned model may only propose an equivalence check.
Exclude deterministic closure, canonical memoization, and compatibility wrappers from model
metrics; the oracle is never asked to decide those states in production.

For source-checkout experiments, `scripts/search_pruner.py train` consumes only complete v3
campaigns and builds the stage-specific graph/action-lineage reference model. `serve` implements
the persistent oracle protocol. Install `vladder[ml]`; do not enable the model unless its
`evaluation.json` reports `live_eligibility.eligible: true`.
Repeat paired `--progress` and `--manifest` arguments to combine campaigns. Do not concatenate
bundles manually: the trainer validates campaign completeness, preserves project provenance,
deduplicates identical branches, and rejects conflicting supervision.
For C++ corpora, source-line roots come from `scripts/build_cpp_search_manifest.py`; a later
non-overlapping strong-symbol tranche can come from `scripts/discover_cpp_object_roots.py` and the
same exact built objects. `artifact_retention: decisive` is valid only with standalone v3 emission:
it preserves compressed resumable search evidence, compact summaries, closure, and all packets
while deleting reproducible terminal products. Keep representative full roots for audit.
If useful roots omitted explicit selected-build regions, `scripts/build_cpp_search_topup_manifest.py`
may create a bounded alternate-domain tranche. It must select named omitted regions, retain the
parent root and positive-count provenance, and keep the original proof and label gates. Do not use a
top-up to relabel old branches, duplicate an existing domain, or weaken model eligibility.

The RC24 C++-primary reference evaluation is historical shadow-only. A three-member 3.1M-parameter ensemble
reaches 99.969% held-project useful-descendant recall while avoiding 1.30% of replayed work; a
zero-miss policy avoids 1.27%. Grammar and candidate decisions have no misses at the selected
operating point, while composition remains the limiting stage. The earlier 19.51% branch-reduction
point missed 41 useful branches and is rejected. Treat the conservative result as evidence that
safe pruning is possible but still small. Do not continue tuning or deploy that hard-pruning head.

The next program trains `scripts/contextual_search_policy.py` on complete sibling frontiers. Its
primary artifact is a held-project recovery curve: exhaustive work consumed versus useful and
retained terminals recovered. Phase A requires at least 99% useful-terminal recovery by 30% work;
future frontier-native data raises that gate to 99.9%. Compare FIFO, random, handwritten, RC24,
graph-only, graph plus history, frontier attention, GIN/GAT, GPS, and exact transposition collapse.

Composition-native campaigns supersede Phase-A reconstruction for composition policy labels. Use
`scripts/build_composition_native_manifest.py`, require complete
`vladder-composition-native-search-trace-v1` artifacts, and train with
`scripts/composition_native_policy.py`. The model consumes explicit interaction and factor graphs,
history, siblings, and exact child deltas. Its runtime oracle changes queue order only. Keep exact
transposition, verifier-approved aliases, and learned finite-budget savings as separate metrics.
Compare against the frozen Phase-A leave-one-project-out GPS checkpoints, not a hand-built proxy.
Require terminal caches to retain intrinsic cold proof/compiler cost separately from cache-read
latency, and exclude normalized held-out topologies from training folds.

Never report a rank score as correctness, speed, or production safety. Use it only as search
priority. Read `docs/learned-search-prior-v0.md` for schema, calibration, split, and scale gates.
Contributed v3 records preserve bounded sanitized topology, structured action, hardware/workload,
branch lineage, search stage, completeness authority, search cost, observation sequences, and
separate direct/descendant utility targets. Treat one search as a ranking and lineage group. Never
train a negative pruning target from `KEEP_UNCERTAIN`, historical v1 telemetry, or flat v2 evidence.
Before budgeted deployment, run `vladder prior evaluate-matrix` and inspect every root, project,
language, hardware, and temporal view separately; an aggregate score may not hide a weak holdout.

## Candidate-Dense Traces

One campaign root may contain a `bundles` array. Load every packet. `full_trace` is the ordinary
single-packet form. `complete_subtree` is a complete local tree whose root records an
`external_parent_branch_id`; it retains proof-derived KEEP and exhaustive-negative authority.
`partial_snapshot` represents incomplete context and fails open. Packetization is not pruning and
must never remove terminal proof, compile, identity, or lineage observations.
