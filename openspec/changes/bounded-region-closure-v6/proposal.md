# Bounded C/C++ Region Closure

## Why

vLadder captures compiled C++ effects but still treats noncanonical C ABIs, aggregate returns,
function-returning loops, definition-visible helpers, and no-growth container writes as generic
adapter failures. Several are finite representation problems, not external protocols. Keeping them
opaque prevents the executable grammar from reaching otherwise bounded information flow.

## What Changes

- Add a language-neutral `RegionClosureGraph` for typed live-ins, scalar or aggregate live-outs,
  exit selectors, helper summaries, and ownership/capacity projections.
- Bind C and C++ ABI lowering to the graph, including register aggregates and `sret` storage.
- Normalize local multi-exit regions into explicit exit-tag/value channels at the IR model level.
- Admit direct, definition-visible, local-effect helpers through exact call-preserving summaries;
  require inlining or a stronger relation before transformations cross a helper.
- Admit no-growth writes to trivially destructible contiguous containers under an explicit
  capacity guard and unchanged allocator/ownership state.
- Generate proof obligations and executable scheduling candidates for the bounded classes while
  retaining fail-closed protocol boundaries.

## Impact

The C/C++ frontends gain substantially broader semantic closure without claiming arbitrary C++
equivalence. Existing expression, dataflow, lifetime, LLVM, Alive2, and physical-ranking layers are
unchanged and consume the new closure graph as another semantic boundary.
