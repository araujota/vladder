# Systems Code Design Quick Reference

Read the complete repository guide at `docs/designing-systems-code-for-vladder.md` when working in
the vLadder source tree. This packaged reference gives the attending agent the invariant design
rules needed when only the installed skill is available.

## Preferred Architecture

Keep an idiomatic ownership/protocol shell around a closed semantic region:

```text
owning shell
  -> checked bounds, capacity, versions, ownership, and dispatch
  -> borrowed or finite-state semantic region
  -> explicit status, extent, output, or candidate state
  -> commit/publication boundary
  -> application workload and complete observable oracle
```

Do not replace RAII, safe ownership, `Drop`, error unions, or Julia safety with raw C-style code.
Isolate the information transformation beneath those mechanisms and prove each boundary at its
actual scope.

## Shapes That Close Well

- bounded arithmetic, reductions, scans, recurrences, stencils, codecs, and compaction;
- borrowed contiguous inputs plus caller-owned bounded outputs;
- explicit output capacity and exact written extent;
- trivial aggregates with every live field in the observable contract;
- direct helpers whose exact definitions are available to build closure;
- finite old-state/input to output/next-state transitions;
- no-growth container writes under a dominating capacity guard; and
- versioned derived state with complete invalidators and fallback.

## Shapes That Need a Separate Boundary

- allocation and nontrivial ownership;
- destructor, exception, panic-recovery, `defer`, or finalizer protocols;
- callbacks, virtual dispatch, coroutines, tasks, and open plugin sets;
- atomic publication, reclamation, and general concurrent protocols;
- syscalls, drivers, remote services, storage, network, and presentation;
- dynamic Julia worlds or dispatch and unresolved Rust/Zig/C++ generics;
- device orchestration beyond a declared finite resource protocol; and
- undefined behavior or data races.

These boundaries do not block closed neighboring regions, lifetime analysis, attribution, or
physical benchmarking.

## Enums

Enums are not categorically unsupported. A finite tag with explicit representation is a good
bit-vector and control-flow value. Require:

- explicit underlying/tag width;
- valid-value and malformed-tag policy;
- exhaustive branching with deliberate invalid/default behavior;
- separate masks for independent flags;
- no unchecked invalid discriminants; and
- no dependence on niche, padding, or compiler object layout at wire or ABI boundaries.

Keep nontrivial variant payload ownership outside local arithmetic proof units. Decode raw bytes
into a validated tag before the semantic kernel.

## Agent Rules

1. Freeze source, compiler, build, target, workload, and contract.
2. Attribute before adding or selecting a grammar family.
3. Name authority, observables, lifetimes, invalidators, ownership, and external actors.
4. Read capability vectors; `workflow_completed` is not semantic closure or promotion.
5. Run cross-TU closure before declaring a definition-visible helper external.
6. Separate allocation/preparation, closed computation, and commit when semantics permit.
7. Preserve exact failure ordering, cleanup, aliasing, overflow, and floating-point behavior.
8. Use protocol models as legality constraints, not extra implementation candidates.
9. Prove only the encoded scope and use complete differential observables.
10. Promote only after same-executable physical and application-level confirmation.

Never add `restrict`, `unsafe`, unchecked indexing, `@inbounds`, `noexcept`, fast-math, cache
retention, or a weaker memory order without proving the corresponding precondition and observable
contract.
