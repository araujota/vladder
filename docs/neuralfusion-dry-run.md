# NeuralFusion Release Dry Run

The `vladder-1.0.0rc1` wheel was installed into an isolated environment and its bundled skill was
installed into an isolated agent home. `vladder doctor --strict` and skill validation both passed.

The dry run selected NeuralFusion's compact/sparse remote-only GPU execution graph because prior
application attribution identifies it as a real physical information-flow boundary. The candidate
eliminates an intermediate color allocation traversal, one compositor dispatch, one barrier, and
contractually constant auxiliary outputs. At 1080p this removes 49,766,400 modeled bytes per frame.

## Verification

- Z3 obligations: 7/7 produced the expected result, including two expected mutation
  counterexamples.
- Alive2: 5/5 boundary function pairs verified; no incorrect or failed transformations.
- Regional full-frame semantic parity: passed in every baseline/candidate process.
- Focused execution-graph, sparse Vulkan cache, and formal-proof tests: 3/3 passed.

The proof excludes SPIR-V compiler and Vulkan driver correctness, generic local/HUD composition,
presentation, scanout, and optical output. The optimized path is guarded by the remote-only
contract and preserves the general compositor fallback.

## Measurement

The two-process release smoke reproduced the regional result on the RTX 5080:

| Workload | GPU latency reduction | Host-call latency reduction |
|---|---:|---:|
| 720p full | 53.99% | 25.92% |
| 720p sparse | 54.11% | 25.27% |
| 1080p full | 70.52% | 55.46% |
| 1080p sparse | 74.53% | 51.43% |
| 1440p full | 75.04% | 65.32% |
| 1440p sparse | 79.13% | 66.69% |

The live local UDP-to-software-visible boundary reduced GPU dispatch latency by 69.87%, but the
60 Hz paced end-to-end boundary improved by only 0.52% (95% bootstrap interval 0.49% to 0.54%).
The small client-work submetric regressed by 10.89%, with an interval reaching zero; it is treated
as a statistical smoke-run warning rather than hidden by the larger GPU result.

## Interpretation

This is a valid installed-skill dry run and a fresh confirmation of an actual NeuralFusion code
change already committed on its branch. It is not a new synthesis result. vLadder's generalized C
lowerer cannot faithfully encode this stateful Vulkan graph; the skill correctly routes it through
the specialized graph, proof, and native benchmark harness and labels that support as research.
No NeuralFusion files were modified during this dry run because no new candidate was generated.

Machine-readable details are in `release-validation/neuralfusion-dry-run.json`.
