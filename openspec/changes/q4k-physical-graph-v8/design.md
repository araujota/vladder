# Design: Q4_K Physical Execution Graph V8

The graph is built from the regenerated E1 baseline compiled with the pinned Clang and
native target. `objdump -dSlC` provides assembly/source provenance, debug LLVM IR provides
source/IR provenance, and a register RAW DAG provides a deliberately approximate static
dependency model. Dynamic execution weights account for output groups, blocks, and
sub-blocks. Resource nodes record live ranges, stack references, execution resources, and
explicitly absent conceptual operations.

The graph does not claim a cycle-accurate model. Memory dependencies, loop recurrences,
and the llvm-mca full-function estimate remain separately qualified.
