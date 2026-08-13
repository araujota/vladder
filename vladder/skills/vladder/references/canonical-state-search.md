# Canonical-State Search

For composition-heavy exact search use:

```bash
vladder source-search run --manifest MANIFEST --out-dir OUT \
  --search-mode exhaustive_reduced
```

The state, not the action path, is authoritative. Inspect `canonical-state-dag.json` before the
legacy path trace. A digest match is only a table lookup: canonical bytes, observable summary, and
contracts must also match. Every unique record retains all incoming edges.

Use `exhaustive_canonical` as the oracle when introducing a reduction. `exhaustive_reduced` must
produce the identical terminal canonical-hash set. Never qualify a POR, symmetry, dominance, or
macro rule from performance or branch counts alone.

Action-native grammars must provide complete read/write, owner, alias, lifetime, representation,
contract, authority, and memory-space footprints plus an exact `apply_action`. Missing metadata
means dependent. Commutativity is state-scoped unless formally generalized and requires both orders
to remain legal and canonical-byte identical.

Alpha/symmetry identity erasure is opt-in. Do not erase observable lane IDs, aliases, memory spaces,
atomics, ordering, ownership, protocol state, type/precision, or hardware legality. Hash collision,
incremental-rematerialization mismatch, or missing terminal parity fails closed.

Dominance requires descendant terminal-set inclusion. Macros require equality and may not hide an
intermediate state with a unique legal action. Local e-classes apply only to bounded pure expression
families. ML can order surviving DAG edges; it cannot merge or delete them.

The RC27 bounded qualification replayed all RC26 exact evidence and accepted the canonical reduced
architecture. That is a search-reduction result, not a candidate runtime speedup or global
optimality proof.

RC28 is the production layer. CLI/manifest `fast`, `guided`, and `exhaustive` now operate on the
canonical DAG. Read `production-canonical-search.json` for the adaptive decision, footprint
coverage, cache, memory, and checkpoint evidence. POR is cost-gated; cheap regions may correctly
use canonicalization only. Use `legacy_path_debug` solely when qualification requires the old path
trace. A resource stop is incomplete, not a proof that the remaining frontier is dead.
