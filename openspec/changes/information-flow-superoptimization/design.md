# Design: Information-Flow Superoptimization

## Research Basis

The supporting research pass is in:

- `docs/information_flow_superoptimization_research.md`

The design borrows four practical ideas:

- STOKE: low-level search needs performance and correctness objectives.
- Souper: practical LLVM superoptimization works on extracted slices.
- Equality saturation / egg / Tensat: represent equivalent graphs before
  extracting the cheapest realization.
- Polyhedral/Halide-style scheduling: separate information flow from legal
  execution order and hardware schedule.

## Architecture

### Stage 1: Lower To IR

Compile with Clang 20 to normalized LLVM IR using flags that preserve enough
structure for analysis. Store both raw and analysis-normalized IR.

### Stage 2: Extract Semantic Slice

Extract the target function and its output-producing slice:

- loads from inputs
- stores to outputs
- arithmetic/comparison/select operations
- loop phis and induction variables
- guards and boundary conditions
- memory access functions

### Stage 3: Build Information-Flow Graph

Represent the slice as a typed graph:

- value nodes: constants, arguments, loads, operations, phis
- effect nodes: stores and memory ordering constraints
- control predicates
- loop/index domains
- dependence edges

### Stage 4: Classify Flow Shape

Classify kernels into flow families:

- pointwise map
- pointwise guarded/select map
- reduction
- prefix/scan
- stencil/neighborhood
- recurrence
- indirect/strided memory transform
- mixed/unknown

### Stage 5: Canonicalize

Normalize equivalent surface forms into canonical graph forms:

- branches to selects when legal
- compare/select chains to clamp/min/max forms
- exact strength reductions
- reassociation only when exact or explicitly permitted
- loop-index normalization

### Stage 6: Search Grammar

For each flow family, use an explicit grammar:

- algebraic rewrites
- select/mask/minmax rewrites
- vector-lane rewrites
- schedule rewrites: peel, unroll, tile, vectorize
- memory rewrites: alignment assumptions, restrict/no-alias variants

Search modes:

- equality saturation for local graph equivalences
- bounded enumeration for small instruction forms
- polyhedral legality checks for loop schedules
- static cost-guided extraction
- optional empirical reranking

### Stage 7: Verify

Use a tiered correctness policy:

- graph-rule proof for trusted rewrites
- Z3 proof for scalar schemas
- Alive2 for LLVM slice refinement when tractable
- differential testing as a runtime guard

Candidates must report proof strength explicitly.

### Stage 8: Evaluate

Evaluate candidates with:

- `llvm-mca`
- code size and instruction count
- benchmark timing
- optional perf counters
- confidence interval/noise policy

### Stage 9: Lift Back To C

Generate readable C from the selected graph and schedule:

- preserve the original function signature
- emit intrinsics only when selected by the grammar
- emit comments naming preconditions such as no-alias
- preserve source mapping in reports

DeepSeek is an optional, untrusted C reconstruction proposer. It receives the
selected DAG and bounded SMT semantic relation, but is outside the trusted
computing base. Strict JSON responses are screened for forbidden C operations,
compiled, graph-matched, and subjected to SMT/Alive2 and deterministic
differential verification. Verifier diagnostics drive a bounded repair loop.
No proposal bypasses deterministic lifting or admission when credentials or the
provider are unavailable.

## Meaning Of Optimality

`optimal` means:

> minimum selected cost among all candidates reachable by grammar `G` under
> budget `B`, admitted by proof policy `P`, for target hardware `H`.

This must be printed in reports. If the search terminates by budget rather than
saturation, the result is `best-found`, not `optimal`.

## Risks

- E-graph explosion.
- Alive2 timeout/OOM on loop-heavy IR.
- Cost model mismatch with hardware.
- C lifting that produces unreadable or non-portable output.
- Illegal transformations under aliasing or floating-point edge cases.

## Mitigations

- Slice aggressively.
- Use per-family grammars rather than one universal grammar.
- Track exact FP semantics by default.
- Gate alias-dependent rewrites behind explicit preconditions.
- Keep empirical benchmark selection as the final arbiter.
