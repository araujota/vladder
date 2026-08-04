# Tasks

## Extraction And Corpus

- [x] Extract a normalized Qwen3 decode PipelineGraph from pinned llama.cpp.
- [x] Record model, quantization, context, prompt, seed, and graph hashes.
- [ ] Add manifests for Qwen and discover optional Llama/Gemma/Mistral/Phi artifacts.

## Progressive Regions

- [ ] Integrate residual/norm/activation pipeline alternatives.
- [ ] Integrate projection epilogue and quantized-block alternatives.
- [ ] Integrate RoPE Q/K traversal alternatives.
- [ ] Integrate online attention reduction alternatives.
- [ ] Integrate exact sampling pipeline alternatives.

## Acceptance

- [ ] Attribute at least 25 percent of measured decode to synthesized regions.
- [ ] Run fixed-seed output and repeated tokens/second comparison.
- [ ] Emit production patch, derivation, proof, and attribution report.
