# Change: LLM Projection Integration V5

## Why

V5 must demonstrate generalized gate/up and Q/K/V relevance in production llama.cpp,
not only synthetic projection fixtures.

## What Changes

- Bind Qwen projection complexes to authoritative ggml nodes and model hashes.
- Add phase/token/sequence/context provenance.
- Require exact generated-token verification before model ranking.
