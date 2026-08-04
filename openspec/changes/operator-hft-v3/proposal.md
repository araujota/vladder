# Change: Low-Latency Operators V3

## Why

HFT-oriented validation requires deterministic state transitions and tail
latency, not generic throughput. The scope is an in-memory computational replay,
not strategy or live network synthesis.

## What Changes

- Add fixed binary decode, price-level book, transactional risk, rolling feature,
  encode, and SPSC ring contracts.
- Add deterministic tuning, held-out, and adversarial traces.
- Add batch-1 latency and separate microburst throughput modes.
- Add integrated decode-to-enqueue replay and state/invariant checking.

## Success

At least five HFT operator families and the integrated in-memory path run with
correct state, raw cycle distributions, counters, reproducibility, and no
allocation. Tail constraints determine acceptance.
