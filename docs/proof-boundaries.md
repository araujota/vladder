# Proof Boundaries

vLadder evidence is compositional, not interchangeable.

| Evidence | Establishes | Does not establish |
|---|---|---|
| schema/structural validation | artifact and graph well-formedness | semantic equivalence |
| Z3 obligation | the encoded bounded theorem | unencoded language, ownership, or protocol behavior |
| Alive2 | LLVM refinement for the supplied functions/assumptions | source ownership, arbitrary UB, driver behavior, or machine-code identity |
| differential tests | no mismatch in tested inputs/sequences | universal equivalence |
| protocol model | declared finite transitions and guards | undeclared actors, firmware, device loss, or whole external systems |
| paired benchmark | physical effect for the pinned executable/workload/hardware | portability or causality outside the measured boundary |
| project integration | selected observable and workload remain valid | unrelated application behavior |

Promotion is conjunctive. Missing, unsupported, timed-out, or failed required evidence blocks the
claim. A local proof may support a local source rewrite only when its adapter preconditions and
postconditions are separately established. It never proves an owning wrapper by association.

Use the exact claim language in `promotion-summary.json`. `workflow_completed`,
`meaningful_semantic_coverage`, `candidate_generated`, `candidate_proved`,
`physically_benchmarked`, `application_integrated`, and `production_promoted` are independent
states.

For orchestrated runs, read `disposition.json` first. Its proof badge is a concise view over the
same evidence, not a stronger proof. `PROMOTABLE` requires application integration; a locally
proved and benchmarked source candidate is `INTEGRATION_REQUIRED` until the project oracle binds
the production implementation and composed workload.
