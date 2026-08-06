# Canonical Multilanguage Regions

Rust R2, Zig Z3, and Julia J3 map seven bounded source families into one
`canonical-bounded-regions-v1` model:

- exact predicate reduction;
- pointwise map;
- guarded pointwise map;
- stencil;
- ordered scan;
- ordered recurrence;
- constant-stride modulo-extent indirect read.

The canonical model contains family, normalized expression/coefficients, operation, types,
loop/state topology, neighbor offsets, indirect stride, exactness, and input/output roles. It
contains no Rust, Zig, or Julia syntax. Matching a family while changing the expression produces a
different hash.
`canonical-region.json` is deterministic and its `region_hash` must match for semantically
identical native spellings.

## Evidence Boundary

Extraction has two authorities:

1. The selected source recovers operation shape and maps it to the bounded canonical model.
2. Native compiler evidence must corroborate required memory, arithmetic, compare, recurrence,
   or remainder structure.

Rust uses selected MIR plus LLVM. Zig uses a compiler-analyzed wrapper/module plus LLVM. Julia
uses one concrete typed SSA specialization plus LLVM. A missing required signal is
`compiler-shape-mismatch`, not a supported graph.

Borrowing and panic in Rust, safety/error semantics in Zig, and world/specialization/GC semantics
in Julia remain typed obligations and contracts on the shared graph. They are not new node kinds.

## Capability Decision

Read these independently:

1. `semantic_capture.actual`: native compiler artifacts exist.
2. `information_flow.actual` or `closure.actual`: the canonical graph and local effect envelope
   are closed.
3. `candidate_generation.actual`: an executable native lowerer exists for this family.
4. Proof, differential, benchmark, and rewrite capabilities: evidence produced after lowering.

`status: supported` with `candidate_generation.actual: false` is a useful canonical graph, but no
optimization candidate exists. `synthesize` must return `lowerer_required` and zero candidates.
Do not adapt through C or invoke the exact byte-reduction generator.

## Excluded Regions

Multiple unmodeled loops, allocation, dynamic dispatch, unsafe/external effects, concurrency,
ambiguous specializations, and lifecycle protocols remain named boundaries. Isolate a bounded
subregion or use operator, lifetime, or protocol workflows rather than weakening the contract.
