# Contextual Best-First Search Phase A

Date: 2026-08-12

## Disposition

`phase_a_failed`

The contextual policy is implemented as an ordering authority, but the RC24 replay did not meet
the release gate. No learned hard pruning is enabled and no new exhaustive corpus campaign is
authorized by this result.

## Corpus

* 43,153 RC24 branch examples
* 770 historical semantic roots; 751 contributed complete reconstructable decision trees
* 3,867 complete sibling-frontier decisions
* 29,241 frontier actions
* project holdouts: DuckDB, llama.cpp, and RocksDB
* retained-terminal evidence: unavailable
* canonical-state/transposition evidence: unavailable in RC24
* historical proof/compiler call counts: recorded as zero because RC24 omitted terminal cost capture

RC24 remains useful for graph-encoder pretraining, action/contract supervision, OOD vocabulary,
historical retrieval, and branch-level auxiliary tasks. It cannot establish retained-candidate or
transposition recovery.

## Models

Controlled models used the same canonical graph/action vocabulary and stayed below 700k parameters:

* GIN graph only
* GIN plus explicit action-history Transformer
* GIN plus history plus sibling frontier attention
* alternating GIN/GAT plus history/frontier
* GPS-style local message passing plus global graph attention and history/frontier

Training used branch-level encoder pretraining, listwise sibling imitation, pairwise useful/dead
and distance ordering, plus utility, subtree-cost, and redundancy auxiliary heads. The redundancy
head proposes checks only; it has no merge authority.

## Held-Project Replay

Useful-terminal recovery by exhaustive work:

| Policy | 10% | 20% | 30% | 50% |
|---|---:|---:|---:|---:|
| FIFO | 0.0% | 0.0% | 10.4% | 36.1% |
| Random | 9.7% | 18.6% | 30.0% | 54.4% |
| Handwritten | 9.7% | 20.2% | 30.7% | 55.4% |
| RC24 survival ranking | 9.7% | 18.6% | 30.0% | 54.3% |
| GPS contextual policy | 19.8% | 40.8% | **61.0%** | **82.0%** |
| Post-search oracle | 38.5% | 79.4% | 100.0% | 100.0% |

At 30% work, GPS held-project recovery was:

* DuckDB: 62.7%
* llama.cpp: 69.8%
* RocksDB: 52.9%

Among all useful branches, candidate-stage recovery reached 95.2% at 30% work. Composition-stage
recovery was 61.0% and dominates useful terminal count. The reconstructed corpus did not expose a
meaningful grammar-stage terminal metric, so grammar recovery is unavailable rather than zero.

The acceptance requirement was at least 99% useful-terminal recovery within 30% work. The observed
61.0% fails by 38 percentage points. Retained/best-terminal acceptance could not be evaluated.

## Runtime And Data Changes

* Added stable priority-queue search with `fast`, `guided`, and `exhaustive` modes.
* Forced exhaustive semantic authority in all three modes; ML cannot return a deletion decision.
* Applied deterministic legality, sound dominance, and exact state memoization before scoring.
* Added proposal-only learned equivalence, gated by an exact verifier.
* Added action-history and full sibling-frontier JSON-lines protocol.
* Added `vladder-search-decision-bundle-v1` with inference/outcome field separation.
* Future traces retain canonical state hashes, frontier snapshots, selected actions, proof/compiler
  costs, exact transpositions, terminal lineage, and retained outcomes when observed.
* Added failure-safe ordering: malformed, timed-out, unknown, and OOD scores preserve stable order;
  uncertainty raises exploration priority rather than authorizing deletion.

## Decision

The learned best-first architecture has clear signal and materially beats all non-oracle baselines,
but it does not provide the required search reduction. A broad new campaign is not justified yet.
The next bounded study should target composition-heavy, frontier-native traces with retained
outcomes and exact state hashes, and should test whether richer parent/composition state closes the
gap. If that study still requires more than 50% work for near-complete recovery, learned search does
not currently provide the intended asymptotic benefit.

The runtime and data-contract improvements remain useful independently: exact transposition is a
completeness-preserving reduction, and learned ordering improves anytime discovery without placing
semantic correctness under model authority.
