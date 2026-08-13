# Tasks

## Contracts And Runtime

- [x] Add frontier decision and supervision types with strict inference/outcome separation.
- [x] Emit trajectory/frontier records from future exhaustive lazy searches.
- [x] Add deterministic transposition accounting and verified-equivalence proposal hooks.
- [x] Add fast, guided, and exhaustive best-first modes without learned hard deletion.

## Existing Corpus

- [x] Reconstruct complete sibling frontiers and oracle ordering from RC24 v3 traces.
- [x] Mark unavailable retained and canonical-state evidence explicitly.
- [x] Preserve the RC24 encoder, branch labels, retrieval, and OOD data as auxiliary inputs.

## Learning

- [x] Implement listwise frontier training with explicit action-history encoding.
- [x] Evaluate GIN, GIN/GAT, and GPS-style graph encoders at controlled capacity.
- [x] Add a proposal-only equivalence/redundancy head.

## Evaluation

- [x] Replay FIFO, random, handwritten, RC24 ranking, and contextual policies online.
- [x] Report recovery curves, first discovery, physical tool calls, frontier size, and transpositions.
- [x] Apply Phase A acceptance and decide whether a new composition-heavy campaign is warranted.

## Release Integration

- [x] Update README, learned-prior guidance, skill references, and artifact documentation.
- [x] Run focused tests, strict OpenSpec validation, and release-facing regression tests.
