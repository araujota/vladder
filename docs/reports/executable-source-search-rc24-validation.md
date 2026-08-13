# Executable Source Search RC24 Validation

RC24 validates policy-interleaved lazy expansion separately from source-recognition coverage.

## Four-project campaign

The monitored shadow run used 48 real roots, split evenly across llama.cpp, DuckDB, RocksDB, and
Apache DataFusion. Two DataFusion ordered-byte roots reached complete executable enumeration. The
remaining 46 roots stopped at contract recognition and were not interpreted as failed optimization
branches.

The two closed roots each enumerated four concrete candidates. Every candidate compiled and passed
its bounded family proof. The authoritative v3 conversion produced these nonbaseline labels:

| Label | Count |
|---|---:|
| `KEEP` | 9 |
| `PRUNE_HIGH_CONFIDENCE` | 3 |
| `BLOCKED_BY_CONTRACT` | 1 |
| `KEEP_UNCERTAIN` | 45 |

The label total includes grammar and descendant branches. Depth reached three for executable roots.
All 48 per-root v3 bundles passed the public schema after correcting the blocked-root selection-policy
encoding.

## Decision

The campaign passes the engine and lineage gate but fails the model-training gate. Two executable
roots from one grammar and one project cannot support held-out useful-descendant recall or grammar
diversity claims. No pruning model was trained from this run.

The result localizes the next limitation: executable recognition and lowering coverage in real
repositories, not eager candidate materialization or lineage serialization. Supported grammars can
now be expanded lazily and intercepted before child materialization; unsupported semantic roots stay
visible as coverage debt.

Artifacts from the local validation run are under `/tmp/vladder-rc24-four-project-run`; temporary
artifacts are not release inputs.

## Expanded exhaustive campaign

After adding production selected-build closure and canonical native lowering, the same four-project
portfolio was rerun over 48 roots. Eighteen roots reached source-executable closure. Twenty-nine
roots were exhaustive within their declared regional domain; the remaining first incomplete stages
were contract inference (17), source emission (11), and recognition (2). Those incomplete roots
remain coverage evidence, not failed optimization candidates.

The largest closed regional grammar enumerated and resolved all 4,096 Cartesian terminals. Terminal
realization compiled, proved, and assembly-deduplicated candidates in isolated worker processes
without changing lazy branch order or lineage. The complete v3 campaign contains:

| Label | Count |
|---|---:|
| `KEEP` | 480 |
| `PRUNE_HIGH_CONFIDENCE` | 5,713 |
| `KEEP_UNCERTAIN` | 138 |
| `BLOCKED_BY_CONTRACT` | 414 |

All 48 records pass v3 validation. Candidate-dense trees are represented by complete-subtree
packets rather than oversized documents; the campaign produced 904 packets, with the dense root
using 596 packets. Packetization retains every terminal observation and does not convert incomplete
evidence into a negative.

This result corrects the earlier supervision failure: bounded executable roots now provide actual
generated, proved, compiled, deduplicated terminal outcomes and bottom-up useful-descendant labels.
Contract-blocked roots remain explicit unknowns. Root- and project-held-out evaluation is still
required before any live pruning claim because branch volume is concentrated in a few dense roots.

## Preliminary pruning-model evaluation

A 14,171,331-parameter relational shadow model was trained on 6,745 branch examples from 47 usable
semantic roots, with equal project mass and equal semantic-root mass within each project. Four
leave-one-project-out folds produced:

| Metric | Result |
|---|---:|
| Held-out useful branches | 432 |
| Missed useful branches | 112 |
| Useful-descendant recall | 74.07% |
| Search-space reduction | 46.86% |

The model is not live-eligible. It fails the zero-miss rule and the minimum-positive-path evidence
gate. DataFusion and DuckDB abstained safely but pruned nothing; the llama.cpp and RocksDB folds
pruned material search volume while missing useful composition descendants. This is now a model
generalization and corpus-diversity result, not a labeling ambiguity: complete regional searches
provide real terminal labels, but 48 roots do not cover enough cross-project instances of the same
semantic branching decisions to authorize pruning unfamiliar projects.

At retrospective zero-miss thresholds, the available held-out frontier removes only negligible
search volume. The next corpus must add more independent semantic roots per grammar/action family,
especially useful composition paths, before increasing model capacity or enabling live decisions.

## C++-primary exhaustive corpus

The release-defining follow-up focuses on DuckDB, llama.cpp, and RocksDB C++ rather than treating
shallower Rust, Zig, or Julia coverage as a disqualifier. Tranche 1 completed 264 independent
semantic roots with no failed v3 records:

| Project | Roots | Model-eligible positive | Model-eligible negative | Kept uncertain |
|---|---:|---:|---:|---:|
| DuckDB | 89 | 587 | 4,402 | 162 |
| llama.cpp | 82 | 259 | 3,554 | 208 |
| RocksDB | 93 | 334 | 1,388 | 118 |
| **Total** | **264** | **1,180** | **9,344** | **488** |

The model surface excludes baselines, deterministic impossibility, canonicalized duplicates,
synthetic wrappers, and contract-blocked branches. Positive utility derives from generated,
proof-valid, physically distinct C++ or LLVM terminals and propagates to required ancestors. The
264 roots cover 36 project/family cells; 33 contain at least one positive descendant. By search
stage, positives comprise 102 grammar-family, 356 candidate-family, and 722 composition decisions.

Closure remains deliberately bounded. Of 264 roots, 167 are exhaustive within their declared
domain, 24 expose source-executable proof units, and the rest retain explicit contract, proof, or
source-reconstruction frontiers. A maximum of three selected-build regions is composed per corpus
root; omitted eligible regions are reported outside the exhaustive claim rather than silently
pruned.

Dense translation-unit products exposed a campaign scaling issue, not a search-label issue. The
runner now supports `artifact_retention: decisive`: after standalone v3 emission it removes
reproducible objects, gzip-compresses the complete result and trace, preserves a compact summary and
closure, and can resume from the compressed result. One full forensic root per project remains
unpacked. Per-root progress records are request-fingerprinted and preloaded on resume.

Tranche 1 does not meet the conservative 3,000 held-out-positive gate by itself. A second
non-overlapping C++ tranche is therefore required before retraining; no live-pruning claim follows
from the counts above.

## Completed C++ corpus and held-project evaluation

The completed campaign combines two family-stratified source tranches, one strong-symbol object
tranche, and six explicit alternate selected-region domains. All 794 campaign records pass the v3
contract. They cover 770 unique semantic roots after trainer-side branch deduplication and contain
29,050 concrete terminals, of which 17,341 are reported as replacement-ready inside their bounded
proof envelopes. Of the roots, 552 are exhaustive within their declared regional domains; blocked
or omitted regions remain explicit outside those claims.

The trainer loaded 43,153 deduplicated branch examples. Its learned-policy surface contains 3,254
useful-descendant positives and 29,923 exhaustive negatives; baselines, deterministic closure,
canonicalized states, synthetic wrappers, and contract-blocked branches are excluded. Every project
and every grammar/candidate/composition head has both positive and negative evidence:

| Held-out project | Useful branches | Misses | Recall | Branch reduction |
|---|---:|---:|---:|---:|
| DuckDB | 1,473 | 21 | 98.57% | 25.32% |
| llama.cpp | 756 | 3 | 99.60% | 12.30% |
| RocksDB | 1,025 | 17 | 98.34% | 21.32% |
| **Aggregate** | **3,254** | **41** | **98.74%** | **19.51%** |

The trained artifact is a 14,178,051-parameter, three-head relational model. It was trained on the
local RTX 5080 and is stored at `/tmp/vladder-cpp-pruner-v20/model.pt`; the complete evaluation is
`/tmp/vladder-cpp-pruner-v20/evaluation.json`. These temporary paths identify the evaluated local
artifact and are not package inputs.

The model is **not live-eligible**. It passes the corpus-size gates but fails the zero-held-project-
miss gate. Grammar-family decisions had zero misses; candidate and composition decisions account for
all 41. At retrospective zero-miss thresholds, the held-out folds could remove only 0.96% to 3.94%
of policy branches. That frontier shows real discrimination, but not the 70% to 90% reduction at
99.9% recall sought for live deployment. vLadder therefore keeps the oracle shadow-only and fails
open in production search.

This is a substantially stronger result than the 48-root pilot: recall increased from 74.07% to
98.74%, the supervision gate is now satisfied by generated/proved/compiled descendants, and the
remaining limitation is specifically cross-project candidate/composition generalization and
calibration. It is no longer a proxy-label, packet-loss, or eager-enumeration failure.

## Conservative frozen-corpus follow-up

The 19.51% operating point above is now superseded and remains rejected. A subsequent frozen-corpus
pass evaluated smaller encoders, stage-specific objectives, independent-seed ensembles, one-sided
risk calibration, branch-level OOD, historical retrieval, boosted-tree baselines, hard-example
objectives, and online lazy-tree replay. The maximum policy satisfying the 99.9% aggregate
useful-descendant floor avoids 1.30% of replayed work at 99.969% recall; a zero-miss policy avoids
1.27%. Neither is live-enabled. See
[the conservative validation report](conservative-search-pruner-rc24-validation.md).
