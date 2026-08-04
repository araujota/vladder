# Change: Q4_K Active Path Capture V7

## Why

Production transfer is invalid unless the benchmark proves which llama.cpp kernel,
layout, dimensions, and model tensors actually executed.

## What Changes

- Add opt-in runtime Q4_K dispatch records.
- Freeze source, binary, compiler, model, and hardware hashes.
- Fail closed when the observed decode symbol differs from the manifest.

## Success

The pinned Qwen run captures representative FFN and attention tensors and proves that
single-row decode selects the declared Q4_K GEMV path.
