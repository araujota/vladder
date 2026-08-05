## ADDED Requirements

### Requirement: Counter normalization with provenance
vLadder SHALL normalize vendor counters into shared semantic categories while retaining raw names,
architecture, collector, replay count, and serialization behavior.

#### Scenario: ROCprofiler dispatch counting serializes kernels
- **WHEN** dispatch counters were collected in serialized mode
- **THEN** the report SHALL mark timing as profiler-distorted and SHALL not rank it as production time

### Requirement: Clean physical ranking
Promotion SHALL require exact declared observables and randomized uninstrumented device timing.

#### Scenario: Counter improvement without clean timing
- **WHEN** memory transactions improve under a profiler but no clean timing samples exist
- **THEN** the result SHALL be an attribution-supported hypothesis, not a physical winner

### Requirement: Hardware/topology identity
Measurements from materially different devices, drivers, firmware, queue topology, or counter
configurations SHALL not be combined.

#### Scenario: Device UUID mismatch
- **WHEN** baseline and candidate device identities differ
- **THEN** ranking SHALL fail closed

### Requirement: Native CUDA physical oracle
For bounded CUDA artifacts, vLadder SHALL support fresh-process execution with deterministic input,
exact output identity, target-device identity, launch geometry, and clean device-event timing.

#### Scenario: Generated CUDA candidate wins
- **WHEN** a generated candidate passes its bounded proof, matches the baseline output hash on the
  same device, and its randomized clean-timing confidence interval excludes the minimum effect
- **THEN** vLadder MAY emit the selected CUDA source and launch plan together

### Requirement: Counter/ranking separation
Hardware counter collection SHALL retain profiler replay and serialization evidence and SHALL not
replace clean physical timing.

#### Scenario: Nsight Compute replays a kernel
- **WHEN** Nsight Compute uses multiple replay passes and reports a profiler duration
- **THEN** the counters MAY explain a candidate but the profiler duration SHALL be excluded from
  effect-size and promotion calculations
