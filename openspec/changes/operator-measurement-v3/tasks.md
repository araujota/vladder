# Tasks

## Identity And Runner

- [x] Capture immutable hardware/software/workload manifests and hashes.
- [x] Reject mixed topology, affinity, governor, microcode, compiler, or trace data.
- [x] Add serialized cycles, independent processes, randomized order, warm/cold
  modes, and raw sample retention.
- [x] Collect perf counters, stack usage, relocations, vectorization remarks,
  traffic estimates, frequency, and thermal state.

## Statistics And Ranking

- [x] Compute p50/p90/p99/p99.9/p99.99/max and block-bootstrap intervals.
- [x] Implement statistical ties and minimum-effect thresholds.
- [x] Implement token and HFT objective profiles.
- [x] Reject HFT winners with material p99.99 regression.
- [x] Separate tuning and held-out traces.

## Workflow

- [x] Add target manifest and objective CLI controls.
- [x] Test incompatibility refusal and deterministic statistics.
- [x] Strictly validate specs and run measurement E2E tests.
