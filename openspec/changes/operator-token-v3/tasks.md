# Tasks

## Baseline And Contracts

- [x] Pin llama.cpp commit and build configuration.
- [x] Record exact production kernel source/commit in candidate reports.
- [x] Define tensor, model, quantization, context, tolerance, determinism, and
  sampling-seed contracts.

## Operators

- [x] Implement RMSNorm and residual/RMSNorm/quantization graphs and references.
- [x] Implement RoPE Q/K graph and reference.
- [x] Implement bounded quantized GEMV epilogue graph and reference.
- [x] Implement materialized and online attention reduction graphs/references.
- [x] Implement penalty, top-k/top-p/min-p, and greedy sampling graphs/references.

## Testing And Integration

- [x] Add extreme values, NaN/Inf policy, quantization edges, context buckets,
  repeated tokens, deterministic seeds, and long-run drift tests.
- [x] Benchmark staged, hand-fused, pinned-production, and synthesized candidates.
- [x] Integrate at least one graph-derived candidate into pinned llama.cpp.
- [x] Run model-level output and token-time comparison when model artifacts exist.

## Workflow

- [x] Add token operator manifests and CLI examples.
- [x] Strictly validate specs and publish standalone versus integrated evidence.
