## Context

The v2 frontend treats source syntax as a proxy for runtime effects. That is too conservative for
C++ because Clang commonly lowers spans to pointer/extent pairs, aggregate returns to `sret`, and
small helpers to ordinary SSA. Conversely, accepting source constructs by name is unsound when an
allocator, destructor, callback, or external API remains observable.

Research basis:

- Clang compilation databases preserve the exact translation-unit command:
  <https://clang.llvm.org/docs/JSONCompilationDatabase.html>.
- Clang dataflow analysis supports all-path reasoning about writes, reads, pointer escape, and
  liveness: <https://clang.llvm.org/docs/DataFlowAnalysisIntro.html>.
- LLVM defines `memory`, `captures`, `nofree`, `nounwind`, `nosync`, `sret`, `writable`, and
  `initializes` as semantic effects and ABI obligations: <https://llvm.org/docs/LangRef.html>.
- LLVM CodeExtractor exposes explicit live inputs and outputs for eligible regions:
  <https://llvm.org/docs/doxygen/classllvm_1_1CodeExtractor.html>.
- Alive2 explicitly excludes interprocedural transformation claims:
  <https://github.com/AliveToolkit/alive2>.
- CBMC supports bounded C/C++ memory, exception, pointer, and assertion proofs, but requires
  explicit harness bounds and external models: <https://github.com/diffblue/cbmc>.

## Decisions

### 1. Compile before final semantic rejection

After selecting one concrete definition, vLadder emits a dedicated `-O2` effect module using the
production semantic flags. The effect module is not ranking code. It exists to expose helper
closure and compiler-established function attributes. Explicit source throws, atomics, inline
assembly, coroutines, and indirect calls remain blockers even if an optimizer happens to remove a
path.

### 2. Use two authorities

The AST remains authoritative for source identity, type spelling, object state, explicit lifetime
operations, source ranges, and rewrite placement. LLVM IR is authoritative for the selected
compiled realization's remaining calls, unwind edges, memory operations, allocation calls,
synchronization operations, and lowered ABI shape. A candidate is accepted only when both views
are compatible.

### 3. Introduce support tiers

- `canonical_source_transform`: existing source extraction, regeneration, and optimization.
- `whole_function_local_ir`: bounded compiled information flow with no remaining external,
  allocation, unwind, synchronization, or indirect-call effect; no generic source rewrite claim.
- `bounded_state_transition`: local compiled work using an explicit object-state projection; Z3 or
  CBMC adapter work remains required.
- `extractable_subregions`: source regions with explicit boundaries that may be isolated without
  claiming the owning function is equivalent.
- `external_protocol`: Vulkan, OpenUSD, syscalls, callbacks, concurrency, allocation protocols, or
  other remaining externally observable effects.

`status`, `accepted`, `transformation_ready`, `proof_classification`, and `claim_boundary` are
reported separately.

### 4. Model types structurally

Typed ABI descriptors cover scalar arithmetic and enum values; raw pointers; dynamic spans;
borrowed vectors; lvalue references; callable parameters; and aggregate results. Unknown source
layout is never invented. Aggregate return acceptance requires compiler evidence such as a direct
scalar return or `sret`; source rewriting additionally requires a generated layout bridge and
proof.

### 5. Infer helper closure from remaining calls

Source helper calls are reported for provenance. A direct call that disappears from the effect IR
is classified `inlined_or_folded`, not external. Remaining LLVM intrinsics are modeled. Remaining
direct calls receive effect summaries when their declarations carry sufficient attributes;
otherwise they are external. Indirect and virtual calls always require a callable contract.

### 6. Mine regions without promising automatic rewriting

The initial miner enumerates loops and branch-bearing compound regions from Clang source ranges,
records local calls and explicit hazards, and classifies candidates conservatively. It emits a
proof envelope containing live-boundary requirements, alias/extent obligations, state projection,
container capacity, and protocol exclusions. A later native LibTooling/CodeExtractor backend may
replace this implementation without changing the schema.

### 7. Normalize aggregate proof ABIs explicitly

Alive2-facing transformations use identical internal signatures. Aggregate results are represented
through explicit output storage in the proof ABI. Z3 proves span extent and non-overlap arithmetic;
CBMC is the preferred bounded verifier for structured adapters where available. Unsupported Alive2
attributes are not silently deleted when they carry semantic meaning.

### 8. Keep transformation readiness fail closed

Only `canonical_source_transform` enters the current optimizer. Other accepted tiers provide
information-flow graphs and proof plans, but `cpp optimize` exits with a typed grammar/lowerer
requirement until an executable lowerer is registered.

## Risks And Mitigations

- Compiler attributes can depend on optimization and whole-program visibility. Reports hash the
  effect command and classify facts as build-specific.
- `nofree` does not mean no local allocation. Allocation call scanning remains required.
- Source and IR regions may not map one-to-one. Subregions are candidates until source/IR
  provenance and adapter proof are complete.
- Aggregate layout and standard-library ABI are implementation-specific. Reports retain target,
  compiler, type spelling, and lowered signature hashes.
- More accepted analysis regions can be mistaken for rewrite support. Separate readiness fields
  and CLI failure codes prevent promotion.

## Validation Strategy

Use independent fixtures for byte spans, integer spans, aggregate results, inlined helpers,
compiler-inferred no-throw functions, structured borrowed views, allocation, object state,
external calls, and nested loops. Run the complete existing suite, strict OpenSpec validation, and
an inspection-only NeuralFusion matrix. Do not benchmark or patch NeuralFusion in this change.
