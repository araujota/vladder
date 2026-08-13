# Lazy Executable Search

Use `vladder source-search run --manifest MANIFEST --out-dir OUT` when the task requires real
candidate lineage or contextual search-policy data. The generator exposes every partial or terminal
semantic state before descendant expansion or expensive source/proof/compile materialization,
canonicalizes exact equivalent states, scores legal sibling actions jointly, and emits one
parent-linked v3 trace plus contextual `SearchDecision` bundles.

With `family: auto`, family dispatch is part of that trace and the live decision surface. Soundly
inapplicable families close before the oracle; each applicable or contract-incomplete family is a
depth-zero branch. Expanding one branch enters only that family's descendants.

Inspect in this order:

1. `executable-closure.json`: first incomplete stage and bounded parameter domains.
2. `canonical-state-dag.json`: authoritative unique states and all transformation edges, when present.
3. `executable-search.json`: terminal proof, compile, and physical-identity dispositions.
4. `executable-search-trace.json`: compatible path lineage and observations.

Never convert an incomplete subtree into a negative. Hard elimination is restricted to sound
legality/contract proofs, canonical identity, sound dominance, and verifier-accepted equivalence.
Learned scores change priority only. Unknown grammar and OOD states use stable fail-open ordering.
Branches marked `decision_surface=deterministic`, `canonicalized`, or `synthetic_wrapper` are
retained for audit but excluded from learned-policy training and evaluation.

Configure an argv-form persistent ordering oracle under `frontier_oracle.command`. vLadder sends
`vladder-frontier-oracle-protocol-v1` JSON lines containing the parent, action history, and complete
legal sibling frontier. Timeouts, crashes, malformed responses, and OOD roots preserve stable
grammar order. The oracle may spend expansion budget; it may not establish semantic impossibility.
Prefer `search_mode: exhaustive_reduced` for exact composition work. Use `exhaustive_canonical` as
the terminal-set oracle and `guided_reduced` only for priority. Legacy `fast`, `guided`, and
`exhaustive` remain available for existing manifests.

Selected-build C++ composition exposes baseline, unroll, vector-width, and interleave choices per
semantically captured region. The oracle sees each partial choice before schedule-specific source,
Z3 proof, candidate IR, or the full translation-unit candidate is generated. Surviving regional
choices are materialized once and reused across terminal compositions. Shadow mode remains the
authority for descendant labels.

Source-executable classes currently include deep byte-predicate realization, ordered prefix/suffix
reduction, exact bit-popcount reduction, and bounded
compaction/codec/delta/AoS-reduction/quantized-block kernels. Lifetime,
cross-TU, and finite protocol roots produce proved plans but stop before owning source realization
unless a separate implementation and physical runner close those stages.

Manifest runs emit one local schema-validated v3 bundle per root under `training-v3/`. Inspect the
incremental `training-v3-progress.json` while the run is active, then the campaign's
`training_v3.status_counts` and `label_counts`; a successfully completed search with a
failed bundle is a data-contract failure, not usable training evidence.
Do not treat progress as complete until `complete` is true and record count equals expected count.

For pruning supervision, exhaust every tractable bounded root and a stratified set of deeper
composition roots. Budget-limited broad roots are still useful for grammar applicability and OOD
coverage, but every open frontier and affected ancestor must remain `KEEP_UNCERTAIN`. Never turn an
unvisited Cartesian combination into a negative. Root resume uses a request-content fingerprint;
terminal source/proof/compile results are cached atomically and survive interruption.
