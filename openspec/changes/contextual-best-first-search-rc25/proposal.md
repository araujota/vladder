# Contextual Best-First Learned Search

## Why

RC24 showed that independent branch deletion cannot produce material search reduction at the required
recall. Its 43k-branch corpus nevertheless contains useful graph, lineage, contract, and outcome
evidence. vLadder should use that evidence to order finite-budget search while reserving elimination
for deterministic and formally verified authorities.

## What Changes

- Introduce frontier-level search-decision records with complete sibling context and post-search
  utility/cost labels kept outside inference features.
- Reconstruct eligible frontier decisions from complete RC24 traces without relabeling incomplete
  branches.
- Add exact canonical transposition accounting and verified-equivalence proposal hooks.
- Add contextual graph/history/frontier ranking models and anytime best-first runtime modes.
- Evaluate held-project recovery curves against FIFO, random, handwritten, and RC24-score baselines.

## Non-Claims

Learned scores are priority only. They do not establish illegality, dominance, equivalence, or safe
deletion. Fast/guided modes are incomplete by budget; exhaustive mode eventually explores every
state not closed by deterministic or formal mechanisms.
