# Zig Regions

Z2 closes native, allocation-free functions over scalars and borrowed byte slices with an exact
registered operation. Capture preserves the original module graph and records the exact Zig version, build files, optimization/safety
mode, source hash, LLVM IR, and assembly. Candidates are native Zig and are never applied
automatically.

Allocator ownership, error unions, `defer`/`errdefer`, volatile or atomic access, inline assembly,
FFI, external effects, and unresolved comptime dependencies require explicit adapters.

Use `--specialization u8` only for a compatible `comptime T: type` signature whose remaining ABI
is a borrowed byte slice and byte scalar. A broader module may have successful compiler capture
while candidate generation remains unavailable; report that as `local_graph_only`.

Optimization benchmarks call the baseline through its original module rather than copying the
selected body. A synthesis-only PASS does not imply that module helpers are closed or that a
physical comparison succeeded; inspect `zig-optimization.json` separately.

Read evidence in this order:

1. `zig-support.json`: selection, source/build identity, graph, and blockers.
2. `candidate.zig`: regenerated source.
3. `schedule.smt2`: parametric all-length schedule theorem and bounded value obligations.
4. `schedule-proof.ll`: canonical Alive2 lowerer validation.
5. Native LLVM/assembly: provenance, not relabeled as direct Alive2 source proof.
6. Differential and randomized same-executable physical evidence.

Only project tests and workload confirmation can promote a local winner.
