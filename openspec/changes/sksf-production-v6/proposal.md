# Change: SKSF Production Projection and Pipeline Integration V6

## Why

Synthetic kernel wins do not establish model or portfolio value. SKSF must integrate
accepted graph-level candidates into pinned llama.cpp and exercise full inference state.

## What Changes

- Integrate generated gate/up and Q/K/V kernels with guarded runtime dispatch.
- Extend ranking through prompt, decode, concurrent serving, and KV pressure.
- Compose accepted plans into InferencePipelineGraph and emit patches.

## Success

An exact, graph-derived candidate improves portfolio-weighted Qwen tokens/sec by at least
five percent with no workload outside its floor and reproduces on a second matching host.
