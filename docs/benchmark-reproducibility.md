# Benchmark Reproducibility Guide

## Freeze Inputs

Record source revision, dirty-tree state, compiler and flags, grammar/schema versions, contract,
workload/trace hash, hardware manifest, core/NUMA placement, SMT policy, governor/frequency policy,
temperature policy, and every candidate identity.

## Measure Paired Executables

Reference and candidate must run in the same harness and executable where possible. Randomize
candidate order across independent processes. Separate warm/cold and cache-resident/streaming
regimes. Preserve raw samples; do not rank profiler-instrumented timings.

```bash
vladder benchmark paired --manifest paired-benchmark.yaml --out-dir paired-out
```

Use at least ten independent processes for promotion and increase samples when expected effects
are below 3%. Report bootstrap confidence intervals and a predeclared minimum effect. A confidence
interval crossing that threshold is a tie, not a win.

## Prevent Double Counting

Do not multiply or add speedups from overlapping parent/child regions. Use an interaction run or
measure the composed executable:

```bash
vladder benchmark compose --manifest regional-effects.yaml --out composition.json
```

## Reproduce Elsewhere

Export hashes, manifests, compiler/tool versions, raw samples, summary, and applied-source identity.
Rerun on a clean Linux host and, for small effects, on a separate day. Report regional and
end-to-end effects independently, including regressions and rejected candidates.
