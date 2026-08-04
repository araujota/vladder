# Design: Pipeline IR V4

PipelineGraph is an immutable typed directed multigraph. Nodes identify semantic
operators and content-addressed OperatorGraph children. Edges distinguish logical
tensors from physical realizations. Materialization, layout, lifetime, cache target,
and traversal are explicit fields. Graph normalization computes topological stages,
live-byte frontiers, fusion regions, and operator attribution weights.

Unknown contracts are barriers. PipelineGraph never invents alias freedom, numerical
reassociation authority, or cache residency guarantees.
