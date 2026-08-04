# Design: Q4_K Physical Decomposition Workflow V8

The workflow accepts only passing V7 capture, reconstruction, and parity artifacts. It
re-hashes model and kernel sources, captures the hardware manifest, reruns parity, checks
assembly shape, builds the physical graph and diagnostics, collects randomized evidence,
then emits attribution, memory, bounds, ceilings, and admission reports. Boost remains
enabled on this host, so per-process frequency and temperature are recorded and regression
is nuisance analysis only. Any promoted candidate still requires separate-day reproduction.
