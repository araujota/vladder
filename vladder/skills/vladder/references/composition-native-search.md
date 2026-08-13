# Composition-Native Search

Use composition-native traces only when an exhaustive source-search run emitted the exact parent
state, canonical hash, full sibling frontier, ordered history, action delta, interaction graph,
terminal outcomes, and costs. Reconstructed RC24 decisions remain auxiliary evidence.

Current native traces must carry `vladder-search-policy-training-contract-v1`. The emitter rejects
state/parent inconsistencies, multiple canonical owners, incomplete sibling sets, unrealized child
states, incomplete label permutations, non-owner terminal evidence, summary drift, and stale trace
hashes. `future_policy_training_eligible` requires exhaustive enumeration, canonical identities,
complete frontiers, and terminal outcomes. `search_cost_capture=partial` is visible coverage debt,
not permission to invent cost labels.

The authority order is deterministic impossibility, exact transposition, formally verified
equivalence/dominance, learned ordering, and exhaustive fallback. A learned score changes queue
priority only. A relation head may request a canonical/Z3/Alive2 check; it cannot merge states.
Always build model features through `inference_view`; never expose the completed state set,
transpositions, chosen action, terminal outcomes, labels, or measured cost to the encoder.

```bash
python scripts/build_composition_native_manifest.py \
  --roots-per-project 34 --output composition-native.json
vladder source-search run --manifest composition-native.json \
  --out-dir composition-corpus
python scripts/audit_composition_native_corpus.py \
  --corpus composition-corpus --manifest composition-native.json \
  --output composition-audit.json
python scripts/composition_native_policy.py \
  --corpus composition-corpus --output composition-model \
  --rc24-progress RC24/training-v3/training-v3-progress.json \
  --rc24-manifest rc24-manifest.json
```

Read `evaluation.json`. Report exact transposition reductions separately from model-guided budget
savings. At 30% exhaustive cost, require at least 80% composition recovery, 95% useful-terminal
recovery, and complete material/retained recovery when those terminal classes exist before scaling
the corpus. Production policy qualification still requires 99.9% useful recovery.

The completed RC26 experiment failed those gates: the full interaction model reached 62.0% useful
composition recovery at 30% cost. Treat `ABANDON_LEARNED_SEARCH_AS_PRIMARY_REDUCTION` as the active
disposition. Do not scale that corpus design or install its checkpoint as a production prior. The
native trace format, strict audit, and exact transposition mechanism remain supported evidence and
search infrastructure.

RC27's canonical semantic-state DAG is now the primary exact reduction architecture. RC26 model
artifacts remain ordering research only. New production search should emit `canonical-state-dag.json`
and qualify every reduced run against `exhaustive_canonical`; see
[canonical-state-search.md](canonical-state-search.md).

Use `scripts/composition_policy_oracle.py --checkpoint CHECKPOINT` only as the argv-form
`frontier_oracle.command`. Unknown or OOD actions fail open. `fast` and `guided` are budgeted and
incomplete; `exhaustive` eventually explores every state not closed by exact authority.

Do not train if the audit reports a terminal attached to `canonical_duplicate` or
`verified_equivalent`; terminal evidence belongs to the canonical owner. Do not remove singleton
frontiers from online replay merely because they supply no ranking loss. They are required state
transitions and must inherit the active ancestor priority. For older native v1 evidence, use
`scripts/normalize_composition_native_corpus.py` and rerun the audit; this migration may move an
unchanged terminal record to its canonical owner but may not alter proof, compiler, benchmark, or
cost outcomes.
