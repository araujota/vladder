## Why

`bounded-cpp-regions-v3` distinguishes local compiled information flow from ownership and external
protocols, but only the legacy float loop has an executable isolation and source-lowering path.
Consequently, broader C++ regions can be analyzed but cannot become proof units or verified source
candidates. At the same time, reporting every nonlocal C++ method as one undifferentiated adapter
failure obscures local optimization opportunities inside otherwise non-isolatable protocols.

## What Changes

- Add a closure taxonomy that separately reports semantic capture, automatic isolation, candidate
  generation, local proof, benchmark readiness, source rewrite readiness, and external protocol
  scope.
- Materialize whole-function LLVM proof units for local typed functions, aggregate returns, and
  finite object-state methods whose compiled effects remain local.
- Materialize bounded loop capsules as immediately invoked, reference-capturing noinline lambdas so
  local C++ types remain in their owning translation unit while Clang emits a separate proof symbol.
- Generate guarded loop-schedule source candidates for typed loops. The physical build enables the
  Clang scheduling hint; the proof build suppresses it and must be LLVM-identical to the baseline
  capsule.
- Emit Z3 schedule obligations, Alive2 or canonical-IR evidence, source-range provenance, compiler
  evidence, and explicit benchmark-harness requirements.
- Replace categorical `adapter_required` reporting with verbose scoped dispositions that explain
  what is locally optimizable, what requires a contract, and what cannot be automatically proved.
- Validate capability coverage against NeuralFusion without applying candidates or running its full
  optimization workflows.

## Impact

Pure byte parsers, aggregate-result helpers, typed borrowed loops, local state transitions, and
bounded loops inside allocating wrappers become automatically isolatable. Typed loop scheduling
becomes automatically source-lowerable and locally proofable. Arbitrary RAII, exceptions,
concurrency, callbacks, syscalls, Vulkan, and OpenUSD semantics remain outside generic equivalence,
but no longer hide independently isolatable local regions.
