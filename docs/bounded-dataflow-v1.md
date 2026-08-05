# Bounded Variable-Output Dataflow

`bounded-dataflow-v1` extends vLadder from scalar reductions to bounded C++ regions whose
observable result includes an output sequence, exact extent, packed representation, or state
transition. It remains one language-neutral SemanticFlowGraph v2 vocabulary. `std::span`,
`std::vector`, exception behavior, and native ABI details are typed obligations at the C++
boundary, not parallel semantic node kinds.

## Research Basis

- LLVM defines masked compress-store as consecutive storage of enabled lanes, which is the native
  realization needed by stable value compaction on supporting targets:
  <https://llvm.org/docs/LangRef.html#llvm-masked-compressstore-intrinsics>.
- Clang exposes target builtins for masked compress stores; vLadder still emits a checked ISA
  dispatch and scalar fallback rather than turning target availability into a deployment guess:
  <https://clang.llvm.org/docs/LanguageExtensions.html>.
- Prefix sums provide stable destination offsets for selected elements. The grammar uses this
  structure as a semantic primitive, independently of whether a terminal materializes the prefix:
  <https://www.cs.cmu.edu/~scandal/papers/CMU-CS-90-190.html>.
- LLVM's loop vectorizer documents legality and profitability limits around control flow and
  memory, so compare/compact/state publication is modeled above instruction selection rather than
  assumed to follow from a compiler flag: <https://llvm.org/docs/Vectorizers.html>.
- The C++ standard's vector capacity rules establish when reallocation occurs, but capacity alone
  does not prove no-throw construction, trivial destruction, aliases, or owning-wrapper behavior:
  <https://eel.is/c++draft/vector.capacity>.
- Alive2 is applicable to local LLVM refinement. Variable-length output protocols and owning C++
  state require bounded sequence/state obligations and application adapters instead:
  <https://users.cs.utah.edu/~regehr/alive2-pldi21.pdf>.

## Supported Families

| Family | Executable realizations | Exact observables |
|---|---|---|
| Predicate/stable compaction | scalar, fused, mask/prefix, guarded AVX2, guarded AVX-512 | status, extent, stable indices, values, untouched output on all-or-nothing failure |
| Fixed-width codec | field pack, fused word pack, coalesced envelope | field bits, endian order, packed word |
| Stateful delta | staged, transactional, mask/transactional | ordered delta, next state, commit/rollback |
| AoS multi-reduction | repeated scans, fused pass, blocked pass | all projected counters and totals |
| Quantized 4x4 block | scalar reference, fused, packed-lane | encoded bytes, decoded identity, or bounded quality as separate contracts |

Every terminal has a deterministic SemanticFlowGraph derivation, native C++20 emitter, Z3 proof
obligations, and compiled differential runner. Fixed codec helpers also receive a local Alive2
check. This is not an Alive2 proof of an owning wrapper.

## Bounded C++ Closure

Automatic no-growth closure requires all of the following:

1. Borrowed contiguous input and caller-owned contiguous output.
2. A pre-write proof that `required_extent <= available_capacity`.
3. Trivially copyable and trivially destructible output elements.
4. No throwing construction or helper call in the isolated region.
5. Declared input/output aliasing.
6. Exact success, failure, extent, order, and state observables.

`reserve()` by itself is not enough. A vector that may grow, a nontrivial element, an allocator,
or an owning return remains an adapter boundary. The agent can still isolate a pointer/span proof
unit and separately verify the wrapper precondition and postcondition.

## Commands

```bash
vladder dataflow coverage
vladder dataflow graph \
  --contract examples/dataflow/compaction-contract.json \
  --target mask-prefix-stable --out /tmp/compaction-graph.json
vladder dataflow verify \
  --contract examples/dataflow/compaction-contract.json \
  --target guarded-avx2-compaction --out-dir /tmp/compaction-proof
```

Read `bounded-dataflow-workflow.json` as an emitted local candidate and proof envelope. It records
`production_promotion: false`. Physical promotion still requires a same-executable application
adapter, complete project observables, confidence intervals, and a source rewrite matching the
proved candidate.

For a repository acceptance audit:

```bash
cd /path/to/project
vladder dataflow audit \
  --manifest /path/to/vladder/examples/dataflow/neuralfusion-sample-audit.yaml \
  --out-dir /tmp/vladder-dataflow-audit
```

The audit hashes all tracked source before and after and reports `source_changed` if they differ.
It classifies semantic archetypes and adapter obligations; it does not emit a production patch or
claim a speedup.

## Deferred Classes

- Batched geometry requires explicit floating-point order, NaN, determinism, and layout contracts.
- Incremental dependency invalidation belongs to the lifetime/protocol grammar because graph
  identity, revision ordering, and publication are the correctness boundary.
- Allocating containers, callbacks, coroutines, drivers, sockets, GPU queues, and concurrent
  publication require finite protocol adapters over their actual observables.

