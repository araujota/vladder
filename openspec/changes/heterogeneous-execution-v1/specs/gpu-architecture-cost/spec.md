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
