## Context

Zig provides ahead-of-time compilation, explicit safety modes, native source regeneration, and
LLVM/assembly emission. Julia selects methods by concrete argument types, lowers and infers typed
IR, JIT-compiles through LLVM, and exposes lowered, typed, LLVM, and native representations through
reflection. These frontends differ, but their information realization vocabulary does not.

Primary-source basis:

- Zig downloads and installation: <https://ziglang.org/download/> and
  <https://ziglang.org/learn/getting-started/>.
- Zig language reference and compiler artifact emission: <https://ziglang.org/documentation/0.16.0/>.
- Julia reflection (`code_lowered`, `code_typed`, `code_llvm`, `code_native`):
  <https://docs.julialang.org/en/v1/base/reflection/>.
- Julia project and manifest identity: <https://docs.julialang.org/en/v1/manual/code-loading/>.
- Julia type stability, allocation, and bounds behavior:
  <https://docs.julialang.org/en/v1/manual/performance-tips/> and
  <https://docs.julialang.org/en/v1/devdocs/boundscheck/>.
- Julia's semantic LLVM passes: <https://docs.julialang.org/en/v1/devdocs/llvm-passes/>.

## Decisions

### 1. One semantic vocabulary

Both adapters lower inputs, borrows/views, loads, comparisons, reductions, control, materialization,
state, and lifetime into the existing graph. Zig error unions, safety mode, `defer`, allocator use,
and comptime dependencies are obligations/provenance. Julia specialization signatures, world age,
type stability, GC allocation, bounds policy, and dynamic dispatch are obligations/provenance.

### 2. Native semantic capture precedes LLVM

Zig source and compiler diagnostics establish language semantics before LLVM refinement. Julia
lowered and typed IR establish the selected method specialization before LLVM evidence. LLVM alone
does not prove either source-language boundary.

### 3. First envelopes are narrow and exact

Z1 admits allocation-free scalar/array/borrowed-slice loops with no error union, `defer`, unsafe
pointer escape, atomics, volatile I/O, inline assembly, allocator, or external effect. J1 admits one
concrete, type-stable, allocation-free method over primitive scalars and dense borrowed arrays with
no dynamic dispatch, global mutation, task/concurrency behavior, exceptions, `ccall`, or external
effect. Both initially close exact `UInt8` equality reductions.

### 4. Julia evidence is specialization-scoped

Every Julia artifact is keyed by module, method name, exact tuple signature, Julia version, project,
manifest, CPU target, and source hash. The claim does not extend to other methods or future world
states. Candidate ranking runs in independent Julia processes after warm-up to separate compilation
from steady-state execution.

### 5. Proof layers remain explicit

Native candidate source is parsed back into a schedule, then a parametric Z3 theorem proves complete
index coverage and exact reduction. Fixed-bound LLVM units are used for Alive2 when the compiler
emits compatible pure functions. Differential tests and physical ranking remain separate evidence.
Unavailable LLVM refinement cannot be promoted under a strict exact contract.

## Risks

- Zig compiler IR and CLI options evolve; adapter support is pinned by exact compiler identity.
- Julia generated IR depends on method specialization, world state, project preferences, sysimage,
  and CPU target; evidence is nonportable unless those identities match.
- Julia bounds elision or Zig safety changes can alter failure behavior. Candidates preserve the
  captured policy and reject source forms whose safety observables cannot be modeled.
- JIT compilation can contaminate timing. Warm-up and independent process measurements are mandatory.
