## Context

The v3 frontend already captures exact compile commands, Clang AST definitions, LLVM effects,
typed boundaries, object-state use, and candidate source loops. The missing link is an executable
proof unit and deterministic source realization for admitted bounded classes.

Primary-source basis:

- Clang LibTooling and AST matchers support source-aware standalone transformation tools:
  <https://clang.llvm.org/docs/Tooling.html> and <https://clang.llvm.org/docs/LibASTMatchers.html>.
- Clang's refactoring engine separates requirements from source replacements, matching vLadder's
  fail-closed candidate model: <https://clang.llvm.org/docs/RefactoringEngine.html>.
- LLVM CodeExtractor exposes region eligibility plus explicit input/output sets:
  <https://llvm.org/docs/doxygen/classllvm_1_1CodeExtractor.html>.
- Alive2 validates local LLVM refinement but explicitly excludes interprocedural transformations:
  <https://github.com/AliveToolkit/alive2>.
- CBMC checks bounded C/C++ assertions, pointer bounds, overflow, and memory safety when loops and
  environments are explicitly bounded: <https://diffblue.github.io/cbmc/man/cbmc.html>.

## Decisions

### 1. Report a capability vector, not one support boolean

Each selected function reports:

- `semantic_capture`: whether source and compiled effects are understood;
- `isolation`: whether a concrete proof symbol was emitted;
- `candidate_generation`: whether a deterministic grammar applies;
- `local_proof`: whether the candidate proof envelope can be discharged;
- `benchmark`: whether an executable workload adapter exists;
- `source_rewrite`: whether a source candidate and placement map exist;
- `protocol_scope`: what remains outside local equivalence.

The top-level disposition is one of `automatic`, `automatic_with_benchmark_adapter`,
`contract_bounded`, `local_regions_only`, `external_protocol_only`, or `unresolved_selection`.
No disposition blocks unrelated vLadder C, IR, operator, lifetime, or hardware workflows.

### 2. Whole local functions are valid proof units

When the selected LLVM definition is local-effect, no-unwind, and has a modeled ABI, its normalized
function is emitted as a proof unit. Aggregate returns retain the exact compiler-lowered signature;
vLadder does not invent a source layout. Object-state methods retain the exact `this` representation
and additionally require a state-observable contract before a nonidentity rewrite can be promoted.

### 3. Use lambda capsules for bounded nested loops

A loop with a stable source range and no escaping `return`, `goto`, coroutine transfer, inline
assembly, synchronization, or object-state access is replaced in a generated translation unit by
an immediately invoked `[&]` lambda marked `noinline`. This preserves surrounding allocation,
exceptions, and ownership while causing Clang to emit a concrete local function for the loop.

The capsule is a generated proof/benchmark realization. It is not automatically applied to the
repository. A final source patch may retain the capsule or realize the same candidate more
idiomatically after applied-source verification.

### 4. Start with schedule-only typed loop candidates

The first generic typed grammar adds guarded Clang unroll hints with factors 2 and 4. The proof
translation unit defines `VLADDER_PROOF`, suppressing the hint and producing the baseline capsule
IR. The physical translation unit retains the hint. This changes compiler scheduling, not C++
abstract-machine semantics, and follows the existing C loop-hint proof pattern.

No arithmetic rewrite is generated without a typed expression grammar and matching SMT/Alive2
obligation.

### 5. Separate local proof from application benchmarking

Generic C++ input construction is not inferred. A candidate may be locally source/proof ready while
still requiring a project benchmark adapter. `cpp optimize` must not claim a winner without that
adapter. Isolation and synthesis remain useful and reproducible.

### 6. Categorical protocols are verbose, scoped outcomes

Non-isolatable behavior records the semantic reason, authoritative evidence, blocked claim,
permitted continuation, and required adapter. External protocol scope never implies that local
attribution, lifetime optimization, manually contracted kernels, or project measurement must stop.

## Risks

- Lambda capture can change semantics for escaping control flow. Such regions are rejected.
- Macros can make source replacement ambiguous. Candidate compilation and exact source ranges fail
  closed; macro-origin regions remain contract-bound.
- Compiler scheduling hints are not graph-level arithmetic transformations. Reports classify them
  as schedule autotuning, not information-flow invention.
- Identity proof-unit validation does not prove a future candidate. Every candidate retains an
  independent proof status.
- Whole-function LLVM proof cannot establish class invariants or external protocols. Those remain
  explicit promotion obligations.

## Validation

Use independent fixtures for aggregate returns, byte spans, structured loops, allocating wrappers,
finite state methods, escaping control flow, callbacks, synchronization, and external protocols.
Compile every generated capsule with its production command, verify proof-build IR identity, run
the complete suite, validate OpenSpec strictly, and rerun the NeuralFusion acceptance matrix in
non-applying mode.
