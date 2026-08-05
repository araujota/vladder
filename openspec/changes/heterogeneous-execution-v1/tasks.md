## 1. Research And Architecture

- [x] 1.1 Validate current GPU limitations against source and tests.
- [x] 1.2 Research SPIR-V, PTX/CUDA, Vulkan synchronization, GPUDirect/dma-buf, KMS, and counter APIs.
- [x] 1.3 Define shared graph levels, claim boundaries, and realization classes.

## 2. Semantic Graphs And Recognition

- [x] 2.1 Extend SemanticFlowGraph vocabulary for parallel execution and external-device protocols.
- [x] 2.2 Implement SPIR-V and PTX recognition with typed nodes, edges, resources, and provenance.
- [x] 2.3 Compose kernel, protocol, topology, and placement into HeterogeneousExecutionGraph.

## 3. Architecture And Grammar

- [x] 3.1 Implement hardware manifests and occupancy/register/shared-memory/transaction cost models.
- [x] 3.2 Implement architecture-aware schedule, memory, barrier, and placement grammar plans.
- [x] 3.3 Emit deterministic realization classifications and reject unsupported lowering honestly.

## 4. Protocol Verification

- [x] 4.1 Implement queue/semaphore/barrier hazard and timeline verification.
- [x] 4.2 Implement GPU/NIC DMA registration, route, ownership, completion, and topology verification.
- [x] 4.3 Implement swapchain/page-flip/scanout acquire-present-release verification.

## 5. Physical Evidence

- [x] 5.1 Normalize CUPTI, ROCprofiler, Vulkan-query, and runner counters with provenance.
- [x] 5.2 Implement clean-timing plus counter-supported randomized physical ranking.
- [x] 5.3 Reject profiler-distorted, incomplete-observable, topology-mismatched, and unproved evidence.

## 6. Workflow And Release

- [x] 6.1 Add `vladder gpu capture|synthesize|verify|rank|support` and manifests.
- [x] 6.2 Add fixtures, unit tests, CLI tests, and end-to-end simulated evidence tests.
- [x] 6.3 Update README, architecture, bundled skill, examples, and release metadata.
- [x] 6.4 Run full tests, strict OpenSpec, package build/install, and strict doctor.

## 7. Native Runtime Closure

- [x] 7.1 Add a CUDA-driver runner with deterministic inputs, exact output hashes, clean device
  timestamps, and JIT-resolved kernel resources.
- [x] 7.2 Add bounded CUDA pointwise extraction, source regeneration, exhaustive schedule search,
  Z3 coverage/injectivity proof, physical promotion, patch, and launch-plan emission.
- [x] 7.3 Add automatic Nsight Compute collection while excluding replay timing from ranking.
- [x] 7.4 Probe and bind CUDA/Vulkan UUIDs, queue families, PCIe/IOMMU/NIC/RDMA topology, and DRM
  connectors; reject unsupported direct DMA and inactive presentation paths.
- [x] 7.5 Strengthen queue stage/access checks, repeated presentation lifecycle verification, and
  DMA registration/completion/publication/reuse obligations.
- [x] 7.6 Exercise both no-win and promoted CUDA searches on the local RTX target and retain exact
  proof, clean timing, counter, replacement, and launch-plan artifacts.
