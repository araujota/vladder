# Design: Pipeline Verification V4

Verification is layered: structural refinement, child proof composition, memory
footprints/lifetimes, numerical error propagation, and stateful differential tests.
Cache placement and reuse are measured hypotheses; a cache miss cannot affect
correctness. Exact sampling preserves token selection and RNG consumption order.
