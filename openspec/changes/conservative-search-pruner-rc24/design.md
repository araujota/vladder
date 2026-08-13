# Design

## Decision Boundary

The policy receives only information available immediately before a lazy expansion decision. Search
outcomes are supervision and evaluation targets, never inference inputs.

The cascade is:

1. sound deterministic rejection;
2. canonical-state memoization;
3. exact historical decision lookup;
4. conservative learned selective prediction;
5. fail-open expansion and exploration reserve.

## Forest Reconstruction

Branches are joined by project, semantic root, search ID, branch ID, and parent branch ID. Each branch
receives post-search targets for descendant count, useful-terminal count, proof-valid/distinct/retained
severity, observed expansion cost, and terminal failure class. Online replay prunes only the highest
eligible ancestor and counts descendants that would never have been generated.

## Model

A shared graph/action/lineage encoder feeds independent grammar, candidate, and composition survival
heads plus auxiliary failure, severity, and log-subtree-cost heads. Training proceeds head-by-head and
then jointly. Survival uses an asymmetric focal loss; sibling positive/negative pairs add a margin
ranking loss. Positive branches are never downsampled. Redundant negative signatures are capped, while
hard false-keeps and false-prunes receive additional weight during a second pass.

## Policy

Independent models provide an ensemble mean and variance. A branch is prunable only when its
upper-confidence score is below a threshold calibrated for its decision stage and, when sufficiently
supported, semantic family. Unknown vocabulary, decision-level OOD, new families, retrieval neighbors
containing useful descendants, and exploration-reserve branches fail open.

Threshold selection maximizes avoided descendant expansions subject to the configured useful-descendant
recall floor. Calibration and held-project evaluation remain separate.

## Claims

The report distinguishes static branch reduction, online node-expansion reduction, proof/compiler-call
reduction where recorded, and severity of any missed positive. No model is live-eligible solely because
training completed.
