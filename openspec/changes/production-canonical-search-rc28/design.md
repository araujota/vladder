# Design

## Runtime Architecture

`ProductionCanonicalSearchEngine` wraps the exact RC27 quotient-DAG engine with a production policy,
resource controller, durable checkpoint store, and telemetry collector. State identity is
`(canonical schema version, SHA-256 digest, canonical bytes)`. A lock-protected per-root
`TranspositionTable` is the sole recursive-exploration authority. Canonical blobs and analyses are
deduplicated by state ID while provenance remains edge-oriented.

## Reduction Policy

Canonical transposition is always enabled. The adaptive policy selects `ENUMERATE`,
`CANONICALIZE_ONLY`, `CANONICALIZE_PLUS_POR`, or `FULL_EXACT_REDUCTION` using rolling construction,
proof, compilation, canonicalization, commutativity, fanout, depth, footprint, and historical
transposition statistics. The policy can only decline an optional reduction; it cannot authorize an
unqualified reduction. Unknown footprints and cost uncertainty fail open.

## Persistence And Memory

Checkpoint files contain canonical schema/search/grammar/source/target identities, canonical state
records, edges, frontier, exploration flags, reduction counters, and cache metadata. Resume rejects
identity mismatches. A memory controller evicts recomputable summaries first and may spill canonical
blobs to a content-addressed store; state identity and collision buckets remain authoritative.

## Qualification

The release suite replays RC26/RC27 evidence, runs adversarial terminal-set fixtures, audits action
footprints, compares raw/canonical/POR scaling, stresses concurrent duplicate insertion, enforces
memory ceilings, and measures real proof/compiler work on source-search roots. Reduction mechanisms
are reported independently and production defaults list every disabled experimental authority.
