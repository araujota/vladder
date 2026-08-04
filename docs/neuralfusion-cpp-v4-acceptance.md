# NeuralFusion Bounded C++ Closure Acceptance

## Scope

This is a non-applying acceptance benchmark of `bounded-cpp-regions-v4` against the existing
46-region NeuralFusion critical-path manifest. It is not an optimization or performance result.
The run used each region's exact production `compile_commands.json` entry and selected mangled
symbol where supplied.

Artifact: `/tmp/vladder-neuralfusion-v4-acceptance-final/cpp-audit.json`

NeuralFusion revision: `04047a50e1634894c4d11b1860c361ef221c482a`

Worktree-status fingerprint before and after:
`d5fc1b083d3c63e563cfdfe5dd4b1e5da5d8fd267e1443545fa736acaf885cff`

## Capability Results

| Capability | Actual regions | Meaning |
|---|---:|---|
| Semantic capture | 43/46 | Concrete AST, ABI, LLVM effects, and information flow captured |
| Isolation | 12/46 | A concrete whole-function or lambda proof symbol was emitted |
| Local proof | 12/46 | Identity refinement artifact passed |
| Candidate generation | 8/46 | The typed loop schedule grammar emitted candidates |
| Source emission | 8/46 | Deterministic compiling repository-source candidates exist |
| Benchmark | 0/46 | No application workload adapter was supplied |
| Protocol equivalence | 0/46 | No owning/external whole-function protocol was proved |

The run emitted 12 passing proof units: eight noinline lambda capsules and four build-specific
whole-function units. It emitted 16 candidate variants. Every variant had:

- `SOURCE_CONTRACT_PROVED` schedule status;
- passing capsule and repository-source compilation;
- `physical_candidate_alive2: NOT_RUN`;
- `application_performed: false`.

All 12 materialized regions passed source-integrity checks. Predicted and actual isolation counts
matched, so there were no capsule compilation, symbol extraction, or identity-proof failures.

## Domain Distribution

| Domain | Regions captured | Locally proved | Candidate-bearing |
|---|---:|---:|---:|
| OpenUSD | 6 | 0 | 0 |
| GPU execution | 7 | 1 | 1 |
| UDP | 9 | 6 | 3 |
| Client cache | 7 | 4 | 3 |
| Redraw | 6 | 1 | 1 |
| Presentation | 8 | 0 | 0 |

Three manifest entries remained unresolved at function-selection/extraction, accounting for the
difference between 43 captured definitions and 46 requested regions.

## Materialized Regions

Whole local proof units were emitted for UDP validation, UDP decode, UDP cache handoff, and the
client-cache identity state transition. Lambda proof units and source candidates were emitted for
GPU work generation, three UDP paths, three client-cache paths, and redraw work selection.

These outcomes do not prove their owning wrappers. The state-transition identity unit does not
prove a nonidentity class-state rewrite; it remains contract-bounded on an explicit state
projection and invariant.

## Rejected Local Shapes

Across discovered source loops, the closure analysis recorded:

| Blocker | Occurrences |
|---|---:|
| Unmodeled helper/external call | 30 |
| Capacity/ownership mutation | 11 |
| Escaping control | 11 |
| Object state outside an admitted local-state boundary | 6 |

These counts overlap. They explain why OpenUSD and presentation paths remain useful for
attribution and lifetime/placement analysis but do not automatically become local proof units.

## Categorical Protocol Boundary

The selected functions retained 39 external API/callback, 36 exception/destructor, 34
ownership/allocation, and four concurrency/memory-order protocol scopes. Those numbers are
region counts and overlap.

Such scopes make generic whole-function C++ equivalence unavailable because the authoritative
state and observables are not closed in local LLVM IR. The reports therefore state the evidence,
blocked claim, required adapter, next workflow, and permitted continuation. This does not block:

- independently closed C++ regions;
- ordinary C/LLVM superoptimization;
- hardware attribution and application benchmarking;
- lifetime and placement synthesis;
- explicitly modeled state or external-protocol verification.

## Comparison With v3

v3 reported 15 semantically accepted definitions and no transformation-ready definitions. v4
materialized 12 proved units and source candidates in eight regions. Its old-style accepted count
is 12 rather than 15 because v4 rejects loops with unresolved calls, capacity mutation, or
escaping control from automatic capsule closure. That lower legacy count is intentional; the new
capability vector exposes the larger useful result without weakening proof boundaries.

## Conclusion

v4 decisively closes automatic proof-unit materialization and bounded schedule-source generation
for explicitly supported C++ region classes. It does not close arbitrary C++ ingestion, generic
workload construction, or owning/external protocol equivalence. NeuralFusion demonstrates both
sides of that boundary on production translation units without requiring application changes.
