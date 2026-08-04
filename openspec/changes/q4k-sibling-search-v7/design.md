# Design: Controlled Production Sibling Search V7

The initial grammar avoids arbitrary decode DAGs. E1 fixes row grouping and accumulator
order. The true fused member loads each Q8_K sub-block once, then applies unchanged native
Q4_K decode/dot operations to gate and up accumulator banks. A persistent interleaved
layout has a byte-exact inverse and includes output adaptation in timing.

Instrumentation is excluded from ranking. Byte accounting, disassembly, and PMU probes
explain results but do not override wall time and confidence intervals.
