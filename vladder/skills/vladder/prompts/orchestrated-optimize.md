# Orchestrated Optimization Prompt

Use this recipe for a measured production region.

1. Run `vladder consent show` and resolve only unknown contribution scopes with the user.
2. Run `vladder can-optimize SYMBOL --source SOURCE --project ROOT --out-dir OUT`.
3. Read `OUT/optimization-plan.json`: classification, first unreachable state, authority map,
   grammar coverage, representativeness, forecast, and economic decision.
4. If the decision is `STOP`, retain the negative evidence. If `ESCALATE`, complete the named
   scaffold; do not expand search. If `CONTINUE`, run `vladder optimize` with the same inputs.
5. Read `OUT/disposition.json` and report exactly: coverage, candidate, proof, measurement,
   integration, terminal status, and the executable next command.
6. Use `vladder resume --out-dir OUT` after changing a contract, oracle, workload, or adapter.
7. Open specialist artifacts only when one of the five decisive facts requires explanation.

Planning, inferred contracts, discovered tests, static models, and generated adapters have no proof
or promotion authority. Never apply source unless application integration and every promotion gate
pass.
