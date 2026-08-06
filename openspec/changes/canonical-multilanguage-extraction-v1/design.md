# Design

## Shared Boundary

Each frontend maps a selected native function to `CanonicalBoundedRegion`. The model records the
family, canonical operation, loop shape, element type, input/output roles, state topology,
neighbor offsets, indirect stride, and exactness contract. It contains no language syntax.

The model lowers to the existing `SemanticFlowGraph v2` vocabulary. Frontend facts are attached
as `SemanticObligation.language_binding` and source/compiler provenance.

## Compiler Corroboration

- Rust: selected source plus emitted, typed MIR and LLVM IR.
- Zig: compiler-analyzed wrapper/module plus emitted LLVM IR and assembly under the captured
  safety mode.
- Julia: one concrete method specialization, lowered IR, typed SSA IR, LLVM IR, world identity,
  inferred effects, and steady-state allocation probe.

This follows the supported compiler surfaces rather than a source-only approximation: rustc
documents `--emit=mir,llvm-ir`, MIR is a typed CFG used for code generation, and Julia documents
method-specific `code_lowered`, `code_typed`, `code_llvm`, and `code_native` reflection. Zig is
pinned to the locally recorded compiler version and its `build-obj` LLVM/assembly emission
interface because that interface is version-sensitive.

Research references:

- https://doc.rust-lang.org/stable/rustc/command-line-arguments.html
- https://rustc-dev-guide.rust-lang.org/mir/index.html
- https://docs.julialang.org/en/v1/base/reflection/
- https://docs.julialang.org/en/v1/devdocs/ssair/

Source classification proposes a canonical family. Compiler evidence must contain the expected
memory, control, and arithmetic structure; otherwise capture fails closed with a
`compiler-shape-mismatch` boundary.

## Capability Semantics

`status: supported` means meaningful semantic capture and local effect closure. Candidate
generation, proof, benchmark, and source rewrite remain independent capabilities. The existing
exact byte-reduction lowerers remain executable. Other newly captured families report
`candidate_generation.actual: false` until a matching native lowerer and proof unit exist.

## Language Boundaries

Rust borrow/panic/Drop/unsafe semantics, Zig safety/error/defer semantics, and Julia
specialization/world/GC semantics are obligations. They do not create parallel graph node kinds.
External protocols remain explicit adapters.
