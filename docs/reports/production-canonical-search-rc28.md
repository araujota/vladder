# Production Canonical Search RC28 Qualification

## Disposition

`PRODUCTION_CANONICAL_SEARCH_APPROVED`

The qualification passed every declared gate: RC26 replay, fresh RC27 adversarial replay, exact
terminal preservation, three-system source recapture, scaling, measured expensive-root value,
concurrent identity, memory, and footprint coverage.

## Historical And Exact Evidence

- RC26 replay: 66,882 states, 38,656 recorded transpositions (57.80%), 1,333/1,333 U2 terminals
  preserved, 19,167 proof and 22,860 compiler calls represented by the captured corpus.
- Fresh RC27 envelope: 35,280 raw states, 1,795 unique canonical states, 295/295 terminals
  preserved, and 1,805 candidate constructions after POR.
- Cheap negative control: reduced traversal remains slower than raw traversal because AB/BA
  verification and canonicalization dominate trivial terminal work. Production therefore uses the
  adaptive cost gate rather than enabling POR universally.

## Measured Expensive Root

The qualification root executed one real Z3 proof and one optimized clang object compilation per
terminal.

| Measurement | Raw paths | Canonical + POR |
|---|---:|---:|
| Terminal evaluations | 48 | 8 |
| Proof calls | 48 | 8 |
| Compiler calls | 48 | 8 |
| Candidate constructions | 79 | 43 |
| Measured wall time | 746.74 ms | 173.32 ms |

This avoided 40 proof calls and 40 compiler calls and reduced measured wall time by 76.79% while
preserving all eight unique terminal states. This is a search-system result, not optimized-program
runtime performance.

## Real Systems

Fresh clang/compilation-database capture qualified DuckDB `StringValueResult`, llama.cpp
`ggml_compute_forward_sum_f32`, and RocksDB
`DBImplSecondary::CalculateResumedCompactionBytes`.

For each system, one-, two-, and three-region selected-build composition preserved exact terminal
sets. At three regions, 3,481 raw states reduced to 729 unique/reduced constructions and 512
semantic terminals, with complete footprints on all 1,944 observed composition actions.

The controlled width-4 to width-5 scaling step increased raw candidate construction by 10.00x,
while reduced construction increased 2.876x and unique terminal proof/compiler work increased 2x.
All three source-anchored systems therefore met the specification's `acceptable` scaling gate.

## Resources

- Concurrent registration: 4,096 registrations across 16 workers produced exactly 17 canonical
  owners at approximately 21k registrations/s in the qualification run.
- Peak bounded-resource run memory: 1.95 MB under a 64 MiB ceiling.
- Selected-build footprint coverage: 810/810 observed actions complete in the resource fixture.
- Hash collisions, incomplete footprints, alias/contract overlap, incremental-hash divergence,
  hidden macro descendants, and false dominance remain fail-open regression fixtures.

## Production Defaults

Enabled: canonical identity/transposition, deterministic dependencies, explicit alpha/symmetry,
qualified cost-gated POR, proof/compile/physical ranking.

Disabled as deletion authority: learned scores, unqualified dominance, unqualified macros, coarse
optimization equivalence, and global ownership/protocol e-graphs.

The concise machine-readable evidence is
[`production-canonical-search-rc28-summary.json`](production-canonical-search-rc28-summary.json).
