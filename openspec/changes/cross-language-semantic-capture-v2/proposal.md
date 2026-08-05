## Why

RC11 exposes a shared SemanticFlowGraph and native deep-grammar emitters, but upstream evaluation
found four correctness and coverage failures: source-token false positives, empty hot-code
fingerprints presented as exhaustive physical coverage, Zig capture detached from its module graph,
and Julia capture tied to one hard-coded byte-count invocation. The bounded-dataflow grammar also
emits only C++, leaving the shared semantics non-executable in C, Zig, and Julia.

## What Changes

- Replace ambiguous source substring recognition with boundary-aware semantic evidence.
- Require a non-empty, provenance-bearing physical identity before assembly deduplication or a
  bounded-optimality classification.
- Capture Zig through its native module graph and specialize only declared bounded signatures.
- Capture Julia through its project/module/method world without executing arbitrary target methods.
- Add native C, Zig, and Julia source emission for all bounded-dataflow grammar terminals.
- Report semantic capture, candidate generation, proof, and physical coverage independently.
- Re-evaluate pinned C, C++, Zig, and Julia examples without writing their source trees.

## Non-Claims

This change does not make arbitrary checksums, allocators, dynamic Julia methods, Zig comptime
programs, owning C++ protocols, or external effects automatically optimizable. Native compiler IR
is provenance; a language-neutral theorem or canonical Alive2 helper is not relabeled as direct
whole-frontend refinement.
