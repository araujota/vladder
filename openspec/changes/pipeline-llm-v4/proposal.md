# Change: LLM Pipeline Integration V4

## Why

V4 is validated only by production model graphs and end-to-end token generation, not
standalone pipeline simulations.

## What Changes

- Extract pinned llama.cpp graphs and map them into PipelineGraph.
- Support staged residual/norm, projection epilogue, RoPE, attention, and sampling regions.
- Benchmark Qwen first, then add Llama, Gemma, Mistral, and Phi manifests as artifacts permit.

## Success

At least one verified graph-level realization affects 25 percent of measured Qwen
decode; commercial acceptance requires a statistically established 5 percent model win.
