## Architecture

The authoritative path is:

```text
compiler/source capture
  -> SemanticFlowGraph v2 root
  -> contract inference and unresolved-fact set
  -> lazy family applicability decisions
  -> lazy finite parameter-domain expansion
  -> deterministic legality/canonicalization
  -> EXPAND / DEFER / PRUNE policy decision
  -> concrete source/IR candidates
  -> compile + proof + assembly identity
  -> optional composition and source realization
  -> v3 branch/observation trace
```

`ExecutableSearchEngine` owns this path. Specialist grammars register adapters rather than being
invoked indirectly through a string route. An adapter reports independent capability stages and
must provide a finite parameter domain before it can claim exhaustive coverage.

## Lazy Expansion

The engine never requires a grammar to materialize its Cartesian product. Every partial state has
a stable node identity, parent identity, applied action, depth, remaining action domains, and
terminal disposition. Deterministic impossibility is rejected before policy evaluation;
semantically canonical duplicate states are memoized; only uncertain economic value is delegated
to a pruning policy. Exhaustive shadow mode replaces the learned policy with `EXPAND` and is the
authority for useful-descendant supervision.

The policy contract is `EXPAND`, `DEFER`, or `PRUNE`. Baselines, unknown grammars, out-of-distribution
roots, high-uncertainty decisions, and a configured exploration reserve cannot be pruned. A live
prune is an operational budget decision and is never reused as negative training authority.

Live policies use a persistent JSON-lines process protocol. The root graph and contract are
registered once, then each partial or terminal semantic state is queried before descendant
expansion or expensive source/proof/compile materialization. Protocol failure,
OOD, low confidence, an unknown response, or a learned contract-blocked prediction fails open.
Only deterministic legality code may establish semantic impossibility.

Every policy request includes the complete ancestor action path. This preserves input parity with
v3 training examples: a composition decision may depend on the grammar actions that created the
partial state even when its current canonical semantic graph is otherwise identical.

Automatic source capture produces one dispatch root rather than selecting the first matching
family. Each registered family is independently classified. Soundly impossible families are closed
before policy evaluation; applicable and contract-incomplete families become real lazy children,
and only an expanded child instantiates its family grammar. The v3 family path is therefore the
same path observed by the live oracle rather than a reporting-only wrapper.

Selected-build C++ semantic capture stops after AST/IR effects, region boundaries, and eligibility
proof. Schedule-specific source, syntax checks, candidate IR, Z3 partition evidence, and composed
translation-unit assembly are materialized only for actions that survive policy evaluation.
Regional action evidence is memoized so terminal compositions do not repeat it.

## Negative Authority

A family branch is soundly closed only when a registered predicate proves that required semantic
features are absent or a mandatory contract is contradicted. Missing information is not
inapplicability and remains `KEEP_UNCERTAIN`. A fully enumerated finite family with no useful
terminal receives complete-tree authority through the existing v3 bottom-up labeler.

Every v3 branch records whether it was a learned-policy decision surface, deterministic closure,
canonical memoization, or compatibility wrapper. Model training and pruning evaluation include
only learned-policy surfaces; the other classes remain auditable without inflating model results.

## Contracts

Common contract inference is conservative. It may prove facts from typed signatures, compiler
effects, constants, dominance, and explicit guards. It may not infer aliasing, mutation absence,
floating-point tolerance, ownership, or external behavior from a workload trace. Missing facts are
named and attached to the exact family branch.

For C++, a compilation database makes the Clang-selected definition range authoritative. The
lexical extractor is only a fallback and must ignore comments and all literal forms when matching
braces. Runtime-sized spans and pointer-plus-extent regions are represented as such; a finite proof
window is never reported as a semantic maximum. Stable compaction distinguishes rejection based on
input extent from rejection based on selected output extent. When source types do not prove
disjointness, a candidate may introduce an exact range guard only if the overlapping path executes
the baseline operation order.

Corpus and agent workflows may identify an overloaded definition by a source line inside its
Clang-emitted range. Mangled symbols remain the strongest explicit selector, but a recorded source
location closes overload selection without requiring an agent to parse diagnostic output. Search
fingerprints and C++ capture caches include this selector. Family-stratified campaign manifests
deduplicate source/function identities before held-project training and retain the exact compile
command index and source location used for capture.

Closure has two executable levels. `proof_unit_executable` means a generated bounded helper reached
compile, proof, and assembly dispositions. `replacement_ready` additionally requires complete
reconstruction of the compiler-selected owning definition. Reports retain the old
`source_executable` field only as a compatibility alias explicitly scoped to a proof unit.

Bounded dataflow search exposes structural choices such as mask construction, stable scan/scatter,
transactional publication, and fused packing before concrete terminal realizations. These partial
states are policy surfaces and v3 useful-descendant labels propagate through them. A flat list of
opaque terminal implementations is insufficient training evidence.

## Caching And Parallelism

Compilation and proof cache keys include semantic graph hash, contract hash, grammar hash,
candidate source/IR hash, compiler identity, target identity, and proof policy. Parallel workers
write immutable content-addressed entries and the coordinator emits lineage in deterministic order.
The coordinator also emits a schema-validated v3 bundle and progress record as each root finishes,
so campaign interruption does not discard completed supervision.

Successful and failed compiler dispositions are distinct. A reproducible compiler rejection is a
resolved invalid terminal and may train a negative under an otherwise exhaustive subtree. Tool
unavailability, crashes, or unresolved symbol identity remain uncertain. Compile failures are not
persisted because transient resource failures must be retried.

## Initial Closure Classes

1. Canonical bounded expressions, maps, loops, and reductions.
2. Ordered prefix/suffix reductions with preserved early termination.
3. Stable compaction, exact codecs, AoS multi-reductions, and bounded state deltas.
4. Versioned retained-cache and lifetime plans with finite invalidation matrices.
5. Cross-TU compositions of definition-visible pure/local summaries.
6. Bounded ownership shells with caller-owned storage and no-growth guards.
7. Exact fixed-width bit-popcount reductions, including Rust borrowed-byte wrappers.

Concurrency, GPU orchestration, and external protocols are enumerable only from explicit finite
protocol or device manifests; source recognition alone never supplies proof authority.
