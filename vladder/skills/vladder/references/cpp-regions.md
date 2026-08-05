# Bounded C++ Closure

Use `vladder cpp` before writing a manual adapter. The frontend reads the exact
`compile_commands.json` entry, selects a concrete mangled Clang definition, retains production
LLVM IR, combines source hazards with recursive compiled-effect summaries, and emits a typed
information-flow and proof-decomposition report.

## Commands

```bash
vladder cpp inspect --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-inspect
vladder cpp isolate --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-isolation
vladder cpp synthesize --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-synthesis
vladder cpp optimize --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-out
vladder cpp audit --manifest cpp-regions.yaml --materialize-isolation --out-dir vladder-cpp-audit
vladder cpp adapter --report vladder-cpp-inspect/cpp-support.json --out-dir vladder-cpp-adapter
```

Add `--symbol _Z...` for overloads and concrete template specializations. Add
`--command-index N` when one source has multiple build configurations. Never choose either by
guessing; inspect `candidate_symbols` and the compilation database. Materialized audit may compile
and prove local units, but it performs no optimization, ranking, or source change.

## Modeled Boundaries

- scalar and size values;
- borrowed raw pointers;
- typed or byte `std::span` views;
- borrowed `std::vector<T>&` views, including structured elements;
- aggregate references and compiler-lowered aggregate results;
- callable boundaries as explicit external contracts.

`bounded-cpp-regions-v6` adds one shared `RegionClosureGraph` over these source bindings:

- aggregate results become ordered register or `sret` live-out projections;
- ordinary local returns become tagged CFG exits and are scheduled at whole-function scope;
- definition-visible local helpers become exact call-preserving or inlined relations;
- guarded no-growth appends of trivial values become borrowed output projections.

Read `region-closure.json` and `region-closure-proof/region-closure-proof.json`. Z3 closure of an
exit selector, aggregate projection, or capacity inequality does not prove a transformed function;
each candidate still needs Alive2 where applicable and full differential observables.

The frontend also records object-state use, allocation, exceptions, synchronization, source helper
calls, definition-visible compiled helper summaries, and candidate loop/container subregions.

## Read Capabilities, Not One Boolean

Read `closure.disposition` and each `closure.capabilities` entry independently: semantic capture,
isolation, candidate generation, local proof, benchmark, source rewrite, and protocol equivalence.
`ready` is predicted; `actual` requires emitted evidence. Never infer whole-boundary equivalence
from local isolation or proof.

## Support Tiers

- `canonical_source_transform`: automatic source extraction, local proof, benchmark, and C++
  regeneration are implemented.
- `whole_function_local_ir`: typed local compiled semantics can be emitted as an identity proof
  unit; nonidentity candidates still require a matching grammar.
- `bounded_state_transition`: local effects are captured, but an explicit object-state projection
  and invariant are required.
- `extractable_subregions`: eligible loops can be materialized as noinline lambda proof capsules
  inside a wider owning or external function.
- `external_protocol`: no local proof unit is currently sufficient; use the named adapter.

`vladder cpp isolate` may now succeed for noncanonical local proof units. `cpp synthesize` may emit
guarded unroll-hint source candidates. `cpp optimize` still fails closed with
`benchmark_adapter_required` until the application supplies valid input construction, observable
comparison, and a representative workload.

## Categorical Limits

Generic whole-function proof is unavailable for exception/destructor, allocator/ownership,
concurrency/memory-order, and external API/callback protocols whose state and observables are not
closed in local LLVM IR. The report's `protocol_scopes` must say:

- the evidence and blocked claim;
- whether the boundary is `not_generically_modelable`, selection-resolvable, or contract-bounded;
- the required adapter and next workflow;
- which local, attribution, lifetime, placement, benchmark, and domain-verification workflows
  remain available.

This limitation applies to the protocol claim, not the entire source file. Independently closed
subregions remain eligible. Ordinary local returns can use the tagged whole-function CFG mode;
`goto`, coroutine transfer, volatile/synchronization, local exception behavior,
and ambiguous source ranges reject a capsule rather than weakening its contract.

## Recovery Recipes

- Overload: inspect `candidate_symbols`, select one exact mangled symbol, and preserve its type.
- Template: select an emitted concrete specialization or add a production-equivalent explicit
  instantiation; a template pattern without an emitted symbol is not a proof target.
- Member function: isolate local computation, declare a finite observable state projection, and
  separately prove class-state transitions. `this` identity proof is not a class invariant proof.
- Span/vector/string: keep owning construction outside the proof unit; include size, capacity,
  alias, lifetime, encoding, and mutation effects in the adapter contract.
- Callback/coroutine: isolate only regions whose control and live values close locally. Model
  callback order, suspension, cancellation, exceptions, and destruction through an explicit
  protocol adapter and sequence oracle.
- External GPU/syscall/library orchestration: use local kernel proof plus application output,
  ordering, error, and state-transition evidence. Do not infer external state from local LLVM IR.

The generated adapter bundle is a typed incomplete contract. Its C++ skeleton returns failure until
the observable oracle is implemented. This prevents generation from being confused with proof or
benchmark readiness.

## Proof Boundary

Read `typed-abi.json`, `compiled-effects.json`, `subregions.json`,
`cpp-information-flow.json`, and `proof-envelope.json` before proposing a rewrite.

`kernel_isolated_adapter_proved` means Clang AST legality, compile-command provenance, the
generated boundary proof, canonical C isolation, and regenerated C++ compilation passed. It does
not mean a transformed candidate passed Alive2.

`kernel_proved_adapter_bounded` means the canonical isolated candidate additionally passed Z3,
memory proof, Alive2 LLVM refinement, differential execution, physical promotion, and regenerated
C++ compilation. It proves the local computation under adapter preconditions, not an owning
protocol.

For noncanonical tiers, follow `proof-envelope.json`: Alive2 for local LLVM refinement, Z3 for
boundary/state relations, optional CBMC for explicitly bounded aggregate or exception harnesses,
differential tests for complete observables, and project tests for ownership and external APIs.
Do not infer whole-function equivalence from a subregion proof.

The v6 loop scheduler uses a source-level Clang hint. Its proof build removes the hint and proves
capsule IR identity; Z3 proves loop partition coverage. `physical_candidate_alive2: NOT_RUN` is an
explicit boundary, not a passed Alive2 result. Require differential application checks and
physical measurement before promotion.
