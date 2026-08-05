## ADDED Requirements

### Requirement: Queue dependency verification
vLadder SHALL verify bounded queue submissions, semaphore timelines, barriers, stage/access scopes,
resource ownership, and RAW/WAR/WAW hazards.

#### Scenario: Producer write followed by consumer read
- **WHEN** two operations access the same resource with a write-read hazard
- **THEN** an execution dependency and sufficient memory availability/visibility SHALL be required

### Requirement: External DMA and topology verification
vLadder SHALL model device registration, physical route, ownership transfer, DMA completion, memory
ordering, publication, and fallback for direct and staged transfer plans.

#### Scenario: GPU-to-NIC direct DMA
- **WHEN** a NIC consumes GPU-resident bytes directly
- **THEN** topology reachability, memory registration, GPU completion ordering, NIC ownership, and
  completion-before-reuse SHALL be proved or explicitly required

### Requirement: Presentation lifecycle verification
vLadder SHALL model image acquisition, rendering, presentation, scanout, release, and reuse.

#### Scenario: Page flip candidate
- **WHEN** a rendered image is scheduled for scanout
- **THEN** rendering SHALL complete before the flip and the image SHALL not be overwritten until
  release or the declared replacement event

### Requirement: Live capability binding
Protocol candidates SHALL be bindable to observed device, queue-family, PCIe/IOMMU, NIC/RDMA, and
DRM connector identities without treating capability discovery as runtime completion evidence.

#### Scenario: Unsupported direct GPU-to-NIC transfer
- **WHEN** either the selected GPU lacks peer-DMA export or the selected NIC lacks RDMA peer import
- **THEN** no direct route SHALL be admitted and any generated plan SHALL use a declared staged
  fallback or fail closed

#### Scenario: Queue family capability mismatch
- **WHEN** a physically bound operation requires compute, graphics, or transfer behavior absent
  from its observed queue family
- **THEN** queue protocol verification SHALL produce a counterexample

#### Scenario: No active display connector
- **WHEN** the DRM probe observes no connected connector
- **THEN** a presentation template SHALL remain unproved and SHALL not claim page-flip or scanout
  execution
