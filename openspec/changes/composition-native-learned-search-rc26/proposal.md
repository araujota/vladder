# Composition-Native Learned Search

## Why

Phase A recovered 61% of composition-stage useful terminals at 30% work while candidate-stage
recovery reached 95.2%. Its 3,867 frontiers were reconstructed from branch records and omitted exact
state deltas, transformation interactions, transpositions, terminal retention, and stage-resolved
search costs. Composition utility is contextual, so those omissions define the next data boundary.

## What Changes

- Emit native exhaustive search states, complete frontiers, exact child deltas, interaction graphs,
  transpositions, terminal dispositions, and measured search costs from the enumerator.
- Derive tiered descendant utility and sibling-relative advantage only after exhaustive completion.
- Add coupled semantic/interactions/history/frontier models and factor-node higher-order relations.
- Integrate learned best-first ordering while preserving deterministic/formal deletion authority and
  exhaustive fallback.
- Run a bounded, composition-heavy, three-project campaign and evaluate project-held-out recovery
  against required baselines and ablations.

## Non-Claims

ML does not prove impossibility, equivalence, dominance, correctness, or performance. A finite-budget
search may omit low-priority states; exhaustive mode may not. Post-search outcomes are labels and
must never enter inference features.
