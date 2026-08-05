## 1. Shared IR And Contracts

- [x] 1.1 Add capacity, scan, compaction, codec, projection, commit/rollback, and tile nodes to SemanticFlowGraph v2.
- [x] 1.2 Implement deterministic bounded-dataflow contracts and graph hashing.
- [x] 1.3 Keep source-language constructs in typed bindings rather than new language-specific graph vocabularies.

## 2. Grammar And Lowering

- [x] 2.1 Implement predicate-mask-stable-compaction realizations and output modes.
- [x] 2.2 Implement exact fixed-width codec realizations.
- [x] 2.3 Implement bounded stateful delta/commit/rollback realizations.
- [x] 2.4 Implement AoS projection with fused multi-reduction.
- [x] 2.5 Implement deterministic 4x4 packed-block realizations and proof-class separation.
- [x] 2.6 Add native C++20 emitters and guarded ISA fallbacks for every promoted terminal.

## 3. C++ Closure And Verification

- [x] 3.1 Recognize spans, contiguous views, trivial records, and no-growth vector output contracts.
- [x] 3.2 Emit explicit capacity, allocation, exception, alias, and lifetime obligations.
- [x] 3.3 Generate Z3 sequence/bitvector/state proofs and source-binding evidence.
- [x] 3.4 Differentially execute status, extent, ordered outputs, state, and packed bytes.

## 4. Product And Acceptance

- [x] 4.1 Add `vladder dataflow coverage|graph|emit|verify|audit` commands.
- [x] 4.2 Add a no-write NeuralFusion manifest and tracked-source integrity audit.
- [x] 4.3 Validate the four rc10 sample functions without changing NeuralFusion.
- [x] 4.4 Update README and skill guidance with closure recipes and proof boundaries.
- [x] 4.5 Run strict OpenSpec validation, full tests, grammar validation, package audit, and local skill refresh.
