# Change: WeightTraversalGraph IR V9

## Why

V8 admitted work reuse rather than further Q4_K kernel-local rewrites. SiliconTune needs an
optimization unit whose lifetime begins at a weight-block load and spans all ready consumers.

## What Changes

- Add a provenance-bearing `WeightTraversalGraph` above the fixed production kernel.
- Represent token, sequence, projection, barrier, dispatch, commit, and rollback structure.
- Carry E1, ownership, lane, byte, and reuse metadata on graph edges.

## Success

The pinned Qwen Q4_K execution organization is represented completely and deterministically.
