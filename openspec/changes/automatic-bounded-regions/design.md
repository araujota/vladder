## Context

The canonical optimizer already compiles extracted source, constructs LLVM-backed flow graphs,
generates candidates, proves memory obligations, invokes Z3 and Alive2, differentially executes
edge cases, benchmarks physical hardware, and emits proof-gated patches. Its source regeneration
is strongest for pointwise expression DAGs. The new layer must broaden safe regeneration without
claiming arbitrary C++ rewriting.

## Support Matrix

Automatic exact source lowering supports one canonical loop over `size_t i` in a standalone C
function with `void (float *dst, const float *src, size_t n)` ABI:

- pure pointwise maps,
- guarded pointwise maps,
- fixed-radius stencils,
- ordered prefix/running scans,
- bounded scalar recurrences,
- bounded indirect maps.

The loop must have a constant start, monotonic unit increment, a recognized upper-bound form,
braced body, no break/continue/goto/return, no volatile or atomics, and no external calls. The
ordered-unroll lowerer duplicates iterations in original order and retains an exact scalar tail.

## Decisions

### 1. Preserve iteration order

The initial cross-family transformation is ordered unrolling. It reduces loop-control overhead
without reassociating arithmetic or reordering side effects between logical iterations. This
keeps scans and recurrences in the exact track and preserves overlapping source/destination
behavior for admitted bodies.

### 2. Independently parse the source loop

The structural lowerer parses and validates the admitted loop shape independently of the broad
flow classifier. An added region class therefore requires both classifier support and concrete
source parser support.

### 3. Require Alive2 for automatic replacement

Z3 proves the loop partition and memory model; the candidate records a body/substitution hash.
Alive2 validates the complete compiled reference-to-candidate transformation. Differential edge,
overlap, and randomized tests remain mandatory. No automatic patch is promoted without all strict
layers.

### 4. Return adapters as data

Unsupported inputs return a list of adapter kind, reason, required boundary, and next compatible
workflow. They do not silently fall back to compiler-only variants under the automatic command.

## Non-Goals

- Whole-program extraction or arbitrary C++ templates, exceptions, virtual calls, or concurrency.
- Automatic multi-loop fusion or multi-output reconstruction in this first common frontend.
- Reassociation or approximate floating point.
- Applying a candidate that does not meet the declared physical speedup threshold.
