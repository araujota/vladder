## Why

vLadder's shared information-flow vocabulary is implemented for bounded Rust, Zig, Julia, and
deep C/Rust regions, but legacy C and C++ still emit parallel schemas. Proof obligations are also
stored mainly as free-form strings, preventing machine validation and compositional protocol
reasoning.

## What Changes

- Introduce `semantic-flow-v2` with typed obligations, effects, protocol transitions, and claims.
- Preserve one language-neutral value/flow/lifetime vocabulary while retaining native semantics as
  typed bindings and provenance.
- Make legacy C and bounded C++ emit v2 graphs while retaining compatibility views for existing
  consumers.
- Add native C++, Zig, and Julia emitters, source reconstruction, proof binding, and physical
  harnesses for every terminal in `deep-v2`.
- Require all five native languages to produce the same semantic-shape hash for one realization.

## Non-Claims

This change does not prove arbitrary C++, Zig, or Julia programs. It closes the finite deep-v2
archetype and improves semantic capture; owning protocols, external effects, dynamic worlds, and
whole-application behavior remain explicit proof boundaries.
