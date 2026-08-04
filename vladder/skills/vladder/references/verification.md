# Verification

## Evidence Layers

1. Structural legality: ABI, shape, bounds, lifetime, alias, side effects, state ownership.
2. Z3: explicit arithmetic, bit-vector, loop partition, path, and bounded footprint obligations.
3. LLVM refinement: canonical normalized-IR identity when functions are alpha-identical;
   otherwise Alive2 refinement from compiled reference IR to candidate IR.
4. Differential tests: edge, randomized, adversarial, overlap/in-place, and sequence inputs.
5. Integration: final source compilation, project tests, state/tensor/logit outputs, and replay.

All required layers must pass. `unsupported`, `unavailable`, `timeout`, and `unknown` are not
proof successes.

## Proof Scope

Read each SMT file and report its quantifiers, bit widths, bounds, memory model, floating-point
mode, and assumptions. A loop-partition proof does not prove the loop body. A schema proof does not
prove arbitrary C semantics. Differential tests do not generalize beyond tested cases.

Canonical identity is a syntactic proof and must report `alive2_invoked: false`. Alive2 proves
LLVM refinement for the compiled functions and flags used when proof IR differs. Neither path
establishes that an applied source edit is the same candidate unless the final function is checked
against the proof bundle. Use `vladder verify-application` after editing production source.

## C++ Isolation

For `vladder cpp`, separate three claims:

1. Clang AST legality and Z3 adapter proof establish only the declared view, extent, and call
   mapping.
2. Alive2 validates the isolated compiled kernel candidate, not constructors, destructors,
   ownership, publication, synchronization, exceptions, or external APIs.
3. Regenerated C++ compilation and project tests validate integration under the production build.

Do not promote an inspect/isolate result. Require `kernel_proved_adapter_bounded` from the optimize
workflow, a passing `optimized.cpp` realization, unchanged source provenance, and application-level
tests. Owning protocols require CBMC, TLA+, project-specific model checking, or an explicit manual
adapter in addition to the local kernel proof.

## Zero-Trust LLM Use

An LLM may propose or reconstruct C, but its output is untrusted. Compile it, regenerate IR, run
the same Z3 and LLVM-refinement obligations, test it differentially, benchmark it, and reject it
on any failure. Never let an LLM explanation substitute for a proof artifact.
