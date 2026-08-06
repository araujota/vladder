# Cross-TU Semantic Closure RC18

## Why

The rc17 C++ frontend can represent bounded local computation, ownership projections, exceptional
control flow, and finite protocols, but it still treats a definition outside the selected
translation unit as opaque. In large C++ systems this makes ordinary project helpers look like
external authorities and prevents otherwise closed regions from reaching executable synthesis.

## What Changes

- Build a deterministic whole-build index from `compile_commands.json` and linked object symbols.
- Materialize persistent, hash-bound function summaries on demand across translation units.
- Construct bounded bidirectional program slices around an attributed seed rather than importing
  an entire program into the candidate search.
- Model ownership construction, borrowing, publication, transfer, retirement, and explicit
  boundaries across the selected slice.
- Prove summary composition, unique definition resolution, effect closure, provenance binding, and
  ownership closure with Z3.
- Preserve unresolved indirect calls, external protocols, driver/runtime behavior, and ambiguous
  ODR definitions as explicit non-crossable boundaries.
- Validate the workflow against NeuralFusion without writing to that repository.

## Non-Goals

- Whole-program C++ equivalence.
- Treating declarations or AST name lookup as evidence of the linker's selected definition.
- Expanding external libraries, arbitrary callbacks, virtual dispatch, syscalls, drivers, or
  concurrency protocols without finite contracts.
- Adding every indexed function to implementation search.

