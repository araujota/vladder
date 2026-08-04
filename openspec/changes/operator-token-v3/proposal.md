# Change: Token-Generation Operators V3

## Why

Synthetic pointwise wins do not establish decode relevance. V3 needs bounded
operators, production baselines, model/tensor contracts, adversarial numerical
testing, and at least one integration whose memory materialization changes.

## What Changes

- Pin llama.cpp and record exact kernel provenance.
- Add residual/RMSNorm/quantization, RoPE Q/K, quantized GEMV epilogue,
  restricted attention, and sampling/logit operator families.
- Add tensor/quantization/context contracts and high-precision references.
- Add standalone and llama.cpp-integrated benchmark adapters.

## Success

At least five token micro-operators run. An accepted production comparison uses
the pinned llama.cpp fused baseline where present. Synthetic-only results are
clearly separated from integration evidence.
