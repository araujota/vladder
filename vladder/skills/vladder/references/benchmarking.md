# Benchmarking And Attribution

## Attribution First

Profile the real application and representative workload. Record regional runtime share, calls,
cycles, instructions, branch misses, L1/L2/LLC and TLB misses, backend stalls, bytes, allocation,
synchronization, and dependency evidence where supported. Use source ablations and assembly/IR
inspection to disambiguate overlapping stages; do not treat ablation times as additive.

Estimate the maximum end-to-end value before search:

`regional runtime share x plausible regional reduction`

## Measurement Controls

- Pin compiler, flags, source/model/input hashes, CPU set, NUMA node, SMT policy, and thread count.
- Stabilize or record governor, frequency, boost, microcode, and temperature.
- Randomize candidate order and use independent processes.
- Benchmark the native baseline in the same executable and ordering schedule.
- Separate warm, cache-resident, LLC, streaming, and cold modes when memory behavior matters.
- Use held-out traces and inputs for confirmation.
- Collect PMU counters separately from final ranking when instrumentation perturbs execution.
- Use bootstrap confidence intervals and a predeclared minimum effect threshold.

## Promotion

Do not promote a local win unless its confidence interval excludes the minimum effect and the full
application improves within declared regression limits. Report every important workload
separately; an aggregate must not hide latency, memory, or correctness regressions.
