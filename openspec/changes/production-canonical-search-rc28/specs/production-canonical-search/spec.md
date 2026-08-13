# Production Canonical-State Search Requirements

## ADDED Requirements

### Requirement: Canonical states are production search objects

Fast, guided, and exhaustive production modes SHALL resolve canonical identity before recursive
expansion and SHALL recursively explore a canonical-identical state at most once.

#### Scenario: Duplicate concurrent discovery

- **GIVEN** two workers construct byte-identical canonical children
- **WHEN** both attempt registration concurrently
- **THEN** one state owns recursive exploration and both provenance edges are retained.

### Requirement: Exact authority fails open

Unknown footprint, dependency, canonicalization, commutativity, proof, protocol, or resource state
SHALL preserve reachability rather than authorize deletion.

#### Scenario: Incomplete action footprint

- **GIVEN** a high-cost action with an incomplete footprint
- **WHEN** adaptive POR evaluates the frontier
- **THEN** the action remains dependent and reachable.

### Requirement: Reduction is cost gated

Optional exact reductions SHALL run only when qualified and predicted to save more downstream search
work than their own analysis cost, unless exhaustive-cost minimization is explicitly requested.

#### Scenario: Cheap shallow frontier

- **GIVEN** low fanout, no proof or compiler cost, and expensive AB/BA realization
- **WHEN** the adaptive policy selects a mode
- **THEN** it selects enumeration or canonicalization without POR.

### Requirement: Search state is resumable

Long-running searches SHALL persist canonical identity, frontier, explored state, provenance, and
configuration identities, and SHALL reject incompatible resumes.

#### Scenario: Grammar changed after checkpoint

- **GIVEN** a checkpoint produced by another grammar semantic hash
- **WHEN** resume is requested
- **THEN** resume fails without exploring any stored state.

### Requirement: Memory limits preserve identity authority

Memory pressure MAY evict recomputable summaries or spill canonical blobs but SHALL NOT silently lose
identity data in a way that permits duplicate recursive exploration.

#### Scenario: Memory ceiling reached

- **GIVEN** a quotient DAG above the configured in-memory cache budget
- **WHEN** resource control reacts
- **THEN** recomputable analyses are evicted first and canonical identity remains collision safe.

### Requirement: Production evidence is mechanism resolved

Every run SHALL report canonicalization, transposition, dependency, POR, alpha, symmetry, dominance,
macro, proof, compilation, benchmark, cache, memory, and policy metrics without double-counting.

#### Scenario: Reduction waterfall

- **GIVEN** a path recognizable by transposition and POR
- **WHEN** it is removed by transposition first
- **THEN** only transposition receives avoided-work credit.

### Requirement: Production reductions preserve terminals

Every enabled exact production mechanism SHALL preserve byte-identical canonical terminal sets on its
qualification envelope.

#### Scenario: POR release gate

- **GIVEN** unreduced canonical and POR searches over a bounded fixture
- **WHEN** release qualification runs
- **THEN** terminal precision and recall are both exactly one.

### Requirement: Scaling is measured, not inferred

Release qualification SHALL compare raw path growth with canonical state, proof, and compiler growth
on at least three independent source systems and SHALL report measured expensive-root net savings.

#### Scenario: Increased composition depth

- **GIVEN** adjacent benchmark levels with broader or deeper grammar
- **WHEN** the scaling suite completes
- **THEN** raw and canonical growth factors and absolute work are reported separately.

### Requirement: Experimental mechanisms remain disabled

Learned deletion, unqualified dominance, unqualified macros, coarse optimization equivalence, and
global ownership/protocol e-graphs SHALL NOT be production deletion authorities.

#### Scenario: Dominance proposal lacks descendant proof

- **GIVEN** a structurally cheaper state without descendant-set qualification
- **WHEN** production search evaluates it
- **THEN** both states remain reachable.
