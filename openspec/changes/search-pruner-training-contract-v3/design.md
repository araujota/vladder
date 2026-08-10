# Design: Search-pruner training contract v3

## Training question

The model estimates whether a useful descendant can exist below a branch. It does not predict
speedup. A useful descendant is a distinct proof-valid realization or stronger evidence: a material
physical result, retained application candidate, or promoted candidate.

## Records

Each bundle contains:

- normalized semantic roots;
- search executions binding a root, grammar, hardware, workload, selection policy, and global
  coverage status;
- branches with stable parent lineage, depth, search stage, action, expansion state, local child
  coverage, direct evidence utility, descendant utility, survival disposition, and search cost;
- typed observations linked to branches.

The branch-oriented learning export partitions fields into `decision_context` and `supervision`.
Only semantic topology, accumulated actions, stage, grammar, hardware, and workload are legal model
inputs. Search completion, observations, costs, and derived targets are supervision; mixing them
into the encoder would leak outcomes unavailable at a live pruning decision.

The baseline is the root branch of each search and is never prunable.

## Label derivation

Labels are recomputed bottom-up.

1. Direct utility is derived from observations, not accepted as an arbitrary producer label.
2. Positive utility propagates to every emitted ancestor.
3. A branch with observed utility is `KEEP` even if the surrounding trace is incomplete.
4. A branch with no positive descendant is negative only when every child is represented and the
   subtree is exhaustive, or when a named sound contract/legality/dominance proof closes it.
5. A sound contract closure is `BLOCKED_BY_CONTRACT`; another complete dead subtree is
   `PRUNE_HIGH_CONFIDENCE`.
6. Every remaining branch is `KEEP_UNCERTAIN`.

Descendant targets remain separate for proof-valid, distinct-realization, material, retained, and
promoted outcomes so future models can choose a stricter preservation objective without rebuilding
the raw corpus.

## Sharding

A bundle is a bounded trace fragment. Parent references are local when present; a fragment may name
an external parent and carry labels computed by the complete authoritative trace. Locally asserted
negative labels still require local complete-subtree or sound-closure evidence. This prevents
sharding from manufacturing negatives.

## Historical conversion

Flat v2/prior evidence becomes a one-level partial search. This preserves useful positive examples
and applicability evidence but does not upgrade absent observations into negative labels.

## Service migration

`POST /api/training/v3` stores v3 records in a new table. The existing v2 table remains intact so a
schema deployment does not invalidate moderated historical records. `/api/training/v2` returns
`410 Gone` for new writes.
