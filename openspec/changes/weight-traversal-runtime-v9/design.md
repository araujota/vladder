# Design: Runtime Planner and llama.cpp Integration V9

The simulator models arrivals, prompt work, decode readiness, queue wait, time to first token,
inter-token latency, weight-byte proxy use, and final sequence state. Dispatch is ordered from
specific guards to `true` fallback. Integration uses the pinned `llama-batched-bench` runtime:
default execution is the production batched path, while `-tgs` is retained only as a causal
sequence-separated ablation. Because the bounded winner lowers to the existing default path,
binary and argument identity deduplicate it before acceptance ranking.
