# Lazy Executable Search

vLadder expands executable grammars one semantic decision at a time. It does not build a full
Cartesian product before asking a search policy for permission to continue.

For composition-heavy exhaustive work, prefer `exhaustive_reduced`. It operates on the canonical
semantic-state DAG and applies state-scoped dependency/POR checks before an action-native grammar
constructs the child. `exhaustive_canonical` provides the exact transposition oracle; compare its
terminal hash set with `exhaustive_reduced` before promoting a reduction rule. See
[Canonical Semantic-State Search](canonical-state-search.md).

```text
semantic root
  -> lazy grammar action
  -> partial semantic state
  -> EXPAND / DEFER / PRUNE
  -> next partial state or concrete terminal
```

The policy runs on every partial or terminal semantic state before descendant expansion or
expensive terminal source/proof/compile materialization. Creating the small typed child state is
not candidate materialization. Three authorities remain separate:

1. Contract or legality proof may eliminate a deterministically impossible state.
2. Canonical semantic identity may memoize an equivalent state reached through another path.
3. A learned policy may decline to spend expansion budget on a merely unlikely state.

Only the third category is model-controlled. Unknown grammars, out-of-distribution roots,
low-confidence decisions, and a deterministic exploration reserve are kept.

For `family: auto`, grammar dispatch is itself the first lazy layer. vLadder independently
classifies each registered family against the captured semantic root, then exposes every applicable
or contract-incomplete family as a real depth-zero policy decision. Soundly inapplicable families
are eliminated before the oracle; expanding an applicable family enters its own partial-state tree.
Training traces no longer manufacture post-search family wrappers that the live policy cannot see.

Selected-build C++ roots also use this path. Clang capture discovers eligible regions and finite
schedule domains without creating schedule-specific source or proof artifacts. The policy sees
each unroll, vector-width, and interleave action before its regional source, Z3 schedule proof, or
candidate IR is materialized. Selected regional evidence is memoized and composed only after a
terminal survives; the translation-unit Cartesian product never exists ahead of lazy expansion.
Local capsule closure and schedule eligibility are separate. Ordinary Clang schedule requests can
therefore be explored in unchanged ownership-heavy or callback-containing functions without
claiming that their external protocols were isolated or proved.

Selected C++ roots also expose the finite `llvm-function-v1` sibling. It retains complete module
context, applies one selected-function pass pipeline per terminal, validates two modules with
Alive2, lowers with `llc`, and deduplicates selected-symbol assembly. A solver-unsupported terminal
is a completed workflow with unresolved evidence; it is not a failed run and not an authoritative
negative.

## Source Search

Use one manifest for independent roots:

```bash
vladder source-search run --manifest executable-search.yaml --out-dir source-search-out
```

```yaml
schema_version: vladder-executable-search-manifest-v1
mode: shadow_exhaustive
workers: 4
terminal_workers: 8
cache_directory: .vladder-cache/executable-search
roots:
  - id: byte-count
    source: count.cpp
    function: count_equal
    language: cpp
    family: auto
  - id: selected-build-slice
    family: cross-tu-composition
    language: cpp
    compile_commands: build/compile_commands.json
    cross_tu_seeds: [hot_entry]
  - id: retained-state
    family: lifetime-realization
    lifetime_manifest: lifetime.yaml
    lifetime_trace: lifetime.jsonl
  - id: publication
    family: bounded-protocol
    protocol_manifest: publication.yaml
```

Live model-guided search uses a persistent JSON-lines oracle. The command is argv-form and receives
one `register_root` message followed by `decide` messages for partial and terminal states. Every
decision includes the complete `ancestor_action_path`, including the current action, so online
composition decisions receive the same lineage features used by v3 supervision:

```yaml
mode: live
oracle:
  command: [python3, serve_pruning_oracle.py, --model, model.pt]
  timeout_seconds: 30
  prune_confidence: 0.999
  exploration_modulus: 100
  exploration_slots: 5
```

The protocol is `vladder-lazy-oracle-protocol-v1`. Oracle timeout, crash, malformed output,
out-of-distribution classification, low confidence, unknown action, and learned
`BLOCKED_BY_CONTRACT` all fail open to `EXPAND`. Only deterministic contract reasoning can close a
branch as semantically impossible. An explicit `DEFER` leaves the run incomplete and is a budget
decision, not negative-label authority.

`scripts/search_pruner.py` provides a 12.3M-parameter shadow trainer and protocol-compatible
reference oracle with separate grammar, candidate, and composition heads. It rejects incomplete
campaigns and emits an explicit live-eligibility gate; a completed training run alone never
authorizes pruning. Install the optional `vladder[ml]` dependencies before using it.
Repeat `--progress CAMPAIGN/training-v3/training-v3-progress.json --manifest MANIFEST` to train from
multiple complete campaigns. Each pair is validated separately and repeated branch identities are
deduplicated; conflicting labels fail closed.

Each root emits:

- `executable-search.json`: concise result and bounded claim;
- `executable-closure.json`: recognition through source-reconstruction stage coverage;
- `executable-search-trace.json`: authoritative v3 parent/child lineage and observations;
- `terminals/`: generated source, proof, compile, assembly identity, or realization plans.
- `training-v3/`: one schema-validated v3 bundle per root, emitted locally by default.

Manifest campaigns emit each bundle as soon as its root completes and refresh
`training-v3/training-v3-progress.json`. A later root failure or interrupted campaign therefore
does not discard already validated lineage. The progress status remains `in_progress` until
`record_count == expected_record_count`; per-record `pass` means only that emitted records validate.

The content-addressed cache includes semantic root, grammar, partial state, compiler, hardware, and
proof policy. Parallel root execution is deterministic; duplicate semantic states are memoized
independently of traversal order.

`workers` controls independent semantic roots; `root_workers` is accepted as a compatibility alias.
`terminal_workers` controls proof/compile realization
after one root's lazy tree has been enumerated. Terminal parallelism does not alter the tree or ask
the policy later; it only resolves independent leaves concurrently. Selected-build searches first
materialize shared regional proof evidence once, then compose and compile terminal translation units
in parallel. That prewarming is non-authoritative: a region capsule that cannot compile in
isolation is recorded in `selected-build-prewarm.json`, and each affected terminal receives its own
compile/proof disposition. A prewarm miss cannot abort sibling terminals or the enclosing campaign.
Deterministic regional materialization failures are content-addressed and reused across terminals;
the tree still retains every affected branch and outcome, but the invalid compiler invocation is
not repeated for every Cartesian composition.

For exhaustive C++ corpus collection, `scripts/build_cpp_search_manifest.py` defaults to at most
three selected-build regions per semantic root. Every selected region is still exhaustively
composed. Additional eligible regions are recorded as omitted from the declared grammar domain;
they are not silently pruned and cannot support an exhaustive whole-function claim. Increase
`--max-selected-build-regions` only when the resulting Cartesian terminal count is physically
affordable.

When a completed corpus is positive-path sparse, `scripts/build_cpp_search_topup_manifest.py`
constructs a separate bounded campaign from roots that already contain model-eligible useful
descendants and explicit omitted regions. Each top-up root declares a different concrete region
subset, receives a distinct semantic/request identity, and remains exhaustive only inside that new
domain. This adds composition supervision without relabeling old branches or relaxing the evidence
gate.

Large campaigns may set `artifact_retention: decisive`. After a root's standalone v3 packets are
successfully emitted, vLadder removes reproducible terminal object/IR directories, gzip-compresses
the complete search and trace, and preserves a compact summary, `executable-closure.json`, and every
v3 packet. Compressed roots remain resumable. Use `full_artifact_identifiers` to retain unpacked
forensic artifacts for representative roots. Release and promotion workflows continue to default
to `full`.

Completed roots are resumed only when a content fingerprint covering source, compilation
database, contract, grammar request, workload, hardware, node budget, and oracle configuration
matches. Selected-build terminal compile/proof results have a second atomic cache, so an
interrupted Cartesian shadow run can resume individual terminal realizations instead of restarting
the root. Per-root v3 progress records carry the same request fingerprint; a resumed campaign
preloads only matching records, so reporting progress never forgets already emitted supervision or
accepts stale bundles from a changed root.

## Closure Classes

Current executable source terminals include deep byte-predicate realizations, ordered prefix and
suffix reductions, exact bit-popcount reductions, and bounded
compaction/codec/delta/AoS-reduction/quantized-block families.
These compile, prove, and receive normalized physical code identities.

Canonical pointwise maps, guarded maps, stencils, scans, recurrences, and indirect-memory loops use
one derivation grammar with native C, C++, Rust, Zig, and Julia emitters. Native compiler IR must
corroborate the captured loop and memory shape before this local executable closure is claimed.

Lifetime plans, definition-visible cross-TU compositions, and bounded state/device protocol
projections are also lazily enumerated and proved. They intentionally stop before compiled owning
source reconstruction. Their external authority, fallback, ownership, and physical-runner
requirements remain explicit and their useful-descendant labels remain uncertain until concrete
implementations close those stages.

## Training Authority

Shadow exhaustive mode records exact `node_id`, `parent_id`, action, depth, canonicalization,
terminal disposition, and observations. Utility propagates from a proof-valid distinct physical
realization or stronger retained outcome to all required ancestors.

Absence of a useful terminal is a pruning negative only when the subtree is exhaustive or a named
sound legality/contract proof closes it. A proof-only plan, unresolved assembly identity, external
protocol boundary, interrupted search, or budget-truncated tree remains `KEEP_UNCERTAIN`.

v3 records mark each branch's `decision_surface` as `learned_eligible`, `deterministic`,
`canonicalized`, or `synthetic_wrapper`. Deterministic impossibility and canonical duplicates stay
in the audit lineage but are excluded from model training and pruning metrics because the live
oracle is never queried for them.

The learned model therefore answers "could a useful descendant exist?" It does not predict
performance, prove equivalence, establish legality, or authorize promotion.

### Exhaustive supervision policy

Use complete Cartesian enumeration wherever the bounded closure is tractable. It is the strongest
source of composition negatives and ancestor utility because every terminal and required path is
observed. Do not require every large root to be exhaustive before collecting useful supervision:

- fully enumerate one- and two-region roots and a stratified set of deeper roots;
- use deeper exhaustive roots to cover interactions that shallow roots cannot express;
- retain budget-truncated broad roots for applicability and OOD coverage;
- label every open frontier and every ancestor whose descendants remain open as
  `KEEP_UNCERTAIN`;
- never infer a prune target from a merely unvisited Cartesian combination.

This distinction lets exhaustive shadow runs provide authoritative labels without making corpus
collection depend on materializing every combinatorial production root. Live search remains lazy
even when the corresponding training root was enumerated exhaustively.

This architecture corrects a limitation in both ordinary optimization and training collection.
Previously, some routes emitted only immediate candidates, so deeper compositions were absent from
normal search and their ancestor utility could not be supervised. The lazy engine now records and
intercepts every supported expansion. It does not turn an unrecognized source region into an
executable grammar: recognition-incomplete roots remain `KEEP_UNCERTAIN`, and their absence of
candidates is reported as semantic coverage debt rather than negative search evidence.
