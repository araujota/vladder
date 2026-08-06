# Close Grammar-Limitation Incidents RC17

## Why

The NeuralFusion rc16 audit found locally available semantics that vLadder could parse but could
not represent precisely enough to reach executable candidate and proof workflows. The dominant
gaps are C++ ownership/cleanup/call relations, exact SPIR-V operations, structured stateful
dataflow, and unsafe artifact naming. These are distinct from proprietary driver behavior and
unavailable physical routes, which remain contract and measurement boundaries.

## What Changes

- Parse SPIR-V instructions rather than arbitrary `Op*` words and add typed semantics for boolean,
  unsigned division/remainder, vector dot, matrix-vector, image, and cooperative-matrix operations.
- Add operation validity and numerical-policy obligations and bind them to shader capture.
- Replace recursive C++ effect traversal with SCC-safe finite summary composition.
- Add parametric C++ container, object-lifetime, exceptional-cleanup, aggregate/member-state, and
  synchronization descriptors without treating standard-library calls as external I/O.
- Add a domain-neutral finite protocol DSL for resources, transitions, failure outcomes,
  happens-before, publication, rollback, and retirement.
- Add structured deep-dataflow archetypes for sparse, parse/materialize, cache, partition/scatter,
  state-transition, traversal-fusion, and lifetime-realization regions.
- Bound generated artifact names with readable prefixes and stable identity hashes.
- Re-run the complete NeuralFusion C++ and shader corpus without modifying its repository.

## Non-Goals

- Proving proprietary driver, firmware, OpenUSD implementation, kernel-networking, display, or NIC
  internals.
- Claiming whole-program C++ equivalence from effect summaries.
- Promoting shader candidates without exact application output and physical timestamp runners.
- Treating recognition of an archetype as proof or a performance result.

