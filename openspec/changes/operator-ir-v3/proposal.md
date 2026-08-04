# Change: Operator IR V3

## Why

The V2 flow graph models one output store and mostly pointwise loops. Fusion,
state, reduction, layout, and multi-output legality require a representation
above scalar LLVM operations and a machine-readable semantic contract.

## What Changes

- Add validated YAML/JSON operator contracts with numerical, state, distribution,
  objective, and resource policies.
- Add a typed `OperatorGraph` with stream, state, reduction, materialization,
  layout, and effect nodes.
- Extract or construct multi-loop, multi-stream, multi-output regions and retain
  source/LLVM provenance.
- Compute state SCCs, fusion boundaries, lifetimes, alias sets, and traffic.

## Success

The initial token and HFT corpus serializes deterministic graphs, detects
invalid contracts, and distinguishes state, reduction, materialization, and
multiple outputs without losing scalar slice provenance.
