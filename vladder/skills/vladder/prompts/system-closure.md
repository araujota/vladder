# Agent Task: Compose A Load-Bearing System

Given native frontend inspection reports for a measured load-bearing path:

1. Build one system-closure manifest from the report paths.
2. Run `vladder system closure` without changing application source.
3. Report closed components, transitive effects, grouped unresolved boundaries, protocol guards,
   and the Z3 composition result.
4. Select only attributed closed components for executable grammar search.
5. Do not treat protocol summaries as implementation candidates.
6. Do not cross an arbitrary callback or third-party API without a declared finite contract.
7. State clearly that system closure is not candidate generation, local Alive2 proof, physical
   measurement, integration, or promotion.
