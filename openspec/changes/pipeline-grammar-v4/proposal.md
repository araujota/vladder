# Change: Hierarchical Grammar And Search V4

## Why

The operator grammar cannot choose boundaries, tile traversal, scratch sharing, or
cross-operator layout. A flat cross-product is intractable.

## What Changes

- Add fusion, materialization, traversal, layout, state, reduction, and scratch rules.
- Add parent pipeline search with bounded child OperatorGraph search.
- Add vector costs, dominance pruning, lower bounds, and complete budget attribution.

## Success

Search deterministically finds legal streaming and fused alternatives, records every
rejection/prune, and labels unsaturated regions without global-optimality language.
