## Context

The existing vLadder hierarchy selects expression, loop, operator, projection, and runtime-plan
graphs. Lifetime is currently represented only as a legality fact on selected edges. The new layer
must express two dual questions for each semantic information identity: the narrowest interval in
which a realization is needed and the broadest interval over which one realization remains valid.

## Decisions

### 1. Contracts and traces are separate authorities

The manifest declares authority, invalidators, ownership, consistency, candidate scopes, and
fallback. Traces provide costs and observed reuse but cannot create semantic invariants. Discovery
may rank only candidates admitted by the manifest.

### 2. Scope containment is a partial order

Scopes are named nodes connected by explicit containment edges. Candidate legality uses reachability
rather than a global enum because frames, transactions, connections, and device epochs can overlap.
Each concrete trace also carries scope-instance identities to prevent reuse across peer lifetimes.

### 3. The first grammar is deliberately bounded

The executable lifetime planner supports repeated derivation retention, serialized-body reuse,
immutable/mutable splitting, intermediate elimination or final-use retirement, and placement
residency. Eager/lazy and invalidation policy are parameters within those families, not unbounded
program synthesis.

### 4. Protocol proof is distinct from LLVM refinement

Z3 discharges bounded version, invalidation, and read-safety obligations. Structural checks cover
scope, ownership, and fallback. Stateful differential traces cover emitted observations. Alive2
obligations are emitted only for local compiled helpers and are never reported as lifecycle proof.

### 5. Repository realization is an honest adapter boundary

The workflow emits a machine-readable realization plan and a concise agent implementation brief
containing permitted files, lifecycle hooks, invalidation matrix, fallback, debug oracle, tests,
and proof obligations. It does not claim generic source regeneration for object ownership, GPU
resources, transport state, or concurrent publication.

### 6. Evaluation is isolated and classification-bounded

An included corpus models record serialization, immutable indexing, intermediate elimination,
shared immutable views, over-retention, and stale-cache negatives. Microbenchmarks establish the
direction and local mechanism only; they are not NeuralFusion or end-to-end application results.

## Failure Boundaries

- Missing invalidators, ambiguous authority, incomparable scopes, unsupported concurrency, or no
  fallback reject promotion.
- Observed non-mutation never widens a semantic lifetime.
- A cost-model win without protocol proof is `unverified_candidate`.
- An isolated benchmark result is `lifetime_*_microbenchmark_win`, not an application claim.
