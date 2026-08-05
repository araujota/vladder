## Why

vLadder has a strong local proof and attribution stack, but an agent must currently assemble several
commands and reports to determine whether a result can move from inspection to production. C++
ownership and external protocols frequently require adapters without a generated starting point,
weak lifetime traces can look like successful analyses, and physical promotion still depends on
custom benchmark code. GPU compute has no comparable first-class evidence workflow.

## What Changes

- Add a manifest-driven agent workflow that emits one queryable lineage and one promotion summary.
- Distinguish workflow completion, semantic capture, candidate generation, proof, physical evidence,
  application integration, and retained production optimization as independent states.
- Generate C++ benchmark, observable, state-projection, and external-protocol adapter bundles from
  closure metadata without claiming the adapters are complete.
- Add bounded Z3 verification for generic versioned-cache and transactional-publication protocols.
- Add randomized paired-process measurement with bootstrap intervals and overlap-aware composition.
- Reject weak lifetime traces as `insufficient_attribution` before candidate synthesis.
- Add a portable GLSL/SPIR-V compute workflow with structural validation, bounded optimizer recipes,
  output-oracle hooks, and GPU timestamp adapters. CUDA remains a toolchain/runner adapter unless its
  production state and execution environment are supplied.
- Add resumable workflow stages keyed by source, compiler, grammar, contract, and workload hashes.
- Promote architectural information-volume findings to explicit outcomes even when no local source
  candidate is available.

## Impact

The release becomes a coherent agent workflow rather than a collection of expert-only subcommands.
It materially reduces adapter and benchmark boilerplate while retaining fail-closed claims at C++,
GPU, concurrency, syscall, driver, and other external boundaries. It does not claim arbitrary C++
or whole-device equivalence.
