# Learned Search Prior v0

vLadder Prior v0 ranks already enumerated grammar actions. It does not generate code, establish
legality, prove equivalence, predict authoritative runtime, or promote a source replacement.

```text
SemanticFlowGraph v2 + structured action + hardware + workload
                              |
                    calibrated search priority
                              |
              ordinary vLadder proof and measurement gates
```

## Canonical Workflow

```bash
vladder prior init --out prior.yaml
vladder prior run --manifest prior.yaml --out-dir prior-out
```

Read `prior-out/prior-summary.json` first. Its independent states answer:

1. Was the experience dataset valid?
2. Was a model trained?
3. Did counterfactual shadow evaluation complete?
4. Did the corpus meet the production evidence gate?
5. Was any live search actually pruned?

The bundled manifest generates controlled Grade C fixtures. It validates mechanics and can never
satisfy the production physical-evidence threshold. Only non-synthetic Grade A/B benchmark or
composition observations count toward that threshold.

## Dataset

The immutable experience store contains semantic roots, structured candidate actions, concrete
hardware/workload-conditioned realizations, and append-only proof, compilation, differential,
benchmark, counter, and composition observations.

The primary model input withholds source-language identity. Provenance retains language for audits,
language holdouts, and domain-shift evaluation. Project paths and frontend-specific node IDs do not
define semantic identity. The graph canonicalizer is an identity aid, not an equivalence proof.

Use root, project, language, hardware, and temporal holdouts. Candidate-level random splitting is
prohibited because candidates from one semantic root are correlated.

The training boundary is intentionally open to future grammar growth. Canonical identity captures
every non-provenance typed node and edge field, including previously unknown relations,
lifetime/authority metadata, protocol annotations, and family-specific attributes. Structured
actions carry `family`, `family_version`, ordered `primitives`, nested `parameters`, and namespaced
`extensions`. Hardware and workload descriptors are open mappings. Stable canonical outcome
classes remain fixed so grammar expansion does not fragment labels.

```bash
vladder prior template --out training-template.yaml
vladder prior materialize --manifest training-template.yaml --store experience
vladder prior ingest --manifest experience-bundle.yaml --store experience
vladder prior validate --store experience
vladder prior split --store experience --method project --out split.json
```

Prior datasets remain local by default. `prior-summary.json` exposes an optional canonical training
contribution stage and its durable consent state, but always records that no network action was
performed. Before contribution, the agent must run `vladder consent show`, ask for an explicit
opt-in or opt-out when the training scope is unknown, and honor a saved opt-out across sessions.
Only a separately reviewed source-free training bundle may be sent; local experience stores and
canonical graphs are not uploaded as arbitrary artifacts.

## Pilot Model

v0 implements a deterministic bootstrapped linear ensemble over hashed pooled graph, action,
hardware, workload, lifetime, and authority features. It has applicability, pairwise ranking,
proof-risk, and ordinal outcome heads. Calibration uses held-out roots, ensemble disagreement,
semantic graph distance, and a conformal residual summary.

This deliberately small backend validates the data and authority boundaries before introducing a
12-30M parameter heterogeneous relational graph transformer. Training that larger model is gated on
at least 2,500 roots, 20 projects, 3 languages, 2 hardware targets, and 25,000 non-synthetic Grade
A/B physical observations. Meeting the size gate makes the corpus eligible for model evaluation;
it does not automatically authorize budgeted production search.

## Search Safety

Every selection retains the baseline. Between 10% and 50% of the non-baseline budget is reserved
for uncertain or underrepresented legal candidates when the budget permits. Unseen hardware,
out-of-distribution graphs, or excessive ensemble uncertainty cause abstention and exhaustive or
existing-heuristic fallback.

```bash
vladder prior train --store experience --split split.json --out-dir model
vladder prior recommend --model model/prior-model.json --store experience \
  --root-id ROOT --out recommendation.json
vladder prior select --recommendation recommendation.json --store experience \
  --root-id ROOT --budget 12 --out decision.json
vladder prior evaluate --model model/prior-model.json --store experience \
  --split split.json --partition test --out shadow.json
vladder prior evaluate-matrix --store experience --out-dir generalization
```

Enable pruning only after shadow replay demonstrates winner recall at the declared budget, low
regret, calibration, project holdout behavior, and safe abstention. Preserve an exploration reserve
after deployment so the prior cannot permanently hide unfamiliar grammar families.

## Claims

Allowed claims concern ranking, counterfactual measurement reduction, winner survival, and
abstention. Do not claim that the model proved equivalence, predicted an authoritative runtime,
made a candidate production-safe, or established cross-project performance from controlled data.

The deterministic division of authority remains: grammar defines bounded possibilities; Z3,
Alive2, protocol checks, and differential oracles establish the proof envelope; physical hardware
ranks verified realizations; vLadder promotion policy decides what may be retained.
