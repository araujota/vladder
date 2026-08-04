# Bounded C++ Closure And Proof Units

## Purpose

`bounded-cpp-regions-v4` expands C++ coverage without claiming arbitrary C++ equivalence. It
distinguishes three jobs that were previously conflated:

1. capture the production translation unit, concrete definition, ABI, and compiled effects;
2. identify the smallest local information-flow or state-transition regions that can be proved;
3. materialize local proof units and bounded source candidates where closure is demonstrated;
4. keep enclosing ownership, exception, concurrency, and external protocols as separate claims.

The frontend therefore may accept a function for automatic decomposition while correctly refusing
to optimize or rewrite it.

## Research Basis

- Clang compilation databases reproduce the working directory and arguments for one translation
  unit: <https://clang.llvm.org/docs/JSONCompilationDatabase.html>.
- Clang's semantic AST retains resolved declarations, source ranges, parameter types, overloads,
  templates, and mangled names: <https://clang.llvm.org/docs/IntroductionToTheClangAST.html>.
- Clang's data-flow framework models facts across all control-flow paths and motivates explicit
  escape and output-pointer handling: <https://clang.llvm.org/docs/DataFlowAnalysisIntro.html>.
- LLVM attributes such as `memory`, `captures`, `nofree`, `nounwind`, `nosync`, `sret`, and
  `initializes` express useful but build-specific boundary facts: <https://llvm.org/docs/LangRef.html>.
- LLVM CodeExtractor documents the live-in/live-out and region-shape problems involved in lifting
  a CFG region into a function: <https://llvm.org/docs/doxygen/classllvm_1_1CodeExtractor.html>.
- Clang AST matchers and refactoring tooling provide semantic source ranges and replacement
  infrastructure without making semantic-equivalence claims:
  <https://clang.llvm.org/docs/LibASTMatchers.html> and
  <https://clang.llvm.org/docs/RefactoringEngine.html>.
- Alive2 validates LLVM transformations but does not support interprocedural transformations:
  <https://github.com/AliveToolkit/alive2>.
- CBMC can check bounded C/C++ memory, pointer, exception, and assertion properties when supplied
  with explicit harness bounds and environmental models: <https://github.com/diffblue/cbmc>.

These sources support a compositional design: local LLVM refinement, explicit boundary and state
proofs, bounded protocol models where practical, and project-level tests for external behavior.

## Commands

```bash
vladder cpp inspect --source target.cpp --function transform --compile-commands build --out-dir inspect
vladder cpp isolate --source target.cpp --function transform --compile-commands build --out-dir isolate
vladder cpp synthesize --source target.cpp --function transform --compile-commands build --out-dir synthesis
vladder cpp optimize --source target.cpp --function transform --compile-commands build --out-dir optimize
vladder cpp audit --manifest cpp-regions.yaml --materialize-isolation --out-dir audit
```

Use `--symbol` for an exact overload or concrete template specialization and `--command-index`
for one exact compilation-database entry. Materialized audit compiles and proves local units but
still records `optimization_performed: false` and `source_changes_performed: false`.

## Typed Boundaries

The semantic ABI recognizes:

- scalar integer, floating-point, boolean, byte, and size values;
- raw borrowed pointers;
- `std::span<T>` including byte and structured element types;
- borrowed `std::vector<T>&` views, distinguished from owning vector values;
- borrowed aggregate references;
- callable boundaries, which remain external until given a call contract;
- aggregate results lowered in registers or through compiler `sret` storage.

Recognition is not proof. The report records the proof model for every boundary and emits the
remaining extent, layout, alias, ownership, and result-correspondence obligations.

## Effect Model

The frontend compiles an optimized effect IR and retains lower-optimization fallback IR so inline
methods and helpers remain discoverable. It summarizes definition-visible direct callees
recursively, while rejecting unresolved or indirect calls from the local-effect envelope. Source
AST evidence remains authoritative for explicit allocation, ownership, object state, exceptions,
atomics, synchronization, inline assembly, and coroutines even when optimization erases them.

Each report includes:

- LLVM memory and function attributes;
- allocation, deallocation, unwind, synchronization, volatile, and global-store evidence;
- internal helper summaries and unresolved calls;
- source calls, constructors, loops, object state, and runtime hazards;
- instruction counts for the selected compiled definition.

## Capability Vector

Do not reduce a report to `supported` or `adapter_required`. Read these independently:

- `semantic_capture`: the selected build, ABI, effects, and information flow were captured;
- `isolation`: a local proof unit was predicted or actually materialized;
- `candidate_generation`: the registered bounded grammar emitted source candidates;
- `local_proof`: the local identity/refinement and typed obligations passed;
- `benchmark`: a representative executable workload is available;
- `source_rewrite`: deterministic repository candidates exist; `application_performed` remains
  false until promotion;
- `protocol_equivalence`: whole-boundary ownership, exception, concurrency, and external behavior.

Each has separate `ready` and `actual` fields. A region can have actual local isolation and proof
while whole-boundary protocol equivalence remains false.

## Closure Dispositions

`canonical_source_transform`
: The original bounded one-loop pointer/span/borrowed-vector path. Extraction, canonical C
  lowering, Z3 boundary proof, Alive2 refinement, benchmarking, and regenerated C++ are available.

`whole_function_local_ir`
: The typed whole function is local and no-unwind in the captured build. Its information flow can
  be emitted immediately as an LLVM proof unit. If no registered grammar matches, the outcome is
  `proof_unit_only`, not an invented optimization.

`bounded_state_transition`
: The compiled effects are local, but the function reads or writes object state. A finite state
  projection and class invariant remain required for nonidentity whole-state rewrites. Eligible
  nested loops may still be isolated independently.

`extractable_subregions`
: One or more bounded loop/container regions are identified inside an owning, allocating,
  exception-capable, or externally interacting function. v4 wraps eligible loops in immediately
  invoked noinline `[&]` lambda capsules, compiles them using the production command, identifies
  the emitted symbol, and proves the local identity unit. Escaping `return`, `goto`, coroutine,
  unresolved macro, volatile, synchronization, and local exception behavior fail closed.

`external_protocol`
: No currently admissible local proof unit exists. The report names the exception, ownership,
  memory-order, ABI, callable, or external protocol adapter that is still required.

Closure dispositions are `automatic`, `automatic_with_benchmark_adapter`, `contract_bounded`,
`proof_unit_only`, `local_regions_only`, `external_protocol_only`, and `unresolved_selection`.
They describe what can happen now rather than treating a whole function as one support bit.

## Bounded Candidate Grammar

For an eligible nested loop, v4 emits guarded Clang unroll hints for factors 2 and 4. The proof
build removes the hint, compiles an identity capsule, and emits a Z3 loop-partition obligation.
The physical candidate is compiled and hashed separately. This is a source scheduling contract,
not an Alive2 proof of the physically unrolled CFG and not evidence of a speedup. Ranking requires
a project benchmark adapter that constructs valid inputs and checks all relevant observables.

The emitter never modifies the repository. It records candidate source, insertion offset,
deterministic hash, compile result, proof class, excluded claims, and `application_performed:
false`.

## Categorical Protocol Scopes

Generic whole-function refinement is not empirically available when correctness depends on state
absent from local IR, including:

- RAII/destructor ordering and allocator ownership;
- exception propagation and cleanup protocols;
- atomics, locks, queues, and C++ memory ordering;
- callbacks, syscalls, Vulkan/OpenUSD, device state, and other external APIs.

Each `protocol_scope` reports evidence, the blocked claim, `automatic_status`, the required
adapter, the next workflow, and what remains available. These are categorical limits on generic
ingestion, not global vLadder failures: local regions, hardware attribution, lifetime/placement
search, and explicitly modeled protocol workflows continue.

## Artifacts

Inspection emits:

- `target.ast.json` and `selected-function.ast.json`;
- production, analysis, and optimized effect LLVM IR;
- `typed-abi.json` and `compiled-effects.json`;
- `subregions.json` and `cpp-information-flow.json`;
- `proof-envelope.json`;
- `cpp-support.json` containing classification and adapter requirements.

Materialized closure additionally emits `cpp-closure.json`, whole-function or lambda proof units,
candidate source and IR, Z3 schedule obligations, source integrity hashes, and explicit benchmark
adapter requirements. Canonical transformation also emits the isolated C kernel, adapter SMT,
regenerated C++, provenance, candidate proof outputs, and benchmark evidence.

## Proof Boundary

Alive2 applies to a selected local LLVM transformation. Z3 discharges generated boundary and
state relations. CBMC is an optional bounded harness route for aggregate/container and exception
models. Differential tests cover complete observables and error paths. Project tests retain
responsibility for owning lifecycles and external protocols.

None of the following implications are valid:

- recognized C++ type implies representation equivalence;
- local optimized IR implies source-level absence of ownership or exceptions;
- isolated loop proof implies whole-function equivalence;
- native compilation implies Vulkan, OpenUSD, socket, callback, or concurrency equivalence;
- accepted support tier implies an automatic source rewrite.

This boundary is the core release guarantee: broader C++ programs receive useful automated
information-flow decomposition and exact missing obligations without overstating formal coverage.
