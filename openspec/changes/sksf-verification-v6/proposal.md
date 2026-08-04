# Change: SKSF Layered Verification V6

## Why

Kernel-internal layout, memory, accumulation, and dispatch rewrites exceed what one proof
engine can soundly and tractably validate.

## What Changes

- Define fail-closed structural, representation, SMT/LLVM, differential, complex, model,
  and stateful verification layers.
- Preserve exact and tolerance tracks separately.
- Treat LLM source reconstruction as untrusted.

## Success

No candidate advances to ranking with an unsupported obligation or a failed output/state
comparison.
