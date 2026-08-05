## Why

vLadder's language-neutral information-flow and proof protocol currently has production frontends
for C, C++, and Rust, but no native path for Zig or Julia. Translating either language through a C
capsule would discard Zig safety/error semantics or Julia method-specialization and runtime facts.

## What Changes

- Add bounded Zig and Julia adapters over the existing `SemanticFlowGraph` vocabulary.
- Capture native build/project identity and emitted semantic, LLVM, assembly, and source artifacts.
- Regenerate native-language candidates and bind them to schedule proofs, differential execution,
  LLVM refinement where compatible, and physical ranking.
- Fail closed with explicit adapter boundaries for semantics outside the supported envelopes.
- Add CLI, workflow, diagnostic, installer, package, documentation, skill, and test surfaces.

## Impact

The release gains native support for exact allocation-free byte reductions in Zig and statically
specialized Julia methods. It does not claim arbitrary Zig comptime/error/allocator protocol proof
or arbitrary dynamic Julia/GC/world-state equivalence.
