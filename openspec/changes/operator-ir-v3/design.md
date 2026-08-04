# Design: Operator IR V3

Contracts are parsed into immutable dataclasses and canonical JSON before any
search. `OperatorGraph` is a directed typed multigraph. Nodes model semantic
operators; edges carry shape, layout, memory, ordering, numerical, and profile
metadata. Scalar V2 graphs attach beneath `Map`, `Reduce`, `Scan`, and
`DecodeField` nodes as provenance, not as the operator-level search surface.

Graph normalization computes SCCs, regions, materialization liveness, and
fusion compatibility. Unknown aliasing, ownership, or numerical policy blocks a
transform rather than becoming an optimistic assumption.
