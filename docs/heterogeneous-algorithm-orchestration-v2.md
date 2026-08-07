# Heterogeneous Algorithm And Orchestration V2

This release layer makes bounded algorithmic and runtime-policy changes executable grammar
members. It sits above local GPU instruction/schedule search and below repository integration:

```text
measured attribution
  -> HeterogeneousPlanGraph
  -> bounded algorithm/policy enumeration
  -> generated CUDA/C++ or executable runtime manifest
  -> Z3 plus finite device-protocol proof
  -> exact application runner
  -> randomized physical promotion
```

## Supported Families

| Family | Generated realization | Proved locally | External requirement |
|---|---|---|---|
| GPU stable compaction | CUDA source plus one-workgroup or hierarchical three-pass launch plan | stable order, extent, capacity atomicity, lane/group coverage, barrier structure | descriptor/buffer binding and device timestamp runner |
| Queue overlap | queue assignment, semaphore, barrier, and resource manifest | dependency order, RAW/WAR/WAW visibility, finite queue/resource protocol | command-buffer binding and physical device timeline |
| Sparse update policy | C++ threshold compaction or exact minimum-byte encoding selector | dispatch completeness, stable output, capacity atomicity, exact minimum, deterministic ties | state/payload adapter and differential oracle |
| Presentation policy | supported mode, image count, flight count, deadline, and lifecycle manifest | acquire/render/present/scanout/release and bounded in-flight state | swapchain binding and physical present-stage/visible timestamps |

Every search requires attribution. Missing attribution and unbounded recursive SCCs fail closed.
Every candidate emits deterministic graph JSON, `SemanticFlowGraph v2`, GraphML, proof artifacts,
and a realization classification. GraphML is suitable for an advisory learned prior; it has no
authority over legality, proof, or promotion.

## Algorithmic Change Boundary

Algorithmic changes are represented by replacing graph topology while preserving the declared
observable contract. Examples include a scalar or one-workgroup filter becoming hierarchical
predicate/local-scan/group-scan/scatter, serial queue execution becoming a dependency-preserving
overlap plan, or one update encoding policy becoming a minimum-information-volume selector.

The grammar is not unrestricted algorithm invention. Each family has a finite semantic template,
bounded parameters, deterministic lowering, and specific proof obligations. A learned model can
prioritize plans but cannot introduce an unproved rewrite.

## External Systems

Driver scheduling, physical queue overlap, network delivery, presentation-engine behavior, and
scanout are not pure local code. vLadder searches the application-controlled policy and proves its
finite state/resource semantics, then delegates physical truth to a runner.

- GPU-to-NIC DMA remains a topology, registration, ownership, completion, and reuse protocol. It is
  not promoted without a representative NIC path.
- WAN pacing/recovery can be represented as a bounded congestion/pacing transducer with packet,
  ACK, loss, deadline, and bytes-in-flight observables. A dedicated executable network-policy
  lowerer is not part of this change; the finite protocol and application runner remain required.
- Presentation policy is executable as a runtime plan, but visible latency needs presentation-stage
  feedback or an external display measurement. Modeled frame latency cannot promote.

## NeuralFusion Read-Only Validation

Validation used `/root/Documents/Codex/2026-06-28/create-a-new-fit-repo-for` without modifying it.
The audit captured identical pre/post `git status --porcelain` output.

- 74 heterogeneous binding surfaces were recognized: 6 compaction, 5 typed SPIR-V, 1 exact sparse
  policy, 59 broad queue-submission owners, and 3 presentation owners. These counts are discovery
  results, not 74 closed optimizations; many queue owners are tools/tests or share one implementation.
- `p2_sparse_discover`, `p2_sparse_local_scan`, `p2_sparse_group_scan`, and `p2_sparse_scatter`
  compiled and achieved complete typed SPIR-V capture with zero unresolved semantic obligations.
- The four stages map to predicate, local prefix, group prefix, and stable scatter nodes in the
  hierarchical GPU compaction graph. Generated CUDA closes the algorithm proof unit; Vulkan shader
  replacement still requires descriptor, dispatch, and exact device-output adapters.
- `src/runtime/sparse_p2_cache.cpp` was recognized as an exact minimum-byte selector over dense
  bitmap, sparse bitmap bytes, runs, and full representations. The generated C++ selector compiles,
  proves minimum selection and tie behavior, and passes native differential fixtures. Integrating it
  still requires binding NeuralFusion's statistics and payload enum without changing wire bytes.
- `src/client/vulkan_presentation.cpp` is now a presentation-plan binding target. No physical
  presentation promotion was attempted because this host has no active monitor/visible-stage runner.

This validation establishes semantic and lowering relevance, not a NeuralFusion speedup. Physical
ranking belongs in the owning application once exact adapters and representative hardware are
available.
