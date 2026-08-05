# GPU Compute Evidence

## Portable Core

`vladder shader inspect|synthesize` supports GLSL compute and SPIR-V modules through
`glslangValidator` and SPIR-V Tools. It records module/disassembly hashes, entry points, local sizes,
optimizer recipes, and structural validation.

SPIR-V validation is not semantic equivalence. SPIR-V optimizer provenance is not a proof.

## Runner Contract

A runner command contains `{module}` and emits one JSON object with:

```json
{"gpu_time_ns": 12345, "output_hash": "exact-observable-hash"}
```

The runner owns production-faithful descriptors, buffers, dimensions, synchronization, warmup,
device timestamp queries, error handling, and complete output readback. vLadder randomizes baseline
and candidate order and rejects output mismatch or an interval below the minimum effect.

## Protocol Boundary

Vulkan/CUDA host orchestration, queues, barriers, memory ownership, drivers, GPU-to-NIC/RDMA,
presentation, topology, and device loss are external protocol state unless explicitly modeled by
the runner or a bounded protocol adapter. CUDA tooling is reported separately; its absence does not
block SPIR-V, C++, lifetime, or CPU work.
