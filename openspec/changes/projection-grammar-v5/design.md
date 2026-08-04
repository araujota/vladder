# Design: Projection Grammar V5

Search proceeds through microkernel, projection, complex, and runtime-plan levels.
The initial implementation searches complex-level static choices while representing
child saturation explicitly. Pareto pruning retains weight traffic, preparation,
compute, temporary traffic, synchronization, code size, and scratch dimensions.

Rules requiring a token/sequence/layout precondition emit a dispatch guard. A larger
token tile is never assumed profitable without a matching workload regime.
