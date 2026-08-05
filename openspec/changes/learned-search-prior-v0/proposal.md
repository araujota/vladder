## Why

vLadder spends proof, compilation, differential-testing, and physical-benchmark capacity on many
legal candidates that are compiler-identical, dominated, regressions, or below the materiality
floor. Existing artifacts contain useful positive, neutral, negative, invalid, and composition
outcomes, but no immutable learning schema or safe mechanism for using them to order search.

## What Changes

- Add a language-neutral experience schema rooted in `SemanticFlowGraph v2`, structured grammar
  actions, hardware/workload descriptors, proof evidence, and measurement distributions.
- Add canonical root/candidate/observation identities, quality grades, immutable JSONL storage,
  artifact lineage, and leakage-safe group splitting.
- Add pooled graph/action/hardware/workload features and a deterministic ensemble ranking baseline
  with calibrated uncertainty and embedding-distance abstention.
- Add grammar applicability, candidate ranking, outcome, proof-risk, and OOD recommendation data.
- Add shadow evaluation and budgeted selection that always retains the baseline and an exploration
  reserve; the prior never changes legality, proof, physical promotion, or source rewriting.
- Add synthetic multilingual/adversarial fixtures, CLI commands, reports, and acceptance metrics.

## Impact

vLadder gains an auditable search prior and the dataset infrastructure needed for a future
relational graph transformer. The initial release does not claim the production acceptance targets
without 2,500 roots and 25,000 physical measurements. It proves workflow safety and evaluates a
pilot model on leakage-safe fixtures while preserving exhaustive fallback.
