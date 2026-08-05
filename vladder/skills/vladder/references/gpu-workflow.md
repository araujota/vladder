# Heterogeneous GPU Evidence

## Choose The Boundary

Use `vladder shader inspect|synthesize` for a standalone GLSL/SPIR-V optimizer recipe study. Use
`vladder gpu capture|synthesize|verify|rank` when the claim includes architecture resources,
launch geometry, queue synchronization, DMA/topology, presentation, or counter attribution.

```bash
vladder gpu support
vladder workflow init --kind gpu --out gpu-workflow.yaml
vladder gpu capture --manifest gpu-workflow.yaml --out-dir gpu-capture
vladder gpu synthesize --manifest gpu-workflow.yaml --out-dir gpu-synthesis
vladder gpu verify --manifest gpu-workflow.yaml --out-dir gpu-proof
vladder gpu rank --manifest gpu-workflow.yaml --out-dir gpu-ranking
```

## Kernel Capture

`heterogeneous-execution-v1` recognizes GLSL/SPIR-V and PTX. CUDA source is compiled to pinned PTX
when `nvcc` exists; otherwise capture the exact deployed PTX and record the unavailable source
toolchain. Operations lower into the same `SemanticFlowGraph v2` vocabulary used by CPU and
lifetime workflows. Dialect instructions remain provenance, not a competing semantic ontology.

Capture records dispatch/workgroup/lane structure, memory transactions, barriers, atomics,
resource declarations, unsupported operations, and source/module/disassembly hashes. Opaque
SPIR-V local sizes are fixed. Literal GLSL workgroup sizes may be regenerated. PTX `.maxntid`
permits bounded launch-only geometry changes; `.reqntid` does not.

## Architecture-Aware Search

The hardware manifest is authoritative for device identity, warp/subgroup width, thread/block/SM
limits, registers, allocation granularity, shared memory, transaction width, issue width, clock,
and measured sustainable bandwidth. Static candidates report occupancy and limiting resources,
register/shared-memory pressure, useful and physical bytes, coalescing, and a pruning score.

Static estimates are hypotheses. They do not model final driver scheduling and never promote a
candidate. Generic realization is deliberately bounded:

- `launch_plan`: unchanged kernel code with a legal launch change;
- `source_rewrite`: recognized lane-independent GLSL with a literal workgroup-size rewrite;
- `adapter_required`: unroll, vector-width, shared-staging, opaque binary geometry, or any
  unrecognized code-shape change needing a dialect-specific lowerer.

The bounded Z3 proof establishes resource feasibility and one-dimensional launch-index coverage.
It does not prove output equivalence or physical scheduling.

## Device Protocols

Queue manifests model ordered submissions, resource reads/writes, stage/access metadata,
barriers, binary or timeline semaphores, and queue-family ownership. DMA manifests model endpoint
capabilities, registration, direct or staged topology routes, producer completion, publication,
consumer completion, and safe reuse. Presentation manifests model acquire, render completion,
present, scanout, release, and deadline policy.

Read every `issues` and `obligations` entry. A passing bounded protocol proves only the declared
finite model. Driver and firmware correctness, undeclared external actors, device loss, NIC/display
behavior, and topology outside the manifest remain excluded claims.

## Physical Ranking

A runner command emits one JSON object per invocation with exact observable identity and a clean
device timestamp. The ranking manifest must use the same hardware identity as the architecture
manifest. vLadder randomizes baseline/candidate process order, performs paired comparisons, and
uses bootstrap confidence intervals.

Counter imports from CUPTI/Nsight, ROCprofiler, Vulkan performance queries, or application runners
are normalized into shared occupancy, byte, transaction, cache, stall, divergence, instruction,
and throughput categories while retaining raw names and collector provenance. Counter collection
supports attribution. Replayed or serialized profiler timing cannot rank.

Promotion requires all of:

1. complete recognized kernel capture;
2. passing declared queue/DMA/presentation protocols;
3. exact output hashes for baseline and candidate;
4. matching concrete device identity;
5. `hardware-device-timestamp` or `application-device-timestamp` evidence;
6. a confidence interval excluding the minimum effect.

`spirv-val`, optimizer provenance, operation-shape equality, launch proof, static occupancy,
counter evidence, and simulated runners are individually non-promoting.
