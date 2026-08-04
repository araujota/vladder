# Design: Operator Synthesis E2E V3

The orchestrator resolves contract, source/manifest, grammar, target, objective,
tuning trace, and held-out trace into immutable hashes. It executes analysis,
search, admission, compilation, static filtering, tuning, held-out measurement,
final verification, ranking, and patch/report emission. A run state file allows
resumption but completed artifacts are content-addressed.

Acceptance is a separate evaluator over evidence. It never converts an
implementation checkbox or synthetic benchmark into a production-domain claim.
