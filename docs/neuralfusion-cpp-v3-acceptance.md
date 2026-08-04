# NeuralFusion C++ Acceptance Benchmark

## Scope

This is an inspection-only benchmark of `bounded-cpp-regions-v3` against the 46-region
NeuralFusion critical-path matrix previously used to evaluate v2. It is not an optimization run,
proof-coverage claim, or NeuralFusion source change.

- NeuralFusion revision: `04047a50e1634894c4d11b1860c361ef221c482a`
- vLadder package version: `1.0.0rc5`
- C++ support matrix: `bounded-cpp-regions-v3`
- Compiler: Clang 20.1.2
- Audit report SHA-256: `f902b8f5c1b1d5020b05b285ea18c23a9d3cc72c704f9dacec9facba34581cbb`
- Manifest SHA-256: `647f5c7c63da5c2477f18d8f684785040f30de82570cab422198606f5d1a58cf`
- NeuralFusion worktree-status hash before and after: `d5fc1b083d3c63e563cfdfe5dd4b1e5da5d8fd267e1443545fa736acaf885cff`

The three entries without a current selected symbol were retained as unselected extraction
failures. Concrete implementation symbols were selected for overloaded state and Vulkan methods.

## Result

| Domain | Regions | v2 accepted | v3 accepted | Transform ready |
|---|---:|---:|---:|---:|
| OpenUSD ingestion | 8 | 0 | 2 | 0 |
| GPU execution | 7 | 0 | 1 | 0 |
| UDP | 9 | 0 | 6 | 0 |
| Client cache | 8 | 0 | 5 | 0 |
| Redraw | 6 | 0 | 1 | 0 |
| Presentation | 8 | 0 | 0 | 0 |
| **Total** | **46** | **0** | **15** | **0** |

Support-tier distribution:

- `whole_function_local_ir`: 3
- `bounded_state_transition`: 1
- `extractable_subregions`: 11
- `external_protocol`: 28
- `unselected`: 3

The semantic acceptance rate increased from 0% to 32.6%. Automatic proof-and-source-rewrite
coverage remains 0%. This distinction is intentional.

## Newly Accepted Evidence

Whole-function local compiled semantics were captured for:

- `parse_header`
- `parse_sparse_rle_block`
- `parse_showcase_frame_commit`

An explicit bounded state-transition boundary was identified for:

- `SparseP2CacheState::validate`

Candidate local subregions were identified inside:

- direct OpenUSD candidate construction;
- remote-only GPU execution-graph construction;
- UDP send/receive batch loops;
- sparse packet validation and application.

These functions are accepted for information-flow decomposition and compositional proof planning,
not as equivalent regenerated replacements.

## Remaining Boundaries

Across the 46-region matrix, the reports retain these adapter obligations:

- external calls: 39
- exceptions or possible unwind: 36
- ownership or lifetime: 34
- object state: 27
- unsupported ABI details: 11
- memory ordering: 4
- stale or missing function extraction: 3
- source lowerers for newly accepted tiers: 15

Vulkan presentation and native compositor paths correctly remain `external_protocol`; their
correctness includes resource ownership, synchronization, device calls, and lifecycle behavior
that a local LLVM proof cannot establish.

## Interpretation

v3 resolves the diagnostic false-negative problem for several byte parsers, structured results,
state methods, and useful inner regions. The next engineering limitation is no longer basic C++
parsing or type recognition. It is executable lowering plus proof bridges for each explicit region
class: aggregate-result functions, finite object-state transitions, helper-closed byte parsers, and
live-in/live-out subregion extraction.

This benchmark deliberately did not run full vLadder workflows against NeuralFusion, in accordance
with the evaluation constraint.
