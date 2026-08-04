# Design: LLM Pipeline Integration V4

The pinned llama.cpp model builder and ggml graph are authoritative. An adapter records
node identity, tensor metadata, allocation/lifetime, backend, and profile attribution.
Patches remain narrow guarded graph/kernels changes. Baseline production fusions stay
enabled, and generated outputs are checked under exact deterministic sampling.
