## 1. Research And Boundary Audit

- [x] 1.1 Audit current C/C++, Rust, Zig, and Julia closure gaps.
- [x] 1.2 Research LLVM effects/MemorySSA/Attributor, Rust MIR cleanup, Zig error/defer, Julia escape analysis, and Alive2 scope.
- [x] 1.3 Define the finite summary lattice and search-space separation.

## 2. Shared Semantic Closure

- [x] 2.1 Implement typed effect footprints, call relations, function summaries, and deterministic hashing.
- [x] 2.2 Implement SCC-aware system graph composition and bounded monotone fixpoint.
- [x] 2.3 Implement finite ownership/protocol envelopes and language-neutral applicability checks.
- [x] 2.4 Emit typed proof obligations and local opaque-boundary dispositions.

## 3. Frontend Bindings

- [x] 3.1 Bind C/C++ LLVM attributes, direct helpers, ABI channels, ownership, unwind, atomics, and volatile effects.
- [x] 3.2 Bind Rust MIR ownership, drop, panic, allocation, dispatch, async, FFI, and atomic facts.
- [x] 3.3 Bind Zig slice, error/defer, allocator, aggregate, atomic, volatile, async, and FFI facts.
- [x] 3.4 Bind Julia typed-specialization, escape, allocation, bounds, task, global, atomic, and ccall facts.

## 4. System Workflow

- [x] 4.1 Add a manifest-driven system closure command and schema.
- [x] 4.2 Prove summary joins, protocol guards, and closed-subgraph isolation.
- [x] 4.3 Confirm that protocol summaries do not enlarge candidate enumeration.

## 5. Validation And Release

- [x] 5.1 Add shared fixtures for helper composition, no-growth ownership, tagged exits, recursion, finite dispatch, and opaque callbacks.
- [x] 5.2 Re-run upstream multilingual probes and NeuralFusion no-write acceptance.
- [x] 5.3 Publish a per-language residual-boundary matrix.
- [x] 5.4 Update README, skill, references, capability registry, schemas, and installation checks.
- [x] 5.5 Run focused/full tests, lint, strict OpenSpec validation, and strict doctor.
