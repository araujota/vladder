# Design: SKSF Kernel IR and Synthesis V6

KernelGraph records the physical flow of activation, quantized blocks, metadata, decoded
values, dot products, accumulator banks, reductions, output transforms, consumers,
materializations, and dispatch. Logical bytes and contracts are immutable; modeled and
measured costs are separate artifacts.

Search applies at most one rule per family in the current bounded region, performs
legality checks before costing, retains a Pareto frontier, and uses a bounded beam for
composition. Static factors are hypotheses used only for pruning.
