# Conservative Search Pruner RC24 Validation

Date: 2026-08-11

## Decision

The frozen C++-primary corpus supports a conservative pruning signal, but not a large one. The
maximum validated operating point avoids **1.30% of replayed search work** at **99.969% useful-
descendant recall**. A strict zero-miss point avoids **1.27%**. Both artifacts remain shadow-only.

This closes the requested training, calibration, and policy ablation pass before another data
campaign. It rejects the earlier 19.51% branch-reduction point, which missed 41 useful ancestors.

## Frozen Corpus

- 43,153 deduplicated examples
- 770 unique semantic roots across DuckDB, llama.cpp, and RocksDB
- 34,461 learned-policy branches
- 3,254 useful-descendant positives
- 29,923 exhaustive negatives
- grammar: 1,344 branches / 235 positives
- candidate: 8,421 branches / 1,029 positives
- composition: 24,696 branches / 1,990 positives

Post-search subtree size, useful-terminal count, proof outcome, failure class, severity, and cost are
derived supervision or evaluation targets. They are excluded from inference tensors.

## Evaluated Variants

| Variant | Parameters | Recall | Static branches pruned | Misses | Disposition |
|---|---:|---:|---:|---:|---|
| Original relational model | 14.18M | 98.740% | 19.506% | 41 | reject |
| Canonical graph-summary tree | non-GNN | 97.326% | 17.721% | 87 | reject |
| Small staged/focal/hard-mined GNN | 3.11M | 96.466% | 16.175% | 115 | reject |
| Small ordinary-BCE GNN | 3.11M | 99.662% | 3.636% | 11 | reject |
| Frozen-encoder ablation | 3.11M | 99.939% | 0.752% | 2 | reject: weak project fold |
| GNN embeddings + tree head | 3.11M encoder | 99.939% | 1.320% | 2 | reject: candidate recall |
| Three-seed GNN ensemble, selected policy | 3 x 3.11M | 99.969% | 0.528% | 1 | retain shadow |
| Three-seed GNN ensemble, zero-miss policy | 3 x 3.11M | 100.000% | 0.493% | 0 | retain shadow |

The staged high-positive-weight focal objective overfit the easier distinctions and materially hurt
held-project preservation. The smaller encoder and ordinary BCE calibrated better. Freezing the
encoder and replacing the neural head with a boosted tree did not improve the safety frontier.
A 48-point guard sweep over exploration reserve, retrieval support/neighbors, uncertainty limits,
and OOD limits changed avoided work by less than 0.01 percentage point; the safer 1% reserve and
five-neighbor/twelve-example retrieval gate were retained.

## Selected Operating Point

The policy uses independent thresholds by decision stage, ensemble mean plus three standard
deviations, exact-history and nearest-neighbor positive fail-open checks, branch-level and family-
local OOD rejection, and a deterministic 1% exploration reserve. Sparse family-specific thresholds
are disabled; sparse families use the conservative stage threshold.

| Stage | Positives | Misses | Recall | Branches pruned |
|---|---:|---:|---:|---:|
| Grammar | 235 | 0 | 100.000% | 37 / 1,344 (2.753%) |
| Candidate | 1,029 | 0 | 100.000% | 127 / 8,421 (1.508%) |
| Composition | 1,990 | 1 | 99.950% | 18 / 24,696 (0.073%) |
| **Total** | **3,254** | **1** | **99.969%** | **182 / 34,461 (0.528%)** |

Online replay counts a pruned ancestor once and suppresses descendants that would not have been
created. It reports 1.30% avoided work and 99.951% useful-terminal survival.

| Held-out project | Recall | Static reduction | Online work reduction |
|---|---:|---:|---:|
| DuckDB | 100.000% | 0.380% | 1.130% |
| llama.cpp | 100.000% | 0.280% | 0.662% |
| RocksDB | 99.902% | 1.298% | 2.839% |

The zero-miss policy sets a stricter composition threshold. It avoids 1.27% of work, preserves all
observed useful terminals, and provides the preferred risk-intolerant comparison point.

## Safety Behavior

The serving policy fails open for:

- unknown action tokens or grammar families;
- decision-level or family-local OOD embeddings;
- uncertainty above the calibrated stage limit;
- historical exact matches with any useful outcome;
- nearest-neighbor neighborhoods containing useful outcomes;
- deterministic exploration-reserve branches; and
- errors in the serving protocol.

Baseline preservation, deterministic impossibility, semantic memoization, formal proof, compilation,
physical ranking, and promotion remain independent authorities. The model predicts neither legality
nor performance.

## Interpretation

The existing representation is useful: it beats a canonical graph-summary baseline, and safe
grammar/candidate discrimination transfers across held-out projects. Calibration was a real part of
the earlier failure. However, policy changes alone do not approach the desired 70-90% reduction.
Composition distinctions are sparse, contextual, and weakly transferable across these three
projects.

The frozen corpus has therefore reached its practical policy-only ceiling. A future campaign is
justified only if it is targeted at candidate/composition sibling frontiers, preserves parent and
sibling context, and adds independent projects or semantic families. Repeating broad grammar-heavy
enumeration would mostly add examples for the already stronger head.

## Artifacts

- selected held-project policy: `/tmp/vladder-cpp-pruner-ensemble-v21c/policy-final.json`
- zero-miss policy: `/tmp/vladder-cpp-pruner-ensemble-v21c/policy-zero-miss.json`
- calibrated serving artifact: `/tmp/vladder-cpp-pruner-ensemble-v21c/model-conservative.pt`
- base ensemble evaluation: `/tmp/vladder-cpp-pruner-ensemble-v21c/evaluation.json`
- embedding-head evaluation: `/tmp/vladder-cpp-pruner-ensemble-v21c/embedding-head-evaluation.json`
- guard-policy sweep: `/tmp/vladder-cpp-pruner-ensemble-v21c/policy-guard-sweep.json`

These paths identify local research artifacts. No model is included in the release package or
enabled for live search.
