# Change: Information-Flow Superoptimization

## Motivation

The current SiliconTune implementation is a useful outer shell but still relies
on source-level recognizers and hand-written candidate templates. It does not
yet comprehend the invariant information-flow shape of a function, search a
formal grammar of equivalent realizations, or lift the selected realization back
to C from a semantic graph.

This change closes that conceptual gap.

## Goal

Build a staged information-flow superoptimizer:

```text
C source
-> LLVM IR
-> target function slice
-> canonical information-flow graph
-> flow-shape classification
-> equality/synthesis grammar search
-> proof and benchmark admission
-> hardware-cost extraction
-> readable C reconstruction
```

## Non-Goals

- Global optimality over all possible C/LLVM/machine-code programs.
- Whole-program optimization.
- Repairing undefined behavior.
- Cross-architecture generalization.
- Replacing Clang/LLVM optimization globally.

## Success Criteria

- Every optimized result names its grammar, proof policy, hardware target, and
  search budget.
- The system can explain the flow shape of each corpus kernel.
- Candidate generation is driven by canonical graph/grammar rules, not only
  regex source templates.
- The corpus is rerun and reports whether the graph-superoptimization path
  improves over the current outer shell.
- At least the current 25-kernel corpus remains regression-free.

## Expected Outcome

SiliconTune should progress from:

```text
"this source looks like clamp; try clamp templates"
```

to:

```text
"this function is a pointwise saturating projection; within the select/mask/minmax
grammar and this target cost model, this realization is cheapest"
```
