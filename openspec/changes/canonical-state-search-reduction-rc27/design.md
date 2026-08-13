# Design

## Authority And Search Object

`CanonicalStateRecord` is the authoritative node. It owns canonical bytes, layered hashes, semantic
observables, contracts, all incoming edges, minimum and maximum discovery depth, enabled actions,
status, and cached semantic summaries. `CanonicalSearchEdge` retains path provenance. A collision-safe
transposition table buckets by digest and confirms byte and semantic-envelope equality before reuse.

The existing lazy trace remains a path audit. The new quotient DAG is emitted alongside it so current
composition-native data producers remain compatible.

## Canonicalization

Canonicalization sorts mappings, sets, graph nodes, and graph edges; removes declared volatile
provenance; alpha-renames only explicitly non-observable identities; and uses typed/color-preserving
WL refinement followed by bounded individualization for declared symmetric classes. Alias, ownership,
synchronization, atomic/volatile, memory-space, type/precision, external observability, and hardware
legality attributes are never discarded.

Incremental state deltas use layered component hashes, but clean canonical serialization remains the
oracle. Tests compare incremental and clean rematerialization.

## Exact Reduction

Grammar actions expose conservative read/write, owner, alias, lifetime, representation, contract,
authority, and memory-space footprints. Unknown relationships are dependent. Static disjointness is
only a screen; state-scoped commutativity additionally requires both orders to be legal and to yield
identical canonical states. Sleep sets skip only an alternative ordering already represented by a
verified-independent transition. Dynamic POR records verified diamonds as they are discovered.

Grammar requires/enables/conflicts edges deterministically suppress impossible schedules. Symmetry
normalization is allowed only for explicitly interchangeable classes. Dominance and macro replacement
require descendant terminal-set inclusion/equality on bounded qualification roots before deletion.

## Bounded Local E-Graph

A compact union-find e-graph represents local pure expression families with explicit equality rules.
It is a feasibility study and reports nodes, classes, memory, saturation, extraction, and preserved
normal forms. It is not applied to global ownership or protocol transitions.

## Qualification

Every mechanism is evaluated independently against canonical exhaustive search. The production gate
is exact equality of terminal canonical bytes, not a statistical recall metric. RC26 traces are replayed
to validate transposition and U2 ownership. Adversarial executable grammars cover commuting actions,
dependencies, symmetry, alpha identities, macro boundaries, and counterexamples to unsound dominance.
