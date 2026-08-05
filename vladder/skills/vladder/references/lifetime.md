# Lifetime-Aware Realization

Use this workflow when profiling shows repeated derivation, validation, serialization, decoding,
allocation, materialization, boundary transfer, or residency after final use.

## Authority Boundary

- The manifest declares semantic validity. Traces never create an invariant.
- The trace measures construction, consumption, mutation, invalidation, retirement, destruction,
  and transfer for stable semantic identities and scope instances.
- Scope containment is a partial order. Two peer frames, records, or transactions are not one
  reusable lifetime merely because both belong to the same process.
- Reject ambiguous authority, incomplete mutation classification, missing fallback, or an
  unsupported publication/retirement protocol.

## Required Manifest Facts

For every information item declare:

- authoritative source projection and concrete representation;
- current scope, construction policy, consistency, publication, and placement;
- candidate scopes and placements;
- consumers and any independent observers;
- every mutation, partitioned into invalidators and non-invalidators;
- mutation dependencies, validity start, invalidation frontier, and final-use frontier;
- owner, readers, writers, alias set, bytes, costs, fallback, and implementation hooks.

Start from `examples/lifetime/lifetime_corpus.yaml`. Capture JSON-line events in the corresponding
trace schema. Use stable identity fields such as record, scene-generation, frame, connection, or
device-generation IDs.

## Commands

```bash
vladder lifetime analyze \
  --manifest lifetime.yaml \
  --trace lifetime.json \
  --out-dir vladder-lifetime-analysis

vladder lifetime synthesize \
  --manifest lifetime.yaml \
  --trace lifetime.json \
  --out-dir vladder-lifetime-out
```

Inspect `lifetime-attribution.json`, `lifetime-candidates.json`, each candidate's
`verification.json`, `realization-contract.json`, and `AGENT_REALIZATION.md`.

Inspect `trace-quality.json` first. `insufficient_attribution` means the trace lacks construction
or transfer, consumption, and repeated-use or complete residency evidence. No candidates are
generated in that state. Mutation observations improve confidence but never authorize an invariant;
the manifest remains semantic authority.

## Initial Grammar

- `repeated-derivation-elimination`: construct once per valid containing scope.
- `serialization-body-reuse`: retain invariant body bytes while varying the envelope.
- `immutable-mutable-projection-split`: retain only the mutation-independent projection.
- `intermediate-realization-elimination`: forward directly or retire at final use.
- `placement-resident-state`: retain a versioned realization at the consuming boundary.

Search shortening and elimination as well as retention. Include construction, retained bytes,
invalidation, synchronization, transfer, memory-pressure, high-churn, and one-shot costs.

## Proof Boundary

- Structural proof: scope containment, ownership, observer freedom, fallback, placement.
- Z3: bounded derivation versions, non-invalidating transitions, complete invalidator coverage.
- Transition replay: publication before read, no stale read, no read after retirement.
- Protocol adapter: concurrent publication, reader retirement, GPU ownership/barriers, device loss.
- Alive2: local compiled helpers only. It does not prove lifecycle protocols.

A proof over the manifest is conditional on the manifest being complete. During implementation,
audit every production mutation path and preserve a sampled shadow baseline recomputation oracle.

## Repository Realization

The agent must implement only declared files and lifecycle hooks, preserve fallback, add ownership
types and invalidation paths, and retain the debug oracle through acceptance. Run stateful mutation,
rollover, cancellation, failure, concurrency, high-churn, one-shot, memory-pressure, regional, and
end-to-end tests. Pass any new hot helper back through the lower-level vLadder grammar and report
architectural and local gains separately.

Allowed claims are bounded to the named contract and grammar. An isolated corpus result is a
mechanism microbenchmark, not application performance.
