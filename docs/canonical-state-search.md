# Canonical Semantic-State Search

vLadder's exact composition search operates on a quotient DAG of semantic states. Transformations
are edges and action sequences are paths. A state is expanded once even when many paths reach it.

## Authority Order

1. Deterministic contract impossibility.
2. Collision-checked canonical identity and transposition.
3. Qualified dependency, commutativity, partial-order, symmetry, dominance, or macro reduction.
4. Optional heuristic or learned ordering.
5. Exhaustive fallback.

ML cannot delete a state. `fast` may stop because its user budget is exhausted;
`guided_reduced` changes priority; `exhaustive_reduced` eventually explores every state not removed
by an exact, qualified mechanism.

## State Identity

`Canonicalizer` emits deterministic canonical bytes, a SHA-256 index, semantic-observable and
contract digests, and component hashes. Digest equality is followed by byte and envelope equality.
The transposition table uses digest buckets, so a hash collision creates another record rather than
merging states.

Mapping/set order and graph node/edge serialization order are normalized. Arbitrary identities are
renamed only when `_nonobservable_ids` declares them or graph nodes belong to an explicit symmetry
class with `identity_observable: false`. Observable order, aliases, ownership, synchronization,
atomic/volatile behavior, memory spaces, types, precision, external state, and hardware constraints
remain part of identity.

Each state record retains all parent edges, first path, minimum/maximum depth, enabled actions,
proof/compiler/terminal status, and memoized alias, ownership, lifetime, contract, grammar, and
cross-TU summaries. `LayeredStateHash.update` must match clean rematerialization or fails closed.

## Partial-Order Reduction

Action-native grammars expose `enabled_actions` and `apply_action`; reductions can then occur before
candidate construction. Every action footprint conservatively states reads, writes, owners, aliases,
lifetime/authority state, representations, contracts, memory spaces, requirements, and conflicts.
An incomplete footprint is dependent.

The current bounded POR uses a canonical representative ordering only after a state-scoped check:

1. footprints are disjoint;
2. both `A -> B` and `B -> A` are legal;
3. both orders produce byte-identical canonical states.

This is a dynamic adjacent sleep-set realization, not a universal commutativity theorem. Evidence is
cached by state and action pair. Unknown pairs remain dependent. Production qualification compares
the full canonical terminal set with the reduced terminal set and requires exact equality.

## Experimental Exact Mechanisms

- Typed WL labels and bounded individualization/permutation study explicit symmetry classes.
- Dominance requires `descendants(A) <= descendants(B)`; structural cost alone has no authority.
- A macro requires exact descendant terminal-set equality and cannot hide unique intermediate actions.
- The local e-class store studies pure bounded expressions. It does not represent global ownership,
  protocol, asynchronous, or cross-TU state.

These mechanisms emit proposals and counterexamples until their qualification gates pass for the
applicable grammar envelope.

## Commands And Artifacts

Use the canonical modes through the regular source-search workflow:

```bash
vladder source-search run \
  --manifest executable-search.yaml \
  --out-dir source-search-out \
  --search-mode exhaustive_reduced
```

Every canonical run emits:

- `canonical-state-dag.json`: public `vladder-canonical-state-dag-v1` artifact;
- `executable-search.json`: proof/compiler dispositions and the embedded DAG;
- existing lazy and composition traces projected from canonical owners for compatibility.

Run the bounded qualification suite with:

```bash
python3 scripts/qualify_canonical_search.py \
  --rc26-root /tmp/vladder-composition-native-rc26-out \
  --adversarial-roots 30 \
  --output canonical-search-qualification.json
```

Qualification separates raw path count, unique states, transpositions, alpha/symmetry collapses,
dependency filtering, POR, proof/compiler work units, wall time, memory, and terminal preservation.

## Claim Boundary

RC26 replay validates real historical source, proof, and compiler evidence but cannot retroactively
qualify POR because those traces do not contain complete action footprints. The adversarial campaign
qualifies exact state/terminal behavior and pre-construction reductions, but its proof/compiler call
counts are bounded work units rather than production compiler timings. Adoption requires both forms
of evidence and does not establish global semantic-state optimality.

RC28 adds production defaults, adaptive cost gating, checkpoint/resume, concurrent identity,
resource control, real proof/compiler timing, and cross-system scaling. See
[Production Canonical-State Search](production-canonical-search.md).
