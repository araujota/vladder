# Verified C++ Kernel Extraction

## Confirmed Gap

The original common frontend was textual and C-only. It rejected `.cpp` before compilation,
assumed one unmangled function name, and could not retain overload resolution, template
instantiation, exception behavior, object lifetime, or production compiler flags. Project-level
tests could validate manually written C++ replacements, but that was not direct LLVM refinement
of the production implementation.

`bounded-cpp-regions-v2` closes the useful bounded part of this gap. It does not claim to solve
general C++ equivalence.

## Research Basis

- Clang compilation databases record the working directory, source file, and either a structured
  argument array or shell command needed to reproduce one translation-unit parse:
  <https://clang.llvm.org/docs/JSONCompilationDatabase.html>.
- Clang's AST represents resolved C++ syntax and semantics, and its JSON dump exposes concrete
  declarations, source ranges, parameter types, and mangled names:
  <https://clang.llvm.org/docs/IntroductionToTheClangAST.html>.
- LLVM exception handling introduces `invoke`, landing pads, personality functions, and unwind
  edges; these are protocol semantics, not ordinary local expression edges:
  <https://llvm.org/docs/ExceptionHandling.html>.
- LLVM object lifetime affects whether memory access is defined, and pointer association affects
  legal access and optimization assumptions: <https://llvm.org/docs/LangRef.html>.
- Alive2 is an LLVM translation validator and explicitly does not support interprocedural
  transformations. A local kernel proof must not be reported as proof of an owning C++ protocol:
  <https://github.com/AliveToolkit/alive2>.
- Clang's thread-safety analysis is intra-procedural and documents limitations around constructors
  and destructors: <https://clang.llvm.org/docs/ThreadSafetyAnalysis.html>.
- Clang lifetime analysis gains precision from explicit owner/pointer contracts and documents
  limitations for mixed ownership models: <https://clang.llvm.org/docs/LifetimeSafety.html>.

## Automatic Boundary

The selected definition must be concrete, `noexcept`, and contain one loop admitted by
`bounded-regions-v1`. The first release accepts:

- `void f(float *, const float *, size_t) noexcept`;
- `void f(std::span<float>, std::span<const float>) noexcept`;
- `void f(std::vector<float> &, const std::vector<float> &) noexcept` as borrowed stable storage;
- state-independent methods with those parameters;
- concrete template specializations with those parameters.

For view adapters, the defined input domain includes `dst.size() >= src.size()`, stable live
storage for the call, and baseline alias behavior. A supported method may not use `this`.

## Artifacts And Proof

`vladder cpp isolate` emits:

- `target.ast.json` and `selected-function.ast.json`;
- `target.production.ll` and `target.normalized.ll`;
- `isolated-kernel.c` and its automatic support analysis;
- `adapter-contract.json` and `adapter-extents.smt2`;
- `regenerated.cpp` and `replacement-body.inc`;
- `provenance.json` with source, compile-command, AST, IR, kernel, and regenerated-source hashes.

Isolation proves the adapter's bounded extent mapping and establishes the semantic bridge. It is
classified `kernel_isolated_adapter_proved`. `vladder cpp optimize` then runs each isolated
candidate through structural, Z3, memory, Alive2, differential, and physical gates. A promoted
candidate is lifted into `optimized.cpp` and classified `kernel_proved_adapter_bounded` only when
the winner and regenerated source pass.

## Adapter Boundary

The frontend fails closed for owning allocation, local nontrivial RAII, moves, exceptions,
object state, atomics, synchronization, callbacks, virtual/indirect calls, Vulkan/OpenUSD calls,
unsupported containers, noncontiguous layouts, multi-loop regions, ambiguous overloads, templates
without a concrete symbol, and ambiguous compile commands.

Those regions can still use vLadder attribution, lifetime synthesis, abstract Z3 obligations,
measurement, and project-level realization. They cannot use the local C++ proof classification
until the named adapter isolates a bounded computational kernel.
