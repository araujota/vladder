## ADDED Requirements

### Requirement: Pinned architecture resource model
vLadder SHALL calculate resource feasibility and occupancy from a hash-bound architecture manifest.

#### Scenario: Register-limited launch
- **WHEN** registers per thread constrain resident blocks below the thread/shared-memory limits
- **THEN** the report SHALL identify registers as the active occupancy limiter

### Requirement: Information-movement accounting
The cost model SHALL report useful bytes, physical transactions, coalescing efficiency, shared/local
traffic, and synchronization cost separately.

#### Scenario: Strided global access
- **WHEN** lane addresses span more memory segments than a contiguous access
- **THEN** the candidate SHALL receive a larger transaction estimate with the assumed segment width

### Requirement: Static model boundary
Static cost and occupancy SHALL be pruning and attribution evidence, not a physical winner claim.

#### Scenario: Higher estimated occupancy
- **WHEN** a candidate has a higher occupancy estimate but no device timing
- **THEN** it SHALL remain physically unranked

### Requirement: Runtime-calibrated architecture evidence
vLadder SHALL distinguish probed device limits, compiler/JIT-resolved candidate resources,
measured sustainable bandwidth, and architecture-family assumptions.

#### Scenario: CUDA candidate resource inspection
- **WHEN** a generated PTX candidate is loaded on the target device
- **THEN** its resolved registers, local memory, static shared memory, PTX/binary version, and
  maximum thread count SHALL be recorded and used for feasibility analysis

#### Scenario: Assumed transaction granularity
- **WHEN** transaction or register allocation granularity is not directly reported by the runtime
- **THEN** the value SHALL remain an explicit model assumption rather than a measured hardware fact
