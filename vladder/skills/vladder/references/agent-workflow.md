# Agent Workflow Decision Tree

## One Entry Point

Create a manifest with `vladder workflow init --kind c|cpp|lifetime|shader|protocol`. Record source,
compiler configuration, semantic contract, attribution report, workload identity, held-out policy,
and minimum effect. Run `vladder workflow run` and read `promotion-summary.json` before any detailed
artifact.

## Evidence States

The states are independent and ordered:

1. `workflow_completed`: a command produced a report.
2. `meaningful_semantic_coverage`: the selected information and observables are nontrivial.
3. `candidate_generated`: a concrete alternative exists.
4. `candidate_proved`: the strongest applicable bounded proof passed.
5. `physically_benchmarked`: representative paired evidence exists.
6. `application_integrated`: the repository and project tests accept the realization.
7. `production_promoted`: all declared promotion gates passed.
8. `production_retained`: an already accepted candidate was revalidated under matching identity.

Never infer a later state from an earlier one. Use `workflow query` to traverse source-to-decision
lineage. A matching resumable key reports `revalidated`; it is not a new optimization.

## Recovery Routes

- Selection ambiguity: select the exact compilation command and mangled overload/template symbol.
- Local C++ closure only: run `cpp isolate`, then generate an application adapter.
- Object state: define a finite observable projection; use the built-in versioned-cache or
  transactional-publication verifier when semantics match exactly.
- External call, callback, coroutine, syscall, or driver: define input, output, ordering, failure,
  and state observables in a protocol plugin or application oracle. Do not summarize it as Alive2.
- Weak lifetime trace: add stable identities plus construct/transfer, consume, and repeated-use or
  complete residency events. Traces measure cost; manifests authorize invariants.
- No local rewrite: preserve an architectural information-volume finding with its measured bytes,
  lifetime, and boundary. It is a valid outcome, not a promoted source candidate.

## Physical Promotion

Use one executable for baseline and candidate, randomized process pairs, bootstrap intervals,
complete observable hashes, and composed-system confirmation. Do not compound overlapping region
effects without an interaction run. Report retained revalidation separately from discovery.
