# Semantic Contracts

## Contract Checklist

Record these fields before search:

- Language and ABI: C dialect or restricted C++20, calling convention, exceptions, `errno`, and
  observable floating-point environment.
- Inputs and outputs: types, shapes, strides, dimensions, valid values, nullability, and ownership.
- Memory: object bounds, pointer provenance, alias sets, alignment, lifetime, mutability, volatile
  access, and allowed overlap or in-place execution.
- Arithmetic: signed/unsigned overflow, shifts, division corner cases, floating-point ordering,
  FMA contraction, reassociation, NaN/infinity/subnormal policy, tolerance, and determinism.
- Effects: I/O, allocation, atomics, locks, callbacks, external calls, global state, and failure
  behavior.
- State and concurrency: initial state, transition invariants, thread ownership, memory order,
  sequence order, commit/rollback, and final state.
- Deployment facts: ISA, dimensions, alignment, topology, and guards/fallbacks.
- Workload: representative and adversarial inputs, distribution, warm/cold cache, latency or
  throughput objective, and regression limits.

## Exactness Classes

- `E1`: Bitwise production equivalence, including operation ordering where observable.
- `E2`: Explicit tolerance equivalence with absolute, relative, and ULP limits. Never call exact.
- Bounded: Exact only within encoded widths, sizes, address regions, or sequence length.
- Distributional: Testing evidence over a declared distribution; never a proof of all inputs.

Prefer E1 for source promotion. Keep tolerance and exact result tracks separate.

## Undefined Behavior

Do not use vLadder to repair existing undefined behavior while optimizing. Establish a defined
reference domain first. Reject candidates that rely on stricter alignment, non-aliasing, overflow,
out-of-bounds access, uninitialized data, invalid shifts, or data races unless the contract and a
guard establish those facts.
