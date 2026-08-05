## Context

Rust normally lowers HIR/THIR into MIR, performs MIR optimization and monomorphization, then lowers
MIR to LLVM IR. rustc can emit both MIR and LLVM IR, while Cargo provides machine-readable workspace
metadata and passes additional flags to the final rustc invocation. The textual MIR format warns
that it is toolchain-coupled, so every parser and proof artifact must be keyed by the exact rustc
identity.

Primary-source basis:

- rustc compilation and MIR/LLVM lowering:
  <https://rustc-dev-guide.rust-lang.org/overview.html> and
  <https://rustc-dev-guide.rust-lang.org/backend/lowering-mir.html>.
- rustc emits MIR, LLVM IR, bitcode, and assembly:
  <https://doc.rust-lang.org/rustc/command-line-arguments.html>.
- Cargo metadata and cargo rustc preserve workspace and final-invocation context:
  <https://doc.rust-lang.org/cargo/commands/cargo-metadata.html> and
  <https://doc.rust-lang.org/cargo/commands/cargo-rustc.html>.
- Panic unwinding executes Drop implementations, so panic/drop behavior is source-observable:
  <https://doc.rust-lang.org/reference/panic.html> and
  <https://doc.rust-lang.org/reference/destructors.html>.
- Unsafe Rust introduces caller- and implementation-held contracts absent from ordinary local IR:
  <https://doc.rust-lang.org/nomicon/safe-unsafe-meaning.html>.
- Miri detects many Rust UB classes but is dynamic evidence rather than exhaustive proof:
  <https://github.com/rust-lang/miri>.
- Crux-MIR and Kani demonstrate bit-precise, bounded MIR verification and compositional proof as the
  practical state of the art: <https://arxiv.org/abs/2410.18280> and
  <https://arxiv.org/abs/2607.01504>.

## Decisions

### 1. General language adapters are evidence-producing protocols

Each adapter implements build capture, region resolution, language semantic IR, closure and effect
classification, information-flow lowering, native source emission, proof, and benchmark binding.
The common protocol never assumes LLVM or C source.

The semantic vocabulary is intentionally shared. `Input`, `Load`, `Compare`, `Reduce`,
`StateRead`, `Materialize`, `Transfer`, and lifetime/ownership edges mean the same thing for C,
C++, and Rust. An adapter may attach language-specific provenance and proof obligations, but it
may not introduce a parallel language ontology unless a semantic distinction cannot be expressed
as common graph metadata. Rust borrows, panic/unwind policy, `Drop`, and unsafe preconditions are
therefore contracts on common values, state, control, and lifetime edges rather than a separate
Rust information-flow graph.

### 2. Rust source semantics and LLVM refinement are separate layers

MIR evidence establishes the selected Rust control/data operations and panic policy. The bounded
MIR verifier encodes the admitted operation and candidate schedule over symbolic values. Alive2
then checks local LLVM refinement where the emitted functions can be normalized into compatible
units by erasing unsupported assumptions and optimization metadata. The normalization is hashed
and cannot rewrite executable operations. Neither layer substitutes for the other.

### 3. R1 is strict but production-useful

R1 admits safe, monomorphic, allocation-free functions over scalars, arrays, and borrowed slices.
It accepts structured index loops, ordered reductions, and pointwise transforms with modeled
integer behavior. It rejects or adapter-scopes unsafe, allocation, custom Drop, trait-object calls,
unresolved calls, panic recovery, async, atomics, FFI, inline assembly, and external state.

### 4. MIR parsers are pinned and fail closed

Textual MIR is parsed only for recognized rustc families and recognized operation forms. Unknown
statements, terminators, types, asserts, or unwind behavior prevent proof. Source syntax may assist
location and regeneration but cannot replace MIR semantic confirmation.

### 5. Candidate source is native Rust

The initial grammar emits guarded unroll and accumulator schedules as Rust source, compiles them
with the captured edition/target/profile, runs rustfmt, and records source-to-MIR-to-LLVM lineage.
Generated C is not a production realization.

### 6. Promotion is application-bound

Candidates run in one generated Rust executable with deterministic adversarial differential tests
and randomized baseline/candidate benchmark order. A project result additionally requires the
project's tests and a project-relevant benchmark. Local wins are not application wins.

## Risks

- MIR text changes between rustc versions. Exact toolchain hashes and parser capability checks fail
  closed and make evidence nonportable by default.
- Optimization can inline or erase target functions. Semantic capture uses a dedicated proof build;
  physical ranking uses release compilation and retains separate provenance.
- LLVM IR may encode Rust alias assumptions that source extraction fails to preserve. Candidate
  lowering keeps native references and compares the generated Rust functions rather than translating
  to C pointer ABIs.
- Source-level unrolling can change panic order or integer overflow behavior. Candidates are legal
  only when the declared panic/overflow contract and MIR proof preserve those observables.

## Validation

Use fixtures for scalar reductions, slice transforms, early exit, panic paths, overflow policy,
unsafe blocks, allocation, Drop, unresolved calls, and unsupported MIR. Verify deterministic graph
hashes, source regeneration, candidate compilation, bounded Z3 counterexamples, Alive2 invocation,
differential tests, physical ranking, and project-level negative as well as positive outcomes.
