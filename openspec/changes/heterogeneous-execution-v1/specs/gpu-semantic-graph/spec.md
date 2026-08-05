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

### Requirement: Executable bounded CUDA semantics
vLadder SHALL extract and regenerate explicitly supported lane-independent CUDA source regions
without translating them through a CPU language.

#### Scenario: Pointwise schedule transformation
- **WHEN** a CUDA kernel contains one canonical guarded pointwise assignment
- **THEN** vLadder SHALL preserve the element expression, prove exact schedule coverage and
  injectivity, compile the regenerated CUDA source for the pinned architecture, and retain all
  unsupported host and device claims explicitly

#### Scenario: CUDA kernel outside the bounded envelope
- **WHEN** a CUDA kernel contains unsupported shared state, atomics, synchronization, loops, or
  unrecognized expressions
- **THEN** code-changing regeneration SHALL be rejected as adapter-required while capture and
  attribution may continue
