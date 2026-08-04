# Design: Projection Measurement V5

The first profiler separates activation conversion, synchronization, and the existing
fused weight-load/metadata-decode/dot/accumulate region. It does not fabricate finer
attribution than the instrumentation can observe. Hardware counters and dedicated
microbenchmarks refine the fused region later. Profiling data prioritizes candidates;
it is never used as tokens-per-second ranking evidence.

Portfolio ranking reports every workload, weighted score, confidence interval, and
floor violation. A score cannot hide an interactive or prompt regression.
