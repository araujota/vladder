## Context

Primary specifications expose common concepts despite different API spellings:

- SPIR-V defines SSA computation, execution models, storage classes, scopes, and memory semantics:
  <https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html>.
- PTX defines a parallel virtual ISA with thread hierarchy, state spaces, barriers, and memory
  consistency: <https://docs.nvidia.com/cuda/parallel-thread-execution/index.html>.
- CUDA occupancy is constrained by threads, warps, registers, shared memory, and resident blocks:
  <https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html>.
- Vulkan execution and memory dependencies distinguish stage ordering from availability and
  visibility: <https://docs.vulkan.org/spec/latest/chapters/synchronization.html>.
- GPUDirect RDMA creates an independent device data path whose ordering requires CUDA work
  submission/synchronization: <https://docs.nvidia.com/cuda/gpudirect-rdma/>.
- Linux dma-buf/dma-fence and KMS define shared DMA ownership, completion, page flips, and scanout:
  <https://docs.kernel.org/driver-api/dma-buf.html> and
  <https://docs.kernel.org/gpu/drm-kms.html>.
- CUPTI and ROCprofiler counters are architecture-specific, can require replay or serialization,
  and therefore support attribution but must not silently replace uninstrumented ranking.

## Decisions

### 1. Shared semantic vocabulary with dialect bindings

Core nodes describe workgroups, lanes, memory regions, transactions, barriers, queues, fences,
DMA, presentation, and resources. SPIR-V opcodes, PTX instructions, CUDA launch syntax, Vulkan
stage/access masks, and Linux/NVIDIA protocol objects are provenance and binding facts.

### 2. Three graph levels

`GPUKernelGraph` represents bounded device computation. `DeviceProtocolGraph` represents queue,
DMA, and presentation transitions. `HeterogeneousExecutionGraph` composes them with physical
placement and topology. Local kernel equivalence never implies protocol equivalence.

### 3. Architecture manifests are measured contracts

Resource limits and transaction widths come from a pinned manifest. Occupancy is a resource-feasible
upper bound, not a performance prediction. Static cost is used for pruning and explanation; exact
output and uninstrumented hardware timing remain the final oracle.

### 4. Protocol verification is hazard- and state-based

Queue verification checks RAW/WAR/WAW dependencies, execution scopes, memory visibility, queue
ownership, and timeline values. DMA verification checks registration, route, ownership, completion,
and publication. Presentation verification checks acquire-before-write, render completion before
present, release before reuse, image generation, and deadline policy.

### 5. Candidate realization classes are explicit

Candidates are classified as `binary_rewrite`, `launch_plan`, `protocol_plan`, `topology_plan`, or
`adapter_required`. A plan without a deterministic backend emitter remains useful search output but
cannot claim generated source/binary replacement.

### 6. Counter evidence is paired with clean timing

Counter adapters normalize metrics into semantic categories such as occupancy, memory transactions,
cache behavior, stalls, synchronization, and throughput. Counter collection records replay and
serialization distortion. Promotion uses randomized uninstrumented timing; counters explain and
filter candidates but cannot alone select a winner.

### 7. Native CUDA closure is deliberately bounded

`cuda-pointwise-schedule-v1` accepts one canonical one-dimensional lane-independent assignment.
The lowerer emits native CUDA source for thread-block and contiguous per-thread schedules. Z3
proves mixed-radix index coverage and injectivity, and normalized source identity preserves the
element expression. A CUDA-driver runner loads the resulting PTX on the target, records JIT
resources, hashes deterministic output bytes, and times with CUDA events. The selected source and
launch plan are one realization. Shared-memory algorithms, atomics, synchronization, indirect
calls, arbitrary control flow, opaque PTX rewrites, and CUDA host protocols remain adapters.

### 8. Capability discovery binds but does not discharge protocols

The live topology probe joins CUDA and Vulkan UUIDs and records queue families, synchronization
features, PCIe/IOMMU ancestry, NIC/RDMA capabilities, and DRM connectors. It may reject impossible
plans. It cannot prove that memory registration, queue execution, DMA completion, page flip, or
scanout occurred. Generated templates therefore preserve missing application mechanisms as failing
obligations rather than filling them with inferred booleans.

## Risks

- Static occupancy can reward kernels with more resident warps but worse instruction locality.
- SPIR-V does not expose the final machine register allocation or scheduling.
- PTX is a virtual ISA and does not prove final SASS behavior.
- Queue and DMA manifests may omit an external invalidator or ownership transition.
- Simulated runners validate workflow mechanics, not hardware performance.

## Validation

Use real SPIR-V compilation/disassembly, checked-in PTX, architecture manifests, intentionally
valid and invalid protocol fixtures, Z3 counterexamples, resource-limit tests, counter-replay
distortion tests, and deterministic simulated runners. On a CUDA-capable release host, also probe
the live CUDA/Vulkan/PCIe/NIC/DRM topology, compile native CUDA candidates, inspect JIT resources,
run exact-output clean-event ranking, collect Nsight counters separately, and exercise both a
no-win search and a promoted source-plus-launch realization. No test may promote a candidate
without exact observable parity and clean timing evidence.
