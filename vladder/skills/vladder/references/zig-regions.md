# Zig Regions

Z1 closes native, allocation-free functions over scalars and borrowed byte slices with an exact
registered operation. Capture records the exact Zig version, build files, optimization/safety
mode, source hash, LLVM IR, and assembly. Candidates are native Zig and are never applied
automatically.

Allocator ownership, error unions, `defer`/`errdefer`, volatile or atomic access, inline assembly,
FFI, external effects, and unresolved comptime dependencies require explicit adapters.

Read evidence in this order:

1. `zig-support.json`: selection, source/build identity, graph, and blockers.
2. `candidate.zig`: regenerated source.
3. `schedule.smt2`: parametric all-length schedule theorem and bounded value obligations.
4. `schedule-proof.ll`: canonical Alive2 lowerer validation.
5. Native LLVM/assembly: provenance, not relabeled as direct Alive2 source proof.
6. Differential and randomized same-executable physical evidence.

Only project tests and workload confirmation can promote a local winner.
