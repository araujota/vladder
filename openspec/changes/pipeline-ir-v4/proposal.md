# Change: Pipeline IR V4

## Why

OperatorGraph cannot express ownership, liveness, layouts, and materialization across
multiple operator boundaries. V4 requires a deterministic graph-of-graphs IR.

## What Changes

- Add validated pipeline manifests and immutable hashes.
- Add PipelineGraph nodes that reference OperatorGraph leaves.
- Add typed tensor/state/control edges with memory-hierarchy metadata.
- Compute boundaries, live sets, critical paths, and hierarchical provenance.

## Success

A transformer-block fixture round-trips deterministically and rejects unresolved
shape, observer, alias, ownership, or numerical contracts.
