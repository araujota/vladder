# Production Canonical-State Search

Production vLadder search operates on unique semantic states, not transformation sequences.
`fast`, `guided`, and `exhaustive` manifest/CLI modes route through
`ProductionCanonicalSearchEngine`; `legacy_path_debug` retains the old path traversal solely for
qualification and trace compatibility.

## Authority

The production authority order is semantic legality, collision-checked canonical bytes, exact
transposition, deterministic dependencies, state-scoped byte-verified commutativity and cost-gated
POR, explicit alpha/symmetry classes, then proof, compilation, physical evaluation, and promotion.

Unknown footprints, dependencies, incremental state, or verifier outcomes fail open. Learned
models may change priority only. Dominance, macros, coarse optimization equivalence, and global
ownership/protocol e-graphs have no production deletion authority without separate qualification.

## Modes

- `fast`: canonical transposition, cheap exact reductions, explicit work/time budget.
- `guided`: canonical DAG, qualified adaptive POR, large finite budget, optional ordering.
- `exhaustive`: every reachable unique canonical state after qualified exact reductions.
- `exhaustive_canonical`: qualification oracle without POR.
- `exhaustive_reduced`: force the qualified exact-reduction envelope.
- `legacy_path_debug`: raw path-oriented qualification only.

CLI and manifest requests default to `exhaustive`. The low-level Python
`ExecutableSearchRequest` retains `legacy` as a compatibility default for callers consuming the
historical training trace; production callers should set an explicit mode.

## Cost Gate

POR estimates avoided descendant construction/proof/compiler cost against footprint analysis and
AB/BA canonicalization cost. Incomplete footprints remain dependent. Cheap shallow regions use
canonicalization only; proof/compiler-heavy regions admit POR when measured moving costs make the
expected net value positive. Choosing too little reduction changes cost, not completeness.

## Persistence And Resources

Production checkpoints bind canonical schema, engine, source semantic hash, grammar identity, and
target identity. Resume rejects any mismatch and cleanly rematerializes every stored state before
registration. Memory pressure evicts recomputable analysis summaries first. If identity records
still exceed the ceiling, search stops incomplete with its canonical frontier intact for checkpoint
and resume; it never silently forgets identity and re-explores duplicate states.

`TranspositionTable` provides lock-protected collision buckets. Concurrent byte-identical
registrations produce one recursive owner and retain every provenance edge.

## Artifacts

Each production run emits:

- `canonical-state-dag.json`: canonical nodes, all edges, terminals, exact reductions;
- `production-canonical-search.json`: policy, cost, cache, footprint, memory, checkpoint, and
  production-default evidence;
- existing executable and composition traces as compatibility projections.

Every installed wheel also carries `artifacts/production-canonical-search-rc29.json`, a compact
schema-validated record of the release's exact authority, defaults, terminal preservation, smoke
coverage, and measured proof/compiler savings. Inspect the installed artifact with:

```bash
vladder release canonical-search-evidence
```

Manifests may configure:

```yaml
search_mode: exhaustive
por_policy: adaptive
search_memory_ceiling_bytes: 1073741824
search_checkpoint: build/vladder-search.checkpoint.json
```

Use `search_resume` with the same path in a subsequent compatible run.

## Pre-Release Smoke

Run the release-blocking battery before the larger release-readiness workflow:

```bash
vladder release smoke-canonical-search \
  --out build/production-canonical-search-smoke.json
```

The eight stages cover collision-safe canonical identity and transposition provenance, POR
commutativity and fail-open alias/incomplete footprints, incremental clean fallback, actual Z3 and
optimized C++ terminal work, cheap-region cost gating, concurrent registration, checkpoint identity,
and width 2/3/4 scaling. Any stage failure returns nonzero. This approximately two-second sentinel
does not replace RC26/RC27 replay or the full three-system qualification.

## Training Contract

The enumerator-native `composition-native-search-trace.json` is the authoritative future
search-policy artifact. At emission time, vLadder verifies canonical state ownership, parent
lineage, complete sibling sets, child-state realization, selected-action membership, one label per
frontier, complete action labeling and oracle ordering, canonical terminal ownership, summary
counts, and the trace hash. The embedded training contract marks incomplete searches and missing
cost evidence explicitly.

Use the library `inference_view` rather than a completed trace when building model inputs. It
contains the parent state, ordered history, siblings, interaction graph, and pre-expansion deltas;
it excludes future state enumeration, transpositions, selected actions, terminal outcomes, labels,
and measured costs. This preserves the production authority rule: learned components may order
work or propose an exact check, while only exact or formally qualified mechanisms remove work.

## Qualification

Run the full local production suite with:

```bash
python3 scripts/qualify_production_canonical_search.py \
  --rc26-root /tmp/vladder-composition-native-rc26-out \
  --rc26-manifest /tmp/vladder-composition-native-rc26-manifest.json \
  --rc27-report /tmp/vladder-canonical-search-qualification-rc27.json \
  --sources /root/Documents/Codex/2026-08-10/vladder-graphml-training-campaign/sources \
  --output build/production-canonical-search-qualification.json
```

Release qualification requires exact terminal equality, real source recapture on three systems,
actual Z3/compiler net savings, deterministic concurrent identity, bounded memory behavior, and
raw-versus-canonical scaling curves. See the
[RC28 production report](reports/production-canonical-search-rc28.md).
