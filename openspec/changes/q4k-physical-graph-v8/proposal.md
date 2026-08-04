# Change: Q4_K Physical Execution Graph V8

## Why

Source-level Q4_K graphs do not expose machine resource use, instruction dependencies,
or the representation work performed by the active kernel.

## What Changes

- Add `Q4KPhysicalExecutionGraph` below `Q4KKernelGraph`.
- Map source, LLVM IR, optimized assembly, semantic obligations, and resource classes.
- Emit machine-readable JSON and Graphviz provenance artifacts.

## Success

At least 95% of hot-loop instructions are classified and every omission is reported.
