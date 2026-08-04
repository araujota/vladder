# Change: SKSF Kernel IR and Synthesis V6

## Why

ProjectionComplexGraph exposes projection topology but treats native Q4_K load, decode,
dot, and accumulation as one opaque physical region.

## What Changes

- Add KernelGraph beneath ProjectionComplexGraph.
- Add attribution-gated decode, traversal, accumulator, shared-projection, materialization,
  token-reuse, and dispatch grammars.
- Add hierarchical Pareto/beam search and a complete candidate audit.

## Success

The system deterministically lowers production projection manifests, rejects illegal or
unjustified rules, and classifies bounded coverage without global-optimality claims.
