## Context

- ProGraML uses directed attributed multigraphs over control, data, and call relations and reports
  cross-language LLVM results: <https://arxiv.org/abs/2003.10536>.
- Ansor combines a bounded hierarchical space with evolutionary search and a learned cost model:
  <https://www.usenix.org/conference/osdi20/presentation/zheng>.
- TpuGraphs treats graph, configuration, and measured runtime as one record:
  <https://arxiv.org/abs/2308.13490>.
- Ithemal demonstrates microarchitecture-conditioned learned throughput estimation:
  <https://arxiv.org/abs/1808.07412>.
- Deep ensembles and conformal calibration motivate uncertainty and abstention rather than one
  uncalibrated score: <https://arxiv.org/abs/1612.01474> and
  <https://arxiv.org/abs/2107.07511>.

## Decisions

### 1. The model is subordinate to grammar, proof, and hardware

The prior sees already enumerated structured actions and recommends evaluation order. It cannot
create preconditions, alter contracts, mark equivalence, suppress the baseline, promote source, or
replace clean physical measurement.

### 2. Semantic root is the grouping and identity boundary

Root identity excludes project path and source language but includes normalized semantic graph,
contract, and observable boundary. Provenance retains language for auditing. Candidates from one
root never cross train/calibration/test groups.

### 3. Immutable normalized experience records

One semantic root owns grammar dispositions and structured candidate realizations. Proof,
compilation, binary identity, local benchmark, and composition results are append-only observations
with content hashes and quality grades. Grade D evidence cannot train physical ranking.

### 4. Safe baseline before deep graph learning

v0 implements deterministic hashed pooled graph features and a bootstrapped linear pairwise
ensemble. This establishes data correctness, ranking metrics, uncertainty, and integration without
adding a heavyweight runtime dependency. A relational graph-transformer backend is an explicit
interface and future implementation gate after the minimum corpus exists.

### 5. Uncertainty combines ensemble disagreement and graph distance

Calibration uses held-out roots. Recommendation abstains when categorical graph distance exceeds
the calibrated threshold, hardware capabilities are unseen, model/schema identities differ, or
ensemble disagreement exceeds policy. Abstention invokes current exhaustive/heuristic search.

### 6. Budget policy has hard safety invariants

The baseline is always selected. Ten to twenty percent of remaining budget is reserved for
deterministic random, underrepresented-family, and high-uncertainty candidates. A budget too small
for these invariants fails closed.

### 7. Acceptance is separated into infrastructure and model scale

Workflow acceptance can pass on a pilot corpus. Production-model acceptance remains
`insufficient_dataset` until the declared root/project/language/hardware/measurement thresholds are
met. Reports expose both states and cannot collapse them into one successful command status.

### 8. Grammar vocabulary is open while outcome authority is stable

Canonical graph v1 includes every non-provenance typed node and edge field in identity and feature
inventory. Actions use versioned family, primitive, parameter, and namespaced-extension descriptors.
The stored normalized graph permits future recanonicalization, and models abstain on an unseen
canonicalizer schema. Semantic and physical outcome classes remain stable so a new grammar family
does not create incomparable labels or acquire new proof authority through an extension payload.

## Risks

- Synthetic generators can leak family identity into features.
- Near-duplicate roots can leak across projects or languages.
- Sparse winners can cause overconfident regression predictions.
- Historical reports can omit observables or contain incomparable timings.
- Feedback loops can starve new grammar families.

## Validation

Use cross-language equivalent graphs, project/root/hardware holdouts, intentionally leaking splits,
invalid labels, low-quality physical observations, unseen node/family/hardware fixtures, baseline
and exploration invariants, deterministic retraining, winner-recall/regret metrics, and shadow
replay where the model cannot affect executed candidates.
