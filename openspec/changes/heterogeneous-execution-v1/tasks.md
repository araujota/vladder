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
