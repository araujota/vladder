# Design

The package owns the fixture construction and assertions in `vladder.production_smoke`. A thin
script and CLI command serialize the same report. Each stage returns explicit assertions, metrics,
duration, and status; the aggregate passes only when all eight stages pass.

The identity and POR stages compare exact canonical terminal hashes against unreduced search. The
incremental stage compares bounded updates with clean rematerialization and deliberately corrupts a
component update to exercise fallback. The expensive stage invokes Z3 and Clang for each terminal
under both raw and reduced search. The cost-gate stage uses unseeded measured-cost policy and must
decline POR. Concurrency stresses collision-safe interning. Resume validates every identity binding.
Scaling uses a source-anchored selected-build composition fixture at widths two through four.

The battery is intentionally self-contained and does not require downloaded application sources.
The complete RC26/RC27/three-system qualification remains the broader authority.
