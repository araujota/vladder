# Julia Regions

J2 closes one concrete, inferred, zero-allocation method specialization over primitive scalars and
dense borrowed arrays. Capture pins Julia, project/manifest/preferences, module, method, tuple
signature, source, world counter, CPU target, inferred effects/allocation, lowered IR, typed IR,
LLVM IR, and native code.

Package capture uses the active project and `Base.require`, then binds `which`, `code_typed`,
`code_llvm`, and `code_native` to the exact tuple signature without invoking an arbitrary target.
Allocation and differential probes run only for operations with a valid generated input model.
Other concrete methods may therefore have compiler capture while remaining `local_graph_only`.

Other methods and later worlds are outside the proof. Dynamic dispatch, unstable return types,
GC-visible allocation, global/method mutation, exceptions, nondeterminism, tasks, `ccall`, and
external effects require adapters. Warm-up and independent processes separate JIT compilation
from steady-state timing.

Read evidence in this order:

1. `julia-support.json`: exact specialization identity and closure.
2. `candidate.jl`: regenerated native method.
3. Candidate typed/LLVM/native recapture and zero-allocation check.
4. Source-derived Z3 schedule theorem and canonical Alive2 lowerer proof.
5. Adversarial differential tests and paired warmed physical ranking.

Never infer generic-function, package, GC protocol, or future-world equivalence from this chain.
