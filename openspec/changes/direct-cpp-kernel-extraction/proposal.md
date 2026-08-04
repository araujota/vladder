## Why

vLadder's common automatic frontend rejects every C++ translation unit before semantic
extraction. This forces valuable bounded loops inside otherwise ordinary C++ methods through
manual adapters and prevents the generated implementation from carrying a machine-checkable
connection back to the production source.

## What Changes

- Add a Clang and `compile_commands.json` based C++ frontend.
- Select one concrete function, method, or instantiated template and retain its mangled symbol,
  source range, compiler arguments, AST facts, LLVM IR, and hashes.
- Isolate supported raw-pointer and `std::span<float>` regions into the existing canonical C
  kernel grammar.
- Generate a restricted C++ realization that calls the isolated kernel.
- Prove local kernel refinement with the existing Z3, memory, Alive2, and differential stack,
  while proving adapter extent obligations separately with Z3.
- Return explicit adapter requirements for ownership, exceptions, concurrency, external APIs,
  ambiguous overloads, and unsupported template instantiations.

## Impact

This adds direct C++ support for explicitly bounded computational regions. It does not claim
whole-program or arbitrary-C++ equivalence. RAII protocols, allocation, synchronization,
Vulkan/OpenUSD calls, and object ownership remain project-level adapter obligations.
