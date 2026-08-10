## ADDED Requirements

### Requirement: Search lineage is first-class training data

Every current model-training bundle SHALL identify each search branch, its search, parent branch,
depth, stage, action, expansion state, child-coverage authority, and observations.

#### Scenario: Useful terminal candidate has ancestors

- **WHEN** a terminal branch has useful evidence
- **THEN** every emitted ancestor required to reach it SHALL receive a positive descendant target
- **AND** SHALL be classified `KEEP`.

### Requirement: Negative pruning labels require authority

No producer SHALL classify a branch as safely prunable merely because no useful candidate was
observed.

#### Scenario: Search was truncated

- **WHEN** a branch has no observed useful descendant and any relevant subtree is partial,
  heuristic, interrupted, or not enumerated
- **THEN** the branch SHALL be `KEEP_UNCERTAIN`.

#### Scenario: Exhaustive dead subtree

- **WHEN** every child is represented, every descendant is terminal or soundly closed, and no
  useful descendant exists
- **THEN** the branch MAY be `PRUNE_HIGH_CONFIDENCE`.

#### Scenario: Sound contract closure

- **WHEN** a contract, legality, or dominance proof soundly excludes all descendants
- **THEN** the branch MAY be `BLOCKED_BY_CONTRACT`
- **AND** the proof class SHALL be recorded.

### Requirement: Utility dimensions remain separable

The contract SHALL separately preserve proof-valid, distinct-realization, physically material,
retained, and promoted direct and descendant utility.

#### Scenario: Proof-valid candidate later regresses physically

- **WHEN** a candidate passes proof but is not physically retained
- **THEN** proof-valid descendant utility SHALL remain true
- **AND** retained and promoted descendant utility SHALL remain false or unknown according to
  coverage.

### Requirement: Search cost is observable

Each branch SHALL record bounded counts for node expansions, compiler invocations, proof calls,
benchmark runs, and elapsed search time when known so pruning evaluation can report avoided work.

#### Scenario: A branch was expanded and compiled

- **WHEN** expanding a branch invokes compilation and proof
- **THEN** the corresponding nonnegative counts SHALL be attached to that branch
- **AND** unknown costs SHALL remain null rather than be reported as zero.

### Requirement: Learning features exclude post-search evidence

The branch learning export SHALL separate pre-decision features from post-search supervision.

#### Scenario: Branch example is emitted

- **WHEN** a v3 branch is converted into a model-learning example
- **THEN** semantic topology, grammar, accumulated action path, stage, hardware, and workload SHALL
  appear in `decision_context`
- **AND** observations, coverage, branch state, search cost, and targets SHALL appear only in
  `supervision`.

### Requirement: V3 is the only current emission format

Templates, prior exports, terminal workflows, outbox enqueue, and remote submission SHALL emit or
accept `vladder-model-training-bundle-v3` only.

#### Scenario: Historical v2 bundle

- **WHEN** a v2 bundle is inspected locally
- **THEN** historical schema validation MAY succeed
- **BUT** enqueue and remote submission SHALL reject it.
