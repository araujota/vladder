# Composition-Native Learned Search RC26 Evaluation

## Decision

`ABANDON_LEARNED_SEARCH_AS_PRIMARY_REDUCTION`

The bounded composition-native experiment failed Gates A, B, and D. Learned ordering remains a
valid optional search-order heuristic, but this representation and policy must not authorize a
larger collection campaign or serve as vLadder's primary effective-search reduction. Exact
canonicalization remains valuable and retains elimination authority.

## Corpus

The exhaustive campaign covered 102 roots, balanced 34 each across DuckDB, llama.cpp, and RocksDB.
The strict post-campaign audit reported:

| Measure | Result |
|---|---:|
| Native states | 66,882 |
| All frontiers | 3,338 |
| Composition frontiers | 3,226 |
| Multi-sibling training decisions | 3,124 |
| Frontier actions | 27,002 |
| Exact transpositions | 38,656 |
| Proof-valid distinct terminals (U2) | 1,333 |
| Material winners (U3) | 0 |
| Retained winners (U4) | 0 |
| Audit failures | 0 |

Canonical transposition collapsed 57.8% of generated search states before learned ordering. The
remaining canonical exhaustive replay represented 27,216 candidate constructions, 19,167 proof
calls, 22,860 compiler calls, and 24.66 cumulative hours of captured cold search cost. No physical
benchmark was part of these bounded terminal evaluations, so U3/U4 recovery is unevaluable.

## Recovery

Useful-terminal recovery by exhaustive-cost fraction:

| Policy | 1% | 5% | 10% | 20% | 30% | 50% | 100% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Random | 1.0% | 4.7% | 9.6% | 20.4% | 29.2% | 47.6% | 100% |
| FIFO | 0.7% | 1.2% | 4.0% | 18.5% | 39.4% | 68.1% | 100% |
| RC24 survival ranking | 6.7% | 25.3% | 33.5% | 45.5% | 54.1% | 74.8% | 100% |
| Frozen Phase-A GPS | 5.9% | 25.0% | 34.8% | 45.1% | 52.4% | 70.4% | 100% |
| Full interaction-frontier | 4.2% | 18.2% | 26.3% | 49.0% | 62.0% | 78.6% | 100% |
| Post-search oracle | 8.9% | 48.2% | 68.0% | 86.5% | 95.8% | 98.6% | 100% |

At 30%, the full model recovered 65.5% on DuckDB, 51.1% on llama.cpp, and 63.7% on RocksDB. The
oracle shows that useful outcomes are concentrated enough for an ideal ordering to satisfy the
bounded 95% gate. The learned representation does not recover that concentration across projects.

Among the 86 roots containing a useful terminal, the full model's first useful/proof-valid discovery
occurred after 3.47% of exhaustive cost on average (23.26 seconds of captured cold search cost),
versus 1.15% (4.11 seconds) for the oracle. Its worst root required 61.4% of exhaustive cost to find
the first useful terminal; the oracle's worst required 12.1%. First material and retained discovery
are unevaluable because those terminal classes are absent.

## Ablations

| Variant | Useful/composition recovery at 30% |
|---|---:|
| No action delta | 69.5% |
| No retained labels | 64.3% |
| No siblings | 63.5% |
| No interaction graph | 63.1% |
| No history | 62.3% |
| Full interaction-frontier | 62.0% |
| Semantic graph only | 61.1% |
| No cost labels | 60.4% |
| Heterogeneous transformer | 57.0% |
| Factor transformer | 56.3% |
| Semantic + history + siblings | 54.4% |

Removing the exact action-delta input improved recovery by 7.5 points. Removing interaction edges,
history, or siblings did not produce the degradation expected if the composition-native context
were transferring robustly. The full model beat semantic-only by only 0.9 points, below the declared
one-point materiality floor. The no-retained-label result has no causal interpretation because the
corpus contains no U4 examples.

## Gates

| Gate | Requirement | Result | Status |
|---|---|---:|---|
| A | composition >=80% and materially above Phase A at 30% | 62.0%; Phase A 52.4% | Fail |
| B | useful recovery >=95% at 30% | 62.0% | Fail |
| C | all material/retained winners at 30% | no U3/U4 evidence | Unevaluable |
| D | A-C and interaction materially beats semantic-only | +0.9 points | Fail |

## Interpretation

The negative result is not evidence that search utility is uniformly distributed: the oracle reaches
95.8% recovery at 30%. It is evidence that the specified pre-expansion semantic, interaction,
history, sibling, and delta representation does not generalize sufficiently across these projects.
In particular, explicit deltas behaved as noise rather than useful transfer signal, while known
interaction structure added less than one point over semantic topology alone.

vLadder should preserve the native trace schema, RC24 auxiliary corpus, exact transposition table,
and priority-only runtime interface. It should not pay for a larger composition-native campaign or
rely on this learned policy for asymptotic reduction. A future reconsideration requires a new causal
representation hypothesis and a corpus with measured U3/U4 outcomes; more examples of the present
representation are not authorized by this experiment.

Machine-readable artifacts are retained locally in
`/tmp/vladder-composition-native-rc26-model/`; the audited corpus is in
`/tmp/vladder-composition-native-rc26-out/`.

Artifact SHA-256 identities:

* corpus audit: `132b5f2e7812ca387137922eac95dfb72e0d9acca6c080d2c156e5782b5c8781`
* evaluation: `cabf79fa7f4bfe2c79e8e5e18654aa406549569296d46b3298fd319b9dfc10bc`
* first-discovery metrics: `5e66c22a2e3c8845b50c3b861dc1d47647a7a4b647312377e5ad677050290814`
