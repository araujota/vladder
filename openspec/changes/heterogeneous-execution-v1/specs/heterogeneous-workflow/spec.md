## ADDED Requirements

### Requirement: Manifest-driven heterogeneous workflow
vLadder SHALL capture, synthesize, verify, and rank kernels and device protocols from one manifest.

#### Scenario: SPIR-V kernel plus Vulkan queue contract
- **WHEN** a manifest supplies a module, architecture, queue protocol, exact observable runner, and
  physical policy
- **THEN** the workflow SHALL emit graph, candidates, proofs, resource costs, physical evidence,
  lineage, and one bounded disposition

### Requirement: Architecture-aware grammar
Candidate derivations SHALL identify whether they change binary code, launch geometry, memory
realization, synchronization, topology, or presentation policy.

#### Scenario: No executable backend for a plan
- **WHEN** a legal semantic candidate cannot be emitted for the selected dialect/API
- **THEN** it SHALL be classified `adapter_required` and SHALL not be physically promoted

### Requirement: Safe rewrite boundary
Generated replacement artifacts SHALL be emitted only when all local and protocol obligations in
the selected scope pass and clean physical ranking promotes the candidate.

#### Scenario: Protocol proof missing
- **WHEN** a kernel candidate wins timing but its queue/DMA/presentation protocol is unverified
- **THEN** no production replacement SHALL be emitted

#### Scenario: CUDA source and launch are jointly selected
- **WHEN** physical ranking promotes a bounded CUDA schedule
- **THEN** the replacement SHALL contain the source derivation, source/proof hashes, patch, and the
  exact selected threads and elements-per-thread launch plan

### Requirement: Fail-closed topology templates
vLadder SHALL generate queue, DMA, and presentation templates from live capability evidence while
leaving unobserved runtime mechanisms unresolved.

#### Scenario: Topology exists without transfer evidence
- **WHEN** PCIe reachability is observed but registration, producer completion, DMA completion,
  publication, or reuse guards are not supplied
- **THEN** the generated DMA protocol SHALL fail verification with each missing mechanism named
