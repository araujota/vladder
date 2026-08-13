# Learned Search Prior v0

vLadder's learned search component is a high-recall branch-survival oracle. It asks whether useful
work may exist below a branch; it does not predict speedup, generate code, establish legality, prove
equivalence, predict authoritative runtime, or promote a source replacement.

```text
SemanticFlowGraph v2 + structured action + hardware + workload
                              |
               conservative branch-survival decision
                              |
              ordinary vLadder proof and measurement gates
```

## Canonical Workflow

```bash
vladder prior init --out prior.yaml
vladder prior run --manifest prior.yaml --out-dir prior-out
```

The executable generator is policy-interleaved rather than rank-after-enumeration. Use
`vladder source-search run` for authoritative shadow trees: the pruning policy is invoked on each
partial or terminal semantic state before descendant expansion or expensive candidate artifacts
are materialized. Deterministic illegality, semantic-state
memoization, and learned budget decisions are recorded as separate authorities. See
[Lazy Executable Search](lazy-executable-search.md).

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

The contribution/training interchange is `vladder-model-training-bundle-v3`. It preserves semantic
roots, search executions, branch parentage and depth, search stage, structured grammar actions,
hardware/workload context, local child-coverage authority, search costs, typed observations, direct
utility, and bottom-up descendant utility. `graph_learning_examples()` exposes one branch example
with its complete ancestor action path, parent/search identity, and the `KEEP`, `KEEP_UNCERTAIN`, `PRUNE_HIGH_CONFIDENCE`, or
`BLOCKED_BY_CONTRACT` target. Legacy v1 and flat v2 bundles are historical validation-only artifacts
and must not be treated as equivalent pruning samples.

Each JSONL example separates `decision_context` from `supervision`. Semantic topology, grammar,
ancestor actions, stage, hardware, and workload are available before a pruning decision.
Observations, coverage, search state, costs, and targets are post-search supervision and MUST NOT be
fed to the encoder. This partition prevents outcome leakage.

Positive utility propagates from a proof-valid, physically distinct realization or stronger retained
terminal outcome to every required ancestor. Proof validity and physical distinctness are separate
observations: a lone proof remains uncertain, and a proved compiler-identical terminal is negative
when completely closed. A branch becomes a negative example only when its complete subtree is exhaustively
represented or a named sound contract, legality, or dominance proof closes it. Absence of a winner
in a partial, heuristic, budget-truncated, or interrupted trace is not a negative label.

```bash
vladder training graph-examples --bundle vladder-model-training-bundle.json \
  --out graph-learning-examples.jsonl
vladder training ingest-model --bundle vladder-model-training-bundle.json --store experience
```

The JSONL path preserves every project/language occurrence. The v0 prior-store compatibility path
deduplicates exact semantic clones because that older store keys roots by semantic identity; use the
JSONL/relational loader for lineage-aware language- and project-holdout training. Use
`vladder training from-search-trace` for full search trees. `from-prior` is a migration path that
emits partial one-level searches and therefore cannot manufacture exhaustive negatives.
Service ingestion independently recomputes direct utility, descendant utility, and survival class;
producer-supplied labels are not trusted.

Large exhaustive trees are transported as validated `full_trace`, `complete_subtree`, and
`partial_snapshot` packets. Complete subtrees retain their external parent identity and remain
authoritative for local descendant labels. Partial snapshots are deliberately non-negative
evidence. Training loaders must consume every item in a campaign record's `bundles` array; silently
reading only the compatibility `bundle` field discards dense-search supervision.

The training boundary is intentionally open to future grammar growth. Canonical identity captures
every non-provenance typed node and edge field, including previously unknown relations,
lifetime/authority metadata, protocol annotations, and family-specific attributes. Structured
actions carry `family`, `family_version`, ordered `primitives`, nested `parameters`, and namespaced
`extensions`. Hardware and workload descriptors are open mappings. Stable canonical outcome
classes remain fixed so grammar expansion does not fragment labels.

Contribution sanitization preserves the standard action coordinates and supports future public
grammar coordinates through `public_training_schema: true` plus typed `training_features`.
Undeclared extension payloads are omitted. This allows grammar growth without a schema migration
while preventing arbitrary source-derived extension data from crossing the privacy boundary.

```bash
vladder prior template --out training-template.yaml
vladder prior materialize --manifest training-template.yaml --store experience
vladder prior ingest --manifest experience-bundle.yaml --store experience
vladder prior validate --store experience
vladder prior split --store experience --method project --out split.json
```

Prior datasets remain local by default. `prior-summary.json` exposes the canonical training
contribution stage and its durable consent state. Unknown or opt-out performs no network action;
opt-in automatically shards and syncs every supported pseudonymized form after each newly completed
prior workflow. Before the first decision, the agent must show the complete notice and local volume
estimate, ask for explicit opt-in or opt-out, and honor the decision across sessions. Only validated
model-training bundles are sent; local experience stores and arbitrary graph/source artifacts are
not uploaded. The v3 bundle is pseudonymized rather than anonymous because normalized topology and
search lineage are included and can fingerprint a distinctive algorithm or search strategy. Source identifiers, paths, user-defined
types and literals are removed, and linked IDs are installation-secret HMACs. Older training
consent does not carry forward across this disclosure change.

## Pilot Model

v0 implements a deterministic bootstrapped linear ensemble over hashed relational graph motifs, action,
hardware, workload, lifetime, and authority features. It has applicability, pairwise ranking,
proof-risk, and ordinal outcome heads. Calibration uses held-out roots, ensemble disagreement,
semantic graph distance, and a conformal residual summary.

This deliberately small backend validates the data and authority boundaries before introducing a
10-30M parameter relational graph model. The v3 interchange retains the raw topology and partial
action lineage that model requires. A branch-survival model is gated on thousands of
useful-descendant paths, exhaustive or soundly closed negatives, action-family diversity, and
root/project/language holdouts. Performance observations are optional because this head predicts
survival rather than speed. Meeting a size gate makes a corpus eligible for held-out replay; live
pruning additionally requires calibrated high-recall shadow evaluation and fail-open deployment.

The reference relational shadow model is trained and served with:

```bash
python scripts/search_pruner.py train \
  --progress campaign/training-v3/training-v3-progress.json \
  --manifest campaign-manifest.json \
  --output pruner-model

python scripts/search_pruner.py serve --model pruner-model/model.pt
```

It consumes branch-level v3 examples, excludes deterministic, canonicalized, and legacy synthetic
decision surfaces that are absent from the live policy interface, and uses the real lazy family and
ancestor action path. Project-held-out replay,
uncertainty/OOD abstention, exploration reserve, and minimum positive-path counts determine live
eligibility.

The RC24 C++-primary evaluation loaded 43,153 deduplicated examples from 770 semantic roots. The
initial 14.2M-parameter model's 19.51% branch reduction missed 41 of 3,254 useful branches and was
rejected. Frozen-corpus ablations then compared a 3.1M relational encoder, independent-seed
ensembles, staged/focal training, frozen encoders, canonical graph-summary trees, embedding plus
tree heads, hard-example objectives, retrieval consensus, and stage-specific risk thresholds.

The selected three-member ensemble uses an upper-confidence score, exact-history and nearest-
neighbor safety checks, family-local OOD rejection, and a 1% exploration reserve. Its maximum
validated policy avoids 1.30% of online replay work at 99.969% useful-descendant recall. Grammar and
candidate recall are 100%; composition recall is 99.950%. A stricter zero-miss policy avoids 1.27%
of replay work. Both remain `shadow_only`; no packaged or live workflow enables them. The result
shows that the existing corpus can support safe selective pruning, but not the intended 70-90%
reduction. Further progress requires targeted cross-project candidate/composition evidence rather
than broader relabeling or more aggressive calibration of these same roots. See
[the validation report](reports/executable-source-search-rc24-validation.md).

## Contextual Best-First Program

RC24 closes the independent hard-pruning experiment. The successor policy answers which legal
sibling to explore first, not which sibling is safe to delete. This follows learning-to-branch work
that imitates an expensive branching oracle on graph state rather than classifying isolated nodes
([Gasse et al., 2019](https://arxiv.org/abs/1906.01629)). Controlled encoder ablations include GIN,
alternating GIN/GAT, and a local-message-passing plus global-attention variant motivated by the GPS
recipe ([Rampasek et al., 2022](https://arxiv.org/abs/2205.12454)).

One `SearchDecision` contains the parent semantic graph, complete prior action sequence, current
grammar state, and every legal sibling action. Post-search distance, useful and retained terminal
counts, subtree cost, and redundancy class are outcome-only supervision. Listwise and pairwise
losses teach retained descendants before useful descendants, short useful paths before long useful
paths, and useful siblings before exhausted siblings. Utility, cost, and redundancy are auxiliary
heads. A redundancy head can propose equivalence checks, but only canonical identity, Z3, Alive2,
or another declared verifier may merge states.

The runtime is an anytime priority queue. `fast` and `guided` stop under explicit budgets;
`exhaustive` uses the same learned ordering but eventually explores every state not removed by a
sound deterministic mechanism. Evaluation replays held-out projects online and reports useful
recovery at 1, 5, 10, 20, 30, 50, and 100 percent of exhaustive work, plus first discovery,
proof/compiler calls, candidate construction, frontier size, and exact transpositions. Phase A
requires at least 99% useful-terminal recovery by 30% work. Frontier-native future data raises the
target to 99.9% and adds retained-terminal and transposition outcomes unavailable in RC24.

```bash
python scripts/contextual_search_policy.py \
  --progress CAMPAIGN/training-v3/training-v3-progress.json \
  --manifest CAMPAIGN.json \
  --rc24-run RC24_MODEL_DIR \
  --output contextual-policy

vladder source-search run --manifest search.yaml --out-dir search-out --search-mode guided
```

## Search Safety

Every selection retains the baseline. Unknown grammar families, out-of-distribution roots, and
uncertain branches are kept. A fixed exploration reserve remains active even for in-distribution
high-confidence pruning. The headline metric is branch reduction at declared useful-descendant
recall, with 99.9% recall as the initial minimum evaluation point; compiler, proof, benchmark, and
node-expansion savings are supporting metrics.

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
