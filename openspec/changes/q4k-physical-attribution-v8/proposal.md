# Change: Q4_K Controlled Physical Attribution V8

## Why

One fused runtime bucket cannot distinguish required representation work from reducible
implementation cost, and instrumenting the native loop directly changes its schedule.

## What Changes

- Add seven diagnostic-only controlled variants.
- Measure randomized independent processes in warm, cache-size, and streaming regimes.
- Report inclusive, elimination-envelope, and critical-path attribution separately.

## Success

Major stage ordering reproduces across two rounds and no stage above the admission
threshold is represented as an additive pie slice.
