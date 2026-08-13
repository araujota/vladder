# Design

## Authority Separation

The runtime cascade is deterministic legality, canonical transposition, verified equivalence,
learned ordering, then proof/compile/benchmark. ML may reorder or propose exact checks but may not
remove a state.

## Decision Unit

A `SearchDecision` binds one parent semantic state and action history to the complete set of legal
sibling actions visible before expansion. Each option contains only pre-decision action, graph-delta,
contract, owner, width, arity, and deterministic cost features. Distance, descendant utility,
retention, exhaustive subtree cost, and redundancy disposition are supervision only.

RC24 reconstruction groups complete children by search and parent. It derives an oracle ordering
from retained, useful, distance, and cost labels. Because RC24 omitted canonical state hashes and
retained outcomes, the migration marks those fields unavailable rather than fabricating them.

## Runtime

`LazySearchEngine` accepts a contextual frontier scorer and uses a stable priority queue. `fast` and
`guided` stop at declared budgets. `exhaustive` uses the same ordering but remains complete. Exact
semantic-state hashes are memoized before learned scoring. Potential equivalence pairs can be
proposed to an exact verifier; only verifier acceptance creates an alias.

## Model

The shared canonical graph/action vocabulary feeds a parent graph encoder, an explicit ordered
history encoder, and sibling action encoders. Frontier self-attention produces relative scores.
Architectural ablations cover GIN, GIN/GAT, and local-plus-global GPS-style graph encoding without
increasing model size aggressively. Listwise ordering is primary; distance, utility class, subtree
cost, and equivalence class are auxiliary targets.

## Evaluation

Held-project online replay exposes children only after their parent is expanded. Recovery curves
report useful terminals discovered at 1, 5, 10, 20, 30, 50, and 100 percent of exhaustive direct
work. Results also include first-useful cost, proof/compiler/candidate counts, frontier size, and
transposition reduction. Checkpoint selection maximizes 30%-budget useful recovery, with retained
recovery preferred when evidence exists.
