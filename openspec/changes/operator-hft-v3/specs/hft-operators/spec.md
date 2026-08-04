## ADDED Requirements

### Requirement: Deterministic Fixed-Capacity Domain

The HFT POC SHALL use versioned fixed-width schemas, fixed-capacity state, one
instrument per instance, and no hot-path allocation or external I/O.

#### Scenario: Oversized message

- **GIVEN** a message length outside its schema
- **WHEN** decode runs
- **THEN** a deterministic error event is emitted without reading out of bounds
- **AND** book, feature, and risk state remain unchanged.

### Requirement: Five Low-Latency Operator Families

SiliconTune SHALL support binary decode, book update, pre-trade risk, rolling
feature update, and encode/SPSC enqueue.

#### Scenario: Integrated state audit

- **GIVEN** an integrated replay
- **WHEN** each event completes
- **THEN** normalized event, book state, top-of-book, features, risk result, wire
  output, sequence, and ring occupancy are auditable.

### Requirement: Transactional Risk Gate

Rejected risk operations SHALL not mutate reserved exposure.

#### Scenario: Late check failure

- **GIVEN** symbol checks pass and an account check fails
- **WHEN** the order is rejected
- **THEN** all reservation state equals its pre-call value
- **AND** a deterministic reject reason is emitted.

### Requirement: Tail-Safe Acceptance

HFT winners SHALL improve p50 by at least 10% and p99.9 by at least 5% without a
p99.99 regression above 1%, under the declared held-out replay.

#### Scenario: Faster median with rare stall

- **GIVEN** a candidate meeting p50 but regressing p99.99 by 2%
- **WHEN** acceptance runs
- **THEN** it cannot be an accepted winner.

### Requirement: Trace Separation

Tuning, held-out, and adversarial traces SHALL have separate deterministic hashes.

#### Scenario: Tuned trace submitted as held-out

- **GIVEN** identical trace hashes
- **WHEN** final ranking runs
- **THEN** acceptance is refused.

### Requirement: Batch-One Latency

Batch-one and microburst measurements SHALL be separate objective profiles.

#### Scenario: Burst throughput win

- **GIVEN** a burst-32 candidate with better throughput and worse batch-one tail
- **WHEN** the latency profile is selected
- **THEN** burst throughput cannot compensate for the tail regression.
