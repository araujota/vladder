# Change: Production Q4KKernelGraph V7

## Why

The synthetic V6 graph omits production Q4_K metadata, Q8_K activation blocks, native
repacking, minimum corrections, and float accumulation order.

## What Changes

- Add production Q4_K and Q8_K block semantics.
- Add exact native Q4_Kx8 repack and inverse.
- Add typed, provenance-linked Q4KKernelGraph nodes and edges.
- Define separate E1 and E2 numerical contracts.

## Success

Finite metadata/repack checks and randomized/adversarial block tests pass, and every graph
operation is traceable to pinned baseline behavior or a declared grammar rule.
