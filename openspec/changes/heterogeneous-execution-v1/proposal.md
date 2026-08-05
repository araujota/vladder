## Why

vLadder can currently validate and perturb SPIR-V modules, but it cannot represent the physical
kernel execution, architecture resource limits, device queues, cross-device DMA, presentation, or
hardware-counter evidence in the same typed information-flow vocabulary used for CPU work. Those
surfaces therefore stop at external runner evidence rather than generated, verified, physically
ranked realization search.

## What Changes

- Extend SemanticFlowGraph with language-neutral parallel execution, memory transaction, resource,
  synchronization, DMA, topology, presentation, and counter concepts.
- Capture SPIR-V and PTX kernels into a shared GPUKernelGraph with source/assembly provenance and
  explicit unsupported operations.
- Add architecture manifests and deterministic occupancy, register, shared-memory, transaction,
  and scheduling cost models.
- Add bounded protocol graphs and Z3 obligations for Vulkan-style queue dependencies, external DMA
  ownership/order, and acquire-render-present-release lifecycles.
- Add architecture-aware execution-plan grammar and fail-closed source/binary realization classes.
- Add counter normalization and counter-supported physical ranking without ranking instrumented
  executions as if they were production timings.
- Add a manifest-driven `vladder gpu` workflow while retaining `vladder shader` compatibility.

## Impact

GPU and external-device work becomes expressible in the same information-flow ontology as CPU and
lifetime work. Exact claims remain bounded: SPIR-V/PTX capture is semantic decomposition, bounded
protocol proofs cover only declared finite resources and events, and physical promotion still
requires exact output parity plus uninstrumented device timing on the declared topology.
