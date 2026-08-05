## Why

vLadder's implementation graphs and physical evidence are language-independent, but its automatic
source closure and strongest proof chain currently end at C/C++. Rust is a high-value systems
target because rustc exposes MIR and LLVM IR, while Rust ownership, panic, drop, layout, and unsafe
contracts make an LLVM-only adapter unsound as a source-equivalence claim.

## What Changes

- Introduce a versioned language-adapter protocol for build capture, semantic extraction, source
  regeneration, proof, and physical evidence.
- Add a Rust adapter that captures Cargo/rustc identity, extracts selected source, MIR, LLVM IR,
  assembly, effects, and information flow.
- Add a bounded R1 grammar for safe, monomorphic, allocation-free scalar/slice reductions and
  transforms with explicit panic and overflow contracts.
- Regenerate native Rust candidates, prove the admitted MIR semantic model with Z3, validate local
  LLVM refinement with Alive2, execute differential tests, and benchmark in one Rust harness.
- Evaluate the complete workflow against a pinned, manageable open-source Rust systems project.

## Non-Claims

The adapter does not claim arbitrary Rust equivalence, stable MIR syntax across toolchains, proof
of unsafe contracts, custom Drop behavior, async runtimes, FFI, atomics, or external protocols.
Those are classified as explicit adapters while local supported regions remain actionable.
