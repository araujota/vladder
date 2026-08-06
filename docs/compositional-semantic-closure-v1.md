# Compositional Semantic Closure V1

vLadder now maps selected functions into a deterministic `SystemFlowGraph` before asking which
implementation candidates to search. The graph composes finite call and protocol summaries while
keeping ordinary candidate generation inside attributed computational regions.

## Why This Does Not Explode Search

An effect summary is a legality constraint, not a candidate. Each call receives one finite
footprint over memory regions, allocation, cleanup, unwind, synchronization, atomics, volatile
access, publication, invalidation, external I/O, callbacks, nondeterminism, and termination.
Composition is monotone set union over the direct call graph and converges at a bounded fixpoint.

Protocol envelopes add zero candidate dimensions. They either:

- close after every declared guard is proved;
- require a call-preserving boundary; or
- remain an opaque local boundary.

Only a separately attributed computational grammar can add implementation alternatives.

## Workflow

Every C, C++, Rust, Zig, and Julia inspection artifact now contains a
`compositional_summary`. Compose those artifacts directly:

```yaml
system: packet-path
reports:
  - out/parse/cpp-support.json
  - out/compact/rust-support.json
  - out/checksum/automatic-support.json
```

```bash
vladder system closure --manifest system.yaml --out-dir system-closure
vladder schema validate --kind system-closure \
  --artifact system-closure/system-closure-report.json
```

Read in this order:

1. `boundary_matrix`: closure and transitive effects for each function.
2. `boundary_summary`: grouped unresolved contracts and next actions.
3. `system_graph.components`: independently closed search scopes.
4. `proof`: Z3 summary-join and candidate-cardinality obligations.
5. `protocol_validation`: missing applicability guards.

`candidate_generation_performed: false` is intentional. Run an attributed executable grammar only
inside a closed component after composition.

## Finite Envelopes

The first registry covers borrowed contiguous views, checked no-growth append, aggregate results,
tagged ordinary exits, trivial cleanup, scoped allocation, and versioned single-writer
publication. Construct recognition is only an envelope candidate. Closure requires all listed
guards and the declared proof method.

## Language Bindings

| Language | Decisively closable | Finite protocol required | Necessary external boundary |
|---|---|---|---|
| C | direct definitions, LLVM memory effects, first-order ABI | atomics, allocation scopes | open function pointers, syscalls, volatile device behavior |
| C++ | spans, trivial aggregates, no-growth output, direct helpers | RAII, exceptions, finite virtual targets, publication | open callbacks and undeclared object/third-party protocols |
| Rust | borrowed slices, monomorphized MIR helpers | `Drop`, panic cleanup, guarded `Vec`, finite trait targets | unsafe/FFI/async runtime semantics without contracts |
| Zig | slices, tagged/error exits, finite `defer` cleanup | allocators and success/failure retirement | open FFI/async/volatile/callback behavior |
| Julia | one typed specialization, isbits values, inferred direct invokes | GC escape/retention and captured-world mutation | dynamic dispatch, tasks, globals, `ccall`, future worlds |

The language syntax is provenance. All rows bind to the same effect footprint and protocol
vocabulary.

## Proof Boundary

Alive2 remains local. A call-preserving helper relation is bound by compiler attributes,
definition hashes, or a protocol proof. Transforming across the call requires inlining or a
functional relation proof. Arbitrary callbacks and third-party APIs cannot be inferred from local
IR; they stay explicit while neighboring closed components continue through synthesis.
