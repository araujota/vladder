# Change: Operator Grammar And Search V3

## Why

The V2 grammar changes scalar realization and loop shape. V3 must choose fusion,
layout, reduction topology, control representation, schedule, and guarded
specialization without enumerating their complete cross-product.

## What Changes

- Add declarative operator rules with legality and proof obligations.
- Saturate local regions, then compose alternatives with beam search and
  dominance pruning.
- Add hardware-aware static costs for traffic, critical path, registers,
  branches, working set, code, and materializations.
- Lift multi-stage and multi-output candidates to C17/restricted C++20.

## Success

At least three fusion rules, two layout transforms, three reduction structures,
and guarded specialization produce audited candidates; graph-level choices are
distinguishable from compiler-flag variants.
