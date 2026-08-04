## Why

`bounded-cpp-regions-v2` reproduces production translation-unit semantics, but it decides
legality from deliberately narrow source-AST rules before inspecting optimized LLVM effects.
Consequently, harmless `std::span<const std::byte>`, aggregate results, inlined validation
helpers, trivial constructors, and compiler-proven no-throw functions are reported as owning or
external protocols. It also reports only whole-function acceptance even when a valuable bounded
region exists inside an owning method.

## What Changes

- Add compiler-derived effect analysis using the selected production symbol and a deterministic
  optimization profile that exposes helper closure and LLVM memory, unwind, allocation, capture,
  and synchronization facts.
- Replace the float-only ABI check with typed descriptors for scalars, pointers, spans, borrowed
  vectors, aggregate references, and compiler-lowered aggregate results.
- Distinguish transform-ready canonical kernels, whole-function local-IR regions, bounded state
  transitions, extractable subregions, and external protocols.
- Mine loop and straight-line bounded subregions from selected C++ definitions and emit live
  boundary, source range, effect, and proof-envelope artifacts.
- Emit compositional proof plans for aggregate ABI mapping, bounded containers, object-state
  projections, and external effects without claiming that Alive2 proves interprocedural C++.
- Add an inspection-matrix runner suitable for broad C++ repositories. NeuralFusion's audited
  critical-path set is an acceptance benchmark only; this change does not optimize or patch it.

## Impact

The C++ frontend will accept materially broader systems code for analysis and local proof planning
while retaining fail-closed source transformation. Existing float-loop optimization remains fully
automatic. New region classes become transform-ready only when a deterministic lowerer and its
proof bridge exist.
