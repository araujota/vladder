## Context

The two independent agent reports agree that vLadder's proof governance is useful but its evidence
surface is fragmented and its recovery path is underspecified. Existing code already captures
Clang AST/IR closure, local candidates, Z3/Alive2 evidence, bootstrap statistics, lifetime graphs,
and hardware manifests. rc6 connects these capabilities rather than weakening their boundaries.

Primary-source basis:

- Clang LibTooling and AST matchers provide source-aware extraction and exact compile-command
  context: <https://clang.llvm.org/docs/Tooling.html> and
  <https://clang.llvm.org/docs/LibASTMatchers.html>.
- Clang dataflow analysis models values, storage locations, and control-flow joins, supporting
  bounded state-projection discovery without implying arbitrary protocol proof:
  <https://clang.llvm.org/docs/DataFlowAnalysisIntro.html>.
- Alive2 is a local LLVM refinement checker and is not an interprocedural or external-protocol
  verifier: <https://github.com/AliveToolkit/alive2>.
- SPIR-V Tools provides validation, optimization, disassembly, and reduction but does not itself
  establish output equivalence: <https://github.com/KhronosGroup/SPIRV-Tools>.
- Vulkan timestamp queries measure device execution subject to query-pool and synchronization
  rules; host wall time cannot substitute for device timestamps:
  <https://registry.khronos.org/vulkan/specs/latest/html/vkspec.html>.
- CUDA kernels and host orchestration have distinct synchronization and memory semantics, so CUDA
  evidence requires a concrete runner and toolchain rather than a generic C++ proof claim:
  <https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html>.

## Decisions

### 1. One evidence state machine

Every workflow emits a `promotion-summary.json` with independent booleans and evidence references
for inspection, semantic capture, candidate generation, proof, paired benchmark, integration,
promotion, and retained production state. A successful command is never synonymous with a useful
or promotable result.

### 2. Queryable lineage and content-addressed resumption

Artifacts form a DAG from source region through extraction, candidate, proof, benchmark, and final
disposition. Stage cache keys include source content, compile command, grammar, contract, workload,
tool versions, and requested operation. Reuse is explicit and never silently changes evidence age.

### 3. Generated adapters are typed incomplete contracts

C++ closure metadata generates a deterministic manifest, benchmark driver skeleton, oracle
skeleton, and agent task. Unresolved observables, state, ownership, callbacks, or protocols appear
as blocking TODOs in JSON and source. Generation is useful progress but cannot make benchmark or
protocol capability `actual`.

### 4. Prove bounded retained-state protocols, scope everything else

rc6 directly models versioned immutable caches and prepare/commit/rollback publication as finite
state transitions. Vulkan, CUDA, OpenUSD, sockets, coroutine schedulers, drivers, and general
concurrency use a generic protocol-plugin interface and explicit observable/runner contracts.
Library names do not enter the core semantic model.

### 5. Physical evidence is paired and overlap aware

The canonical runner randomizes baseline/candidate order by independent process, keeps both modes
in one executable where configured, and bootstraps paired process-level effects. Composition
requires disjoint region identities or a declared nesting/interaction experiment. Arithmetic
addition or multiplication of overlapping speedups is rejected.

### 6. Trace quality gates synthesis

Lifetime traces are evidence of cost and observed reuse, not semantic authority. Coverage is scored
over events, identities, consumers, invalidators, scope instances, and placements. Weak traces
produce `insufficient_attribution` and no candidates; a complete manifest still remains necessary.

### 7. SPIR-V is the portable first GPU proof boundary

The shader workflow compiles, validates, disassembles, and applies bounded SPIR-V optimizer recipes.
Structural validity is not equivalence. Promotion requires an application output oracle and device
timestamp runner. CUDA reuses the same evidence schema but remains adapter-bound when `nvcc` and a
device runner are unavailable.

## Risks

- Generated adapter code could be mistaken for executable proof. Every bundle carries explicit
  blockers and cannot be promoted until the user-supplied hooks are complete.
- Paired command startup noise can dominate tiny kernels. The manifest records sample granularity
  and recommends an in-process harness for short regions.
- SPIR-V optimizer passes may be legal but numerically or protocol observably different. Output
  differential evidence is mandatory and formal equivalence is not claimed.
- Content hashes do not prove that external hardware state is unchanged. Hardware/workload hashes
  remain separate required evidence.

## Validation

Use independent fixtures for C++ overloads, member state, aggregate results, external protocols,
weak lifetime traces, state-protocol counterexamples, paired benchmark order, overlap rejection,
SPIR-V compilation/validation, resumable lineage, and concise summaries. Re-audit selected existing
NeuralFusion reports without changing its source and verify that adapter bundles and dispositions
are useful for representative local, stateful, and external regions.
