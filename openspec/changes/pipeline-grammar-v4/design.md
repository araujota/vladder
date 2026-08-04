# Design: Hierarchical Grammar And Search V4

Pipeline search first enumerates legal partitions, materialization policies, layouts,
and traversals. A selected region may request bounded child OperatorGraph extraction.
Plans retain a cost vector. Pareto dominance is applied before a hardware-weighted
scalar orders the beam. Every plan records parent/child budgets and saturation.
