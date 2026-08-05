# Executable Deep Grammar

Use `deep-v2` when the central question is whether an apparent negative result reflects hardware
or an insufficient implementation grammar. The first closed archetype is an exact count of bytes
satisfying either equality or the UTF-8 leading-byte predicate.

## Decision Path

1. Run `vladder deep coverage`. Every claimed terminal must name a shared graph constructor,
   native emitter, proof generator, differential oracle, and physical benchmark binding.
2. Place known scalar and expert implementations in an audit manifest. Run `vladder deep audit`.
3. Read the earliest failed stage:
   - `representation_failure`: source syntax or semantic vocabulary cannot express the expert form.
   - `grammar_failure`: both forms are represented but no rule derivation connects them.
   - `lowering_failure`: the derivation exists but native source does not realize the target graph.
   - `proof_failure`: source exists but exact obligations did not close.
   - `performance_not_promoted`: the form was genuinely tested and did not win.
4. Run `vladder deep rank` to prove, assembly-deduplicate, and measure every reachable terminal.
5. Promote source only under the target ISA contract or a complete runtime guard/fallback.

## Current Closed Vocabulary

- scalar-to-packed-word and scalar-to-SIMD lane decomposition
- packed lane predicates and bit-vector identities
- SIMD comparison masks, movemask/popcount, and bounded byte-lane accumulation
- exact horizontal reduction and periodic no-wrap flush
- unaligned contiguous loads, scalar tails, and footprint coverage
- predicate constants, producer/reduction fusion, and no materialized mask array
- direct ISA-specific and guarded fallback realizations
- explicit one-pass `O(n)` complexity and byte/materialization models

C, C++20, Rust, Zig, and Julia consume the same graph and every terminal has a native emitter.
C/C++ object-bound, alias, ownership, and exception facts; Rust borrow, unsafe, panic, and
monomorphization facts; Zig pointer/safety/target facts; and Julia rooting, bounds-elision, numeric,
and specialization facts are typed proof obligations, not separate semantic operations.

## Proof Envelope

Z3 proves packed-word identities, lane masks, reduction equivalence, traversal and tails, constant
synthesis, dispatch completeness, and the 255-block byte-accumulator no-wrap interval. Alive2
proves compatible vector mask/popcount and compare-to-byte-accumulator cores. Native differential
execution checks all 65,536 singleton value/needle pairs and lengths through vector/tail
boundaries. Physical ranking remains evidence about one target and workload, not semantic proof.

`bounded_optimal_local` means only that every terminal in this finite grammar region had a
non-empty symbol-resolved assembly or LLVM identity and every unique identity was closed and
measured after deduplication. Unresolved identities are measured independently and force
`best_verified_found`. This is not LLVM-wide, algorithm-wide, or global optimality.
