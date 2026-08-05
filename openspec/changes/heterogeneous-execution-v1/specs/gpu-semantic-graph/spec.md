## ADDED Requirements

### Requirement: Shared device-kernel semantic graph
vLadder SHALL represent SPIR-V and PTX kernels with the same parallel execution, information-flow,
memory-region, synchronization, and observable vocabulary.

#### Scenario: Equivalent storage operations in different dialects
- **WHEN** SPIR-V storage-buffer operations and PTX global-memory operations are captured
- **THEN** both SHALL use shared load/store/transaction concepts while retaining dialect opcodes as
  provenance

### Requirement: Complete capture disposition
Capture SHALL report mapped operations, unsupported operations, execution geometry, storage
regions, barriers, atomics, and resource estimates.

#### Scenario: Unsupported device instruction
- **WHEN** an instruction has no semantic binding
- **THEN** the graph SHALL retain an explicit unsupported node or blocker and SHALL not claim full
  kernel semantic capture

### Requirement: Cross-level claim boundaries
Kernel graph equivalence SHALL not imply host queue, DMA, presentation, or driver equivalence.

#### Scenario: Kernel output is exact
- **WHEN** device outputs match for a candidate
- **THEN** protocol claims SHALL remain independently required unless their graph is also verified
