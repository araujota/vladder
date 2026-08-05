# NeuralFusion Bounded-Dataflow Acceptance

Date: 2026-08-05

This is a read-only acceptance audit of the four functions in the rc10 sample re-audit. It
validates whether `bounded-dataflow-v1` can represent the newly requested semantic classes. It is
not a full vLadder optimization workflow and makes no NeuralFusion speedup claim.

## Frozen Inputs

- NeuralFusion revision: `120351861aa7fb718a81b0c17864cdda58b24f22`
- Compilation database: `build/dev/compile_commands.json`
- Manifest: `examples/dataflow/neuralfusion-sample-audit.yaml`
- Grammar version: `bounded-dataflow-v1`
- Grammar hash: `04b3ed04d344e47507079b56b9fa3ed62d241a410152c5a8d634600f81c04168`
- Evidence: `/tmp/vladder-nf-dataflow-audit-final3-20260805/bounded-dataflow-audit.json`

## Result

| Production function | Recognized information-flow family | Current closure |
|---|---|---|
| `count_route_kind` | AoS projection and fused multi-reduction | Archetype represented; owning/external wrapper remains |
| `build_sparse_p2_delta_into` | Stable compaction, stateful delta, fixed-width codec | Archetypes represented; growth, errors, hashes, floating quality, and publication require decomposition/adapters |
| `hpc_comp_encode_surface_reference` | Quantized 4x4 packed block | Inner block represented; output-vector ownership and surface boundary remain |
| `evaluate_multi_client_openusd_perspectives` | AoS projected reduction; dependency invalidation deferred | Local reduction represented; revision/invalidation belongs to lifetime/protocol workflow |

All four selected source ranges were resolved through the production compilation database and
`selection_complete` was true. The audit found archetypes in `4/4` functions. It reported each
whole function as an external protocol boundary because none already satisfies the borrowed,
caller-owned, no-growth proof envelope.

Tracked-source identity was identical before and after:

```text
file count: 4283
before: d684b90c487f3c2ddcc79de0994bd5fc4ed80aff1232f90da949b1cbf57fcfd4
after:  d684b90c487f3c2ddcc79de0994bd5fc4ed80aff1232f90da949b1cbf57fcfd4
```

## What This Closes

- RC10's count-only semantic loss is closed for bounded stable index/value output.
- Capacity failure, exact extent, output stability, commit, and rollback are first-class graph
  semantics rather than comments on an adapter.
- The requested sparse P2, wire-codec, AoS, and fixed-block classes have executable grammar
  terminals and local proof envelopes.
- Ambiguous compilation commands fail closed. The audit does not scan an entire translation unit
  when a concrete selected function range is unavailable.

## What This Does Not Close

- The production owning functions were not regenerated, proved, benchmarked, or changed.
- `std::vector` allocation, nontrivial ownership, helper exceptions, cache lineage, floating-point
  RMSE policy, external acknowledgement, and concurrent publication remain adapter obligations.
- The generic 4x4 reference establishes the grammar shape; it is not proof of NeuralFusion's full
  NF-HPC-COMP endpoint/quality semantics until that exact inner block contract is supplied.
- Incremental OpenUSD dependency closure remains a lifetime/protocol problem, not a local LLVM
  rewrite.

The appropriate next NeuralFusion action, outside this no-write acceptance pass, is to expose or
generate bounded borrowed proof units at the recognized subregion boundaries, then connect them to
the existing project oracles and paired application benchmarks.
