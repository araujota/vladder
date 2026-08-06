# Canonical Multilanguage Extraction V1

## Why

Rust, Zig, and Julia currently reach the shared `SemanticFlowGraph v2`, but their source
frontends recognize almost exclusively an exact byte-equality reduction. C recognizes six
additional bounded loop families, so the language-neutral grammar is stranded behind uneven
source capture.

## What Changes

- Introduce one canonical bounded-region model shared by Rust, Zig, and Julia.
- Recognize exact reductions, pointwise maps, guarded maps, stencils, scans, recurrences, and
  bounded indirect-memory traversals.
- Corroborate source classification with each compiler's typed or lowered representation.
- Preserve language-specific ownership, panic, safety, world-age, GC, and ABI facts as typed
  obligations and provenance rather than new semantic node kinds.
- Separate semantic capture from executable candidate lowering in every support report.

## Non-Goals

- Arbitrary source-language parsing or equivalence.
- Generic Rust protocol, Zig allocator/error-union, or Julia GC/task equivalence.
- Claiming candidate-generation parity when only semantic extraction is closed.
