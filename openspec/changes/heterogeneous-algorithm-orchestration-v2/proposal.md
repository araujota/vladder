# Change: Add Executable Heterogeneous Algorithm And Orchestration Grammars

## Why

vLadder can capture GPU kernels, tune bounded pointwise schedules, verify finite queue/DMA/
presentation protocols, and rank externally executed candidates. It cannot yet generate executable
alternatives for the higher-value choices above a local kernel: workgroup algorithm topology,
cross-queue overlap, sparse-update representation policy, and presentation pacing. Those choices
change which information-flow graph exists and cannot be expressed as compiler flags.

## What Changes

- Introduce one bounded `HeterogeneousPlanGraph` vocabulary for algorithm stages, resource
  dependencies, policy guards, physical placement, and externally measured observables.
- Add executable CUDA source lowering for one-workgroup and bounded hierarchical stable compaction and manifest lowering for
  queue-overlap, sparse-update, and presentation policies.
- Add exhaustive bounded enumeration, Z3 obligations, existing device-protocol composition, static
  cost/risk estimates, and deterministic GraphML export for future learned ranking priors.
- Add a runner contract that separates simulated/model evidence from application-device timestamps,
  presentation feedback, and end-to-end physical evidence.
- Keep GPU-to-NIC, driver scheduling, display scanout, and network-path behavior outside local
  equivalence; plans crossing those boundaries remain physically validated adapters.

## Impact

Algorithmic changes become first-class grammar members rather than prose suggestions. A generated
plan can be executable even when its final repository integration remains an adapter, and reports
state exactly which semantics were proved, which source was generated, and which external behavior
still requires a representative runner.
