# Change: Weight-Reuse Portfolio Measurement V9

## Why

Throughput batching can hide latency and workload regressions. V9 requires independent workload
results, physical provenance, a causal no-batching ablation, and portfolio-level gates.

## What Changes

- Benchmark interactive, prompt, concurrent, and KV-pressure workloads.
- Report logical useful-MAC/model-byte proxies separately from measured throughput.
- Preserve raw identity-control samples while forbidding speedup claims between identical plans.

## Success

The workflow either promotes a distinct verified 5% portfolio winner or reports a rigorous
negative transfer without converting batching value into a SiliconTune speedup claim.
