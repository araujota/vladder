# Change: Q4_K Baseline Reconstruction and Parity V7

## Why

A generated search space is not credible if its reproduced baseline is materially weaker
than the active handwritten kernel.

## What Changes

- Extract and independently compile the active AVX implementation.
- Enforce E1 differential verification before timing.
- Compare p50, confidence intervals, assembly, PMU counters, allocation, and stack/code shape.
- Execute the regenerated symbol through the pinned Qwen model.

## Success

The regenerated baseline is within the declared performance gate, is E1-equivalent, is
dynamically bound in the production model path, and produces identical generated output.
