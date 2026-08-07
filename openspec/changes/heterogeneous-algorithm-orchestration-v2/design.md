# Design: Heterogeneous Algorithm And Orchestration V2

## Context

The existing heterogeneous stack has three useful but disconnected layers: GPU kernel graphs,
finite device protocols, and physical ranking. The missing layer is a search representation for
algorithm and runtime-policy alternatives. This change adds that layer without treating external
systems as ordinary pure functions.

## Decisions

### 1. Use one semantic vocabulary

`HeterogeneousPlanGraph` uses universal nodes such as `Load`, `Predicate`, `Scan`, `Scatter`,
`Dispatch`, `QueueOperation`, `Barrier`, `Publish`, `Acquire`, and `Present`. CUDA, Vulkan, socket,
and swapchain concepts are bindings and provenance, not separate semantic universes.

### 2. Keep search finite and attributed

Each manifest declares finite parameter domains and an admission reason tied to measured bytes,
cycles, queue idle time, sparse density, or presentation delay. Candidate limits are enforced before
enumeration. Learned or GraphML-derived priors may order candidates but may not establish legality,
proof, or bounded optimality.

### 3. Separate four plan families

- `gpu-stable-compaction`: predicate, prefix, exact extent, capacity guard, stable scatter.
- `queue-overlap`: legal queue assignment and synchronization over a finite dependency DAG.
- `sparse-update-policy`: exact sparse/dense dispatch, stable payload construction, and generation
  commit under a bounded trace contract.
- `presentation-policy`: image count, frames in flight, supported present mode, acquire/present
  ordering, and deadline policy.

The families share graph, proof, provenance, GraphML, and runner schemas.

### 4. Source and plan lowering are distinct executable realizations

The bounded one-workgroup and three-pass hierarchical compaction family emits compilable CUDA source. Queue, sparse-policy, and
presentation families emit deterministic runtime-plan manifests consumed by an application adapter.
Both are executable outputs, but only generated source is a source replacement. Reports preserve
this distinction.

### 5. Proof is layered

Z3 proves bounded coverage, injectivity/stability, extent/capacity, dispatch completeness, dependency
preservation, and finite lifecycle properties. Existing queue and presentation verifiers prove
resource hazards and acquire/present/reuse rules. Differential output and physical timing remain
mandatory for promotion.

### 6. Physical runners own external truth

A common runner result contains exact output/state hashes, device identity, evidence class, total
latency, stage timestamps, and policy metrics. Presentation may additionally report acquired,
submitted, dequeued, first-pixel-out/visible, dropped, and missed-deadline events when supported.
Absent timing extensions or a physical display, presentation candidates remain verified plans and
cannot be physically promoted.

### 7. Recursive and large graphs require explicit bounds

Recursive SCCs are summarized with declared maximum depth/state count. GraphML export records SCC,
feature, and bound metadata for an upcoming model. An unbounded SCC is not enumerated or proved.

## Claim Boundary

The system may claim a best verified plan in an enumerated bounded grammar. It may not claim driver
scheduling, network delivery, display visibility, or universal algorithmic optimality without the
corresponding physical evidence.
