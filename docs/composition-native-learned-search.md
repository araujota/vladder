# Composition-Native Learned Search

## Authority

The composition policy answers which legal state to explore next. It never proves impossibility,
equivalence, dominance, correctness, or performance. Runtime authority remains:

1. deterministic impossibility;
2. exact canonical transposition;
3. formally verified equivalence or dominance;
4. learned ordering;
5. exhaustive fallback.

`fast` and `guided` may stop at a budget. `exhaustive` eventually visits every state not closed by
the first three authorities.

## Native Evidence

`vladder source-search run --mode exhaustive` writes
`composition-native-search-trace.json`. Unlike the historical reconstructed decision bundle, it
records at enumeration time:

- the exact parent semantic state and canonical hash;
- ordered transformation history;
- every legal sibling in one frontier;
- child semantic graph and structural state delta;
- explicit transformation interactions and factor nodes;
- exact transpositions and verifier-approved aliases;
- U0-U4 terminal outcomes and backward-propagated sibling advantage;
- expansion, proof, compiler, benchmark, and evaluation costs when those operations run.

Post-search outcomes are absent from `inference_view`; relabeling a completed trace cannot change
model input tensors.

## Interaction Graph

The second graph makes known optimization relationships explicit: shared owners and memory regions,
contract requirements/creation/invalidation, materialization creation/removal, lifetime extension
or shortening, authority movement, ordering, cross-TU dependencies, and declared
enable/disable/conflict/commutativity/subsumption. Multi-action conditions use factor nodes. vLadder
does not invent a commutativity or dominance edge from observed outcomes.

The representation follows the same division used in learned branching research: graph state is
encoded and sibling actions are trained by relative preference rather than independent deletion
labels ([Gasse et al., 2019](https://arxiv.org/abs/1906.01629)). The local/global encoder ablation is
based on the GraphGPS recipe ([Rampasek et al., 2022](https://arxiv.org/abs/2205.12454)); factor
nodes follow the standard incidence-expansion approach used to pass messages over higher-order
hypergraph relations ([Feng et al., 2019](https://arxiv.org/abs/1809.09401)). These papers motivate
representation and training choices, not semantic authority.

## Campaign

Select bounded composition roots from prior exhaustive evidence:

```bash
python3 scripts/build_composition_native_manifest.py \
  --roots-per-project 34 \
  --output composition-native-manifest.json
vladder source-search run \
  --manifest composition-native-manifest.json \
  --out-dir composition-native-corpus
```

The selector requires wide/deep composition evidence and balances DuckDB, llama.cpp, and RocksDB.
It does not pad a project with trivial one-step roots. Exhaustive terminal materialization can be
large; `artifact_retention: decisive` deletes reproducible source and assembly products immediately
after each cold terminal result enters the content-addressed cache, then preserves compressed native
traces and one full forensic root per project. Run the strict audit before training:

```bash
python scripts/audit_composition_native_corpus.py \
  --corpus composition-native-corpus \
  --manifest composition-native-manifest.json \
  --output composition-native-audit.json
```

The audit rejects schema or lineage failures, stale trace hashes, terminal evidence attached to a
transposed duplicate rather than its canonical owner, and decisive summaries whose artifact hashes
no longer match. `scripts/normalize_composition_native_corpus.py` is a deterministic migration for
older v1 traces affected by canonical terminal ownership; it does not regenerate or alter proof,
compiler, benchmark, or search-cost outcomes.

## Training And Evaluation

```bash
python scripts/composition_native_policy.py \
  --corpus composition-native-corpus \
  --rc24-progress RC24/training-v3/training-v3-progress.json \
  --rc24-manifest rc24-manifest.json \
  --output composition-policy
```

The curriculum uses RC24 only for semantic-encoder pretraining, then trains listwise/pairwise native
frontier imitation, followed by cost-aware fine-tuning. Project identity and source language are
split metadata, not policy features. The report compares FIFO, random, the handwritten heuristic,
RC24 action priors, the actual frozen leave-one-project-out Phase-A GPS checkpoints, semantic-only
models, contextual variants, the full
interaction model, exact transposition, and the post-search oracle.

The headline curve is exhaustive cost consumed versus useful, proof-valid distinct, material, and
retained terminal recovery at 1, 5, 10, 20, 30, 50, and 100 percent. Exact reductions and learned
budget effects remain separate. The bounded scale gates are 80% composition recovery, 95% useful
recovery, and complete material/retained recovery at 30% work. Production remains stricter:
99.9% useful recovery within 30% work.

Singleton frontiers remain in online replay even though they carry no listwise supervision. They
are mandatory state transitions and inherit their ancestor's priority; removing them from replay
can make ranked descendants unreachable and invalidates every recovery curve, including the oracle.

## Runtime Oracle

```bash
python scripts/composition_policy_oracle.py \
  --checkpoint composition-policy/fold-duckdb-factor-transformer.pt
```

Use that command as `frontier_oracle.command` in a source-search manifest. Unknown action tokens are
marked out of distribution and receive an exploration bonus. Sparse transformation families and
high-uncertainty actions are likewise promoted in the queue; this changes ordering only.
Equivalence pairs are proposals only and are ignored unless the search is configured with an exact
verifier.

Terminal caches preserve the original cold proof/compiler evaluation cost. A cache hit records its
read latency separately and never replaces intrinsic subtree cost in training labels.
