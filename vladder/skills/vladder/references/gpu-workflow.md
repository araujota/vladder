# Heterogeneous GPU Evidence

## Choose The Boundary

Use `vladder shader inspect|synthesize` for a standalone GLSL/SPIR-V optimizer recipe study. Use
`vladder gpu capture|synthesize|verify|rank` when the claim includes architecture resources,
launch geometry, queue synchronization, DMA/topology, presentation, or counter attribution.

```bash
vladder gpu support
vladder gpu probe --out gpu-architecture.yaml
vladder gpu topology --out device-topology.json
vladder workflow init --kind gpu --out gpu-workflow.yaml
vladder gpu capture --manifest gpu-workflow.yaml --out-dir gpu-capture
vladder gpu synthesize --manifest gpu-workflow.yaml --out-dir gpu-synthesis
vladder gpu verify --manifest gpu-workflow.yaml --out-dir gpu-proof
vladder gpu rank --manifest gpu-workflow.yaml --out-dir gpu-ranking
```

For a bounded CUDA pointwise kernel, use the executable source path directly:

```bash
vladder gpu cuda-synthesize --source kernel.cu --function transform \
  --architecture gpu-architecture.yaml --out-dir cuda-candidates
vladder gpu cuda-optimize --source kernel.cu --function transform \
  --architecture gpu-architecture.yaml --out-dir cuda-out
```

`cuda-optimize` emits `optimized.cu`, `optimized.patch`, and `launch-plan.json` only after exact
output hashes, device UUID, clean CUDA event timestamps, and the effect threshold pass. Apply the
source and launch plan together. A source patch without its selected launch geometry is not the
measured candidate.

## Kernel Capture

`heterogeneous-execution-v1` recognizes GLSL/SPIR-V, PTX, and a strict CUDA source envelope. CUDA
source is compiled to pinned PTX for the probed architecture when `nvcc` exists. The executable
`cuda-pointwise-schedule-v1` envelope is one lane-independent guarded assignment with `float *`,
`const float *`, and `size_t` parameters, a canonical one-dimensional global index, and a simple
arithmetic expression. It generates bounded thread-block and contiguous per-thread schedules.
Other CUDA source and opaque PTX/SPIR-V code remains capturable but requires a dialect adapter for
code-changing regeneration. Operations lower into the same `SemanticFlowGraph v2` vocabulary used
by CPU and lifetime workflows. Dialect instructions remain provenance, not a competing ontology.

Capture records dispatch/workgroup/lane structure, memory transactions, barriers, atomics,
resource declarations, unsupported operations, and source/module/disassembly hashes. Opaque
SPIR-V local sizes are fixed. Literal GLSL workgroup sizes may be regenerated. PTX `.maxntid`
permits bounded launch-only geometry changes; `.reqntid` does not.

Typed SPIR-V capture additionally records scalar/vector logical operations, unsigned quotient and
remainder validity domains, dot and matrix numeric policy, image descriptor/sampler state, and
cooperative-matrix capability/shape obligations. `unsupported_operations: []` means the opcode
vocabulary closed; it does not discharge those contracts. Bind `preserve_spirv_validity_domain`,
`numeric_policy`, `image_descriptor_contract`, and `cooperative_matrix_contract` as applicable,
then provide an exact output runner. `gpu verify` remains `INCOMPLETE` for unbound obligations.

## Architecture-Aware Search

`vladder gpu probe` queries the CUDA driver for device UUID, architecture, warp and SM limits,
register and shared-memory capacity, and clocks, then measures a sustainable copy-flow bandwidth.
Each compiled candidate is loaded through the CUDA driver so the report uses JIT-resolved register,
local-memory, shared-memory, PTX, binary, and maximum-thread properties. Assumed allocation and
transaction granularities remain labeled assumptions. Static candidates report occupancy and
limiting resources, useful and physical bytes, coalescing, and a pruning score.

Static estimates are hypotheses. They do not model final driver scheduling and never promote a
candidate. Generic realization is deliberately bounded:

- `launch_plan`: unchanged kernel code with a legal launch change;
- `source_rewrite`: recognized lane-independent GLSL workgroup or bounded CUDA pointwise schedule;
- `adapter_required`: unroll, vector-width, shared-staging, opaque binary geometry, or any
  unrecognized code-shape change needing a dialect-specific lowerer.

For CUDA pointwise schedules, Z3 proves exact mixed-radix coverage and injectivity for the declared
extent, while normalized literal identity preserves the per-element expression. Exact randomized
device output hashes remain a separate differential oracle. The proof does not establish CUDA
compiler correctness, driver scheduling, host launch integration, or external protocols.

## Device Protocols

Queue manifests model ordered submissions, resource reads/writes, stage/access metadata,
barriers, binary or timeline semaphores, and queue-family ownership. DMA manifests model endpoint
capabilities, registration, direct or staged topology routes, producer completion, publication,
consumer completion, and safe reuse. Presentation manifests model acquire, render completion,
present, scanout, release, and deadline policy.

Read every `issues` and `obligations` entry. A passing bounded protocol proves only the declared
finite model. Driver and firmware correctness, undeclared external actors, device loss, NIC/display
behavior, and topology outside the manifest remain excluded claims.

Bind protocol plans to the live machine before treating them as physical candidates:

```bash
vladder gpu topology --out device-topology.json
vladder gpu queue-template --topology device-topology.json --out queue.yaml
vladder gpu dma-template --topology device-topology.json --destination nic0 --out dma.yaml
vladder gpu presentation-template --topology device-topology.json --out presentation.yaml
vladder gpu protocol-verify --manifest queue.yaml --out-dir queue-proof
```

The topology probe joins CUDA and Vulkan devices by UUID, records Vulkan queue families and
synchronization features, PCIe/IOMMU ancestry, NIC/RDMA capabilities, and DRM connectors. A queue
plan fails when the observed family lacks a required operation. A direct DMA plan is emitted only
when both GPU export and NIC peer-import capabilities exist. DMA templates intentionally fail until
registration, producer completion, DMA completion, publication, and reuse mechanisms are filled
from the application. Presentation templates fail when no connector is active. Topology discovery
alone never proves a transfer or page flip occurred.

## Physical Ranking

The built-in CUDA artifact runner launches each sample in a fresh native process and emits an exact
FNV-1a output hash, device UUID, launch geometry, and clean CUDA-event duration. External runners
must provide the same evidence contract. vLadder randomizes baseline/candidate process order,
performs paired comparisons, and uses bootstrap confidence intervals.

Nsight Compute collection is built in for CUDA artifacts. CUPTI/Nsight, ROCprofiler, Vulkan
performance queries, or application-runner counters
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

Nsight replay count and serialized execution are recorded. The profiler's duration is never mixed
with the CUDA-event ranking samples; counters explain occupancy, sectors, cache behavior,
instructions, and stalls after the physical decision.
