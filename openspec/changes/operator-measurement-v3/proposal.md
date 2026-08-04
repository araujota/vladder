# Change: Operator Measurement V3

## Why

V2 reports aggregate nanoseconds per item. Token operators need latency,
throughput, and traffic; HFT acceptance depends on p99.9/p99.99 and configuration
identity. Mean-oriented timing cannot support those claims.

## What Changes

- Add immutable hardware and software manifests and measurement refusal rules.
- Add per-invocation cycle samples, randomized candidate order, independent
  processes, warm/cold modes, perf counters, and bootstrap intervals.
- Add objective-specific rankers with effect thresholds and statistical ties.
- Add deterministic training/held-out trace identities.

## Success

Measurements from incompatible manifests cannot combine. HFT ranking rejects
tail regressions; token ranking reports operator latency, traffic, and optional
integrated token-time contribution separately.
