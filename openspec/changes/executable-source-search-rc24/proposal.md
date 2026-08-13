## Why

vLadder's semantic vocabulary and declarative lowering registry have grown faster than automatic
source-to-candidate closure. A callable source route currently proves only that a specialist API
exists; it does not prove that a compiler-extracted root can be bound to that API, exhaustively
enumerated, compiled, verified, deduplicated, reconstructed, or emitted as authoritative search
lineage. This weakens ordinary optimization coverage and produced a large source-applicability
corpus with no supervised pruning authority.

## What Changes

- Introduce one executable source-search engine used by normal optimization and v3 training export.
- Record stage-specific closure for recognition, contract inference, applicability, enumeration,
  emission, compilation, proof, physical identity, and source reconstruction.
- Infer exact bounded contracts for canonical loops, ordered prefix/suffix reductions, caller-owned
  dataflow, finite state/cache transitions, and versioned lifetime projections.
- Enumerate declared finite parameter domains, preserve composition lineage, and propagate useful
  descendant evidence through the existing v3 labeler.
- Add content-addressed compilation/proof caches and deterministic parallel root execution.
- Permit `PRUNE_HIGH_CONFIDENCE` only after exhaustive bounded enumeration or a registered sound
  inapplicability/contract proof.

## Non-Claims

This change does not enumerate all equivalent programs. It does not infer arbitrary ownership,
concurrency, callback, driver, network, or external-library semantics. Such boundaries remain
explicitly blocked or require a finite protocol contract. Exhaustiveness is always relative to a
named grammar version and finite parameter domain.
