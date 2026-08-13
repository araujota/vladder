# Canonical-State Search RC27 Evaluation

## Disposition

`ADOPT_CANONICAL_REDUCED_SEARCH`

Adoption applies to the canonical quotient-DAG architecture and qualified action-native grammar
envelopes. It does not authorize coarse equivalence, structural dominance, arbitrary symmetry,
global macros, or ML deletion.

## RC26 Replay

The replay read all 102 retained DuckDB, llama.cpp, and RocksDB traces, including compressed
artifacts. It reproduced 66,882 states, 38,656 exact transpositions (57.8%), 28,226 canonical
owners, 19,167 proof calls, 22,860 compiler calls, and 24.65 captured cold evaluation hours. Every
one of the 1,333 U2 terminals remained attached to its canonical owner.

RC26 does not contain complete action footprints. It therefore validates exact transposition and
terminal lineage only; it cannot retroactively qualify POR, symmetry, or dominance.

## Adversarial Qualification

Thirty executable roots covered 15 independent selected-build compositions and five each for
dependency/topological scheduling, explicit alpha identities, and explicit symmetric owners.

| Measure | Result |
|---|---:|
| Raw sequence states | 35,280 |
| Unique canonical states | 1,795 |
| State reduction | 94.91% |
| Canonical candidate constructions | 5,475 |
| Reduced candidate constructions | 1,805 |
| Candidate reduction vs raw sequence | 94.88% |
| Additional POR reduction after canonicalization | 67.03% |
| Dynamic/sleep-set orderings avoided | 3,670 |
| Dependency schedules avoided | 10 |
| Alpha collapses | 5 |
| Symmetry collapses | 5 |
| Unique terminals | 295 |
| Terminal preservation | 100.000% |
| Peak reduced-search memory | 1.80 MiB |

Dynamic adjacent POR and its sleep-set representative mode produced identical terminal sets and
transition counts on this bounded envelope. This is not evidence of universal commutativity; each
skipped inversion passed complete-footprint screening and state-scoped AB/BA canonical equality.

## Net Benefit

Cheap in-memory fixtures are the negative control. Raw path enumeration took 1.27 seconds while
reduced search took 5.86 seconds, a 4.59-second regression caused by canonicalization and AB/BA
verification. POR is therefore cost-gated and should not be used for cheap grammar regions merely
because it removes states.

The same run avoided 21,100 terminal evaluation work units. Calibrating those units with RC26's
captured 4.53-second mean cold terminal cost projects 95.54 million milliseconds saved against
4.59 thousand milliseconds of measured reduction overhead. This projection establishes positive
net value for proof/compiler-expensive search; it is not a measured 26.5-hour production run.

## Mechanism Dispositions

| Mechanism | Disposition | Evidence |
|---|---|---|
| Canonical transposition | Adopt | Collision checked; RC26 replay and exact terminal parity |
| Layered/incremental hash | Adopt | Clean-rematerialization equality required |
| Grammar dependencies | Adopt when explicit | Missing metadata fails open |
| Dynamic adjacent/sleep-set POR | Adopt when footprint, AB/BA, terminal, and cost gates pass | 100% terminal parity; cheap-region negative control |
| Alpha equivalence | Adopt when IDs are explicitly non-observable | Five exact collapses |
| Typed symmetry | Bounded adoption for explicit interchangeable classes | Five exact collapses; observable IDs preserved |
| Optimization signatures | Proposal only | Exact checker still required |
| Dominance/subsumption | Proposal/fixture qualification only | Counterexample fixture correctly rejected |
| Macro/transaction reduction | Proposal/fixture qualification only | Requires descendant-set equality |
| Local e-classes | Continue bounded study | 24 e-nodes, 12 e-classes, 8.4 KB peak |
| Learned ordering | Optional | No deletion authority |

The canonical-labeling ablation reduced two raw identity-sensitive fixtures to one typed WL
partition and one bounded individualized representative. vLadder uses its internal typed bounded
individualization for this envelope; it did not add nauty/Traces as a package dependency.

## Correctness

- Forced hash collision retained two distinct states.
- Canonical bytes preserve alias, ownership, atomic/volatile, synchronization, memory-space,
  type/precision, external-observable, and hardware legality fields.
- Unknown action footprints remained dependent.
- Shared alias or contract state rejected independence.
- Both action orders had to remain legal and byte-identical.
- Full canonical, dynamic POR, and sleep-set terminal hash sets matched on every qualification root.
- A dominance and macro counterexample retained the missing terminal and rejected deletion.
- Incremental component hashes failed closed when they differed from clean rematerialization.

## Claim Boundary

The qualification shows that much of this bounded composition explosion is redundant path ordering,
not distinct semantic realization. It does not show that every vLadder grammar has complete action
footprints, that all semantic graphs have useful symmetry, or that retained production source
search will always achieve 94.9% reduction. Existing grammars without action-level application still
receive collision-safe canonical transposition but cannot claim pre-construction POR savings.
