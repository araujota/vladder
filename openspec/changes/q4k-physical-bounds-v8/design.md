# Design: Q4_K Physical Bounds and Byte Accounting V8

Representation bytes are derived from the native `block_q4_Kx8` and `block_q8_K` shapes.
The memory floor uses the measured warm weight-traversal diagnostic, which is primarily an
LLC-access-pattern bound on this target, not vendor DRAM peak bandwidth. The arithmetic
floor uses an optimistic relevant-vector-operation throughput, and the dependency floor
uses the exact ten-block E1 accumulator recurrence. Since no floor exceeds one third of
observed runtime, the result is classified as memory-sensitive mixed execution.
