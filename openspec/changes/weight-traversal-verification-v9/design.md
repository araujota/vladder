# Design: Stateful Execution Verification V9

The exact track composes structural graph checks, E1 contract checks, deterministic simulation,
per-sequence completion-state comparison, and binary provenance. Schedule timestamps may differ;
prompt and decode token counts may not. Speculative nodes are represented for future exact
verification, but no speculative plan is legal in this change. The report explicitly avoids a
claim that llama.cpp GEMV and GEMM accumulation orders are bitwise interchangeable.
