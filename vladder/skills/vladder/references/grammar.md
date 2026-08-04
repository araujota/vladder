# Grammar Selection

Inspect the active registry with `vladder grammar`, validate callable coverage with `vladder lower
validate`, and inspect one rule with `vladder lower show --family <id> --rule <rule>`.

Every rule has executable deterministic plan lowering. Plan lowering is not source emission: it
produces guards, information-flow operations, proof obligations, cost signals, and an optional
specialized backend route. A route remains shape-specific and must still generate, prove, and
benchmark a candidate before source promotion.

## Status

- `operational`: Has mature specialized generation and proof paths for supported shapes.
- `experimental`: Has bounded adapters or backend routes but requires domain-specific review.
- `modeled`: Has plan lowering and verification obligations but no source backend. Do not claim a source search.
- `research`: Has plan lowering and specialist workflows, not a general source-emission capability.

## Lowering Modes

- `plan`: Available for every rule. Missing contract facts or parameters reject the request.
- `source`: Routes only when a specialized backend exists. `routed` means the backend still needs
  its shape-specific inputs; it does not mean replacement source was emitted.
- A rule with no backend returns `unsupported` in source mode and emits no source.

## Families

- `expression-algebra`: scalar DAG, bit-vector, constants, strength reduction, selects.
- `control-flow`: branches, masks, predicates, fast paths, dispatch.
- `loop-schedule`: unroll, tile, fusion/fission, interchange, software pipeline.
- `memory-alias`: footprints, alignment, restrict, load/store order, prefetch.
- `reductions-scans`: accumulators, trees, scans, online reductions, recurrences.
- `layout-representation`: AoS/SoA, blocking, packing, interleaving, adapters.
- `materialization-fusion`: producer-consumer fusion and temporary elimination.
- `state-window`: bounded transition systems, windows, incremental state.
- `concurrency-memory-order`: ownership, SPSC, atomics, commit/rollback.
- `specialization-dispatch`: dimensions, ISA, alignment, distributions, portfolio plans.
- `hardware-codegen`: SIMD, unroll, prefetch, compiler/codegen variants.
- `operator-pipeline`: hierarchical traversal and work reuse.
- `lifetime-realization`: realization frequency, validity, invalidation, retirement, and placement.

## Admission Rule

Add or promote a grammar family only when attribution shows one of:

- at least 10% marginal regional cost,
- at least 15% critical-path contribution,
- at least 15% physical-byte share with plausible reuse,
- or a measured interaction that increases useful work per fetched byte.

Require a plausible regional ceiling of at least 3%, or 1% when the region exceeds 40% of total
runtime. Add bounded parameters, deterministic lowering, proof obligations, cost signals, and an
ablation plan with the new rule.
