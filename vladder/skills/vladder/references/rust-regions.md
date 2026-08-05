# Rust Regions

## Architectural Rule

Do not translate Rust into a separate semantic vocabulary. The Rust frontend maps source and MIR
into vLadder's common `SemanticFlowGraph`. Ownership, borrows, panic/unwind, `Drop`, unsafe
preconditions, monomorphization, and runtime effects are contracts or proof boundaries attached to
common nodes and edges. Add a language-specific semantic kind only when common value, state,
control, materialization, transfer, and lifetime concepts cannot express it.

## Automatic R1 Envelope

R1 admits one concrete, safe, monomorphic, allocation-free function over primitives, arrays, and
borrowed slices when its operation is registered in the common grammar. The first executable
operation is an exact byte-equality reduction. vLadder captures the exact Cargo package, target,
profile, features, rustc identity, source hash, MIR, LLVM IR, and assembly.

Fail closed for unsafe contracts, allocation/owning collections, custom destruction, panic
recovery, async/coroutines, atomics or concurrency, FFI, inline assembly, unresolved calls, and
external protocols. A named boundary does not block attribution, lifetime analysis, or a smaller
closed region.

## Proof Chain

1. Source selection and Cargo capture identify one concrete definition and build.
2. MIR confirms the registered information-flow operation and generated schedule shape.
3. Z3 proves the chunk/tail schedule for all valid slice lengths and checks bounded symbolic
   content obligations through the declared proof bound.
4. rustc emits fixed-length source and target LLVM wrappers. Alive2 checks bidirectional local
   refinement. Compatibility normalization may erase unsupported assumptions or metadata only;
   original/normalized hashes and every erased class must be recorded.
5. One native Rust executable runs adversarial differential tests and randomized paired-process
   benchmarks with exact observable hashes.
6. A local winner remains unintegrated until the emitted patch matches the proved source, project
   tests pass, and the attributed project workload improves.

`UNAVAILABLE`, `UNSUPPORTED`, `TIMEOUT`, or failed proof evidence is never promotable under the
exact track.

## Commands

```bash
vladder rust support
vladder rust inspect --manifest-path Cargo.toml --source src/lib.rs --function module::function
vladder rust isolate --manifest-path Cargo.toml --source src/lib.rs --function module::function
vladder rust synthesize --manifest-path Cargo.toml --source src/lib.rs --function module::function
vladder rust optimize --manifest-path Cargo.toml --source src/lib.rs --function module::function
vladder rust audit --manifest rust-regions.yaml
```

Use `vladder workflow init --kind rust` for the canonical resumable agent workflow.
