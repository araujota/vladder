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
