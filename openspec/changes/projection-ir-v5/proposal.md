# Change: Projection IR V5

## Why

PipelineGraph attributes projection cost but cannot express quantized block decode,
activation preparation, accumulator banks, or reuse across sibling projections.

## What Changes

- Add immutable ProjectionComplexGraph manifests beneath PipelineGraph.
- Add typed projection nodes and edges with quantization, tile, reuse, and cost data.
- Add FFN gate/up and attention Q/K/V shared-input fixtures.

## Success

Valid complexes hash deterministically and unresolved shape, quantization, alias,
consumer compatibility, or numerical contracts are rejected.
