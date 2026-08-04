# Bounded C++ Regions

Use `vladder cpp` before writing a manual adapter. The frontend reads the exact
`compile_commands.json` entry, asks Clang for the semantic AST, selects one concrete mangled
definition, retains production LLVM IR, and attempts verified kernel isolation.

## Commands

```bash
vladder cpp inspect --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-inspect
vladder cpp isolate --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-isolation
vladder cpp optimize --source target.cpp --function transform --compile-commands build --out-dir vladder-cpp-out
```

Add `--symbol _Z...` for overloads and concrete template specializations. Add
`--command-index N` when one source has multiple build configurations. Never choose either by
guessing; inspect `candidate_symbols` and the compilation database.

## Supported Classes

- `noexcept` canonical pointer views;
- `noexcept` dynamic `std::span<float>` writable/read-only views;
- `noexcept` borrowed `std::vector<float>` writable/read-only references with stable storage;
- state-independent methods that do not access `this`;
- concrete source-defined template specializations;
- one exact loop admitted by `bounded-regions-v1`.

The view contract requires a destination at least as large as the source, live stable storage,
and preserved alias behavior. The generated helper retains iteration and expression order.

## Proof Boundary

`kernel_isolated_adapter_proved` means Clang AST legality, compile-command provenance, Z3 extent
mapping, canonical C isolation, and regenerated C++ compilation passed. It does not mean a
transformed candidate passed Alive2.

`kernel_proved_adapter_bounded` means the selected isolated candidate additionally passed Z3,
memory proof, Alive2 LLVM refinement, differential execution, physical promotion, and regenerated
C++ compilation. It proves the local computation under adapter preconditions, not the surrounding
owning protocol.

Fail closed on ownership, allocation, nontrivial RAII, moves, exceptions, object state, virtual or
indirect calls, atomics, synchronization, callbacks, Vulkan/OpenUSD calls, unsupported containers,
or multi-stage stateful regions. Use the emitted adapter kind to define the missing semantic
boundary, then rerun extraction.
