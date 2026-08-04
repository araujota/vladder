# Change: Operator Verification V3

## Why

Fusion and state can preserve final arrays while violating intermediate outputs,
state transitions, memory ordering, numerical policy, or sequence behavior.
V2's scalar schema proofs and output comparison are insufficient.

## What Changes

- Add structural legality over shapes, regions, state, effects, and memory order.
- Add multi-output and transition-system SMT encodings.
- Add explicit floating-point equivalence/tolerance classes.
- Add stateful sequence and adversarial differential testing.
- Add one modeled C++20 SPSC ring and memory-order litmus/stress verification.

## Success

No candidate reaches ranking without structural admission and contract-specific
proof/testing. Counterexamples name the output, state field, event/token index,
and violated invariant.
