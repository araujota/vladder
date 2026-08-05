# NeuralFusion rc6 Adapter Validation

Validation date: 2026-08-04

Scope: read-only reuse of three existing NeuralFusion `cpp-support.json` artifacts. No source,
build, skill, or audit file in NeuralFusion was changed, and no full application workflow was run.
The NeuralFusion worktree was already actively modified, so its current repository state was
treated as immutable external evidence.

## Cases

| Existing region | rc6 semantic coverage | rc6 disposition | Generated recovery |
|---|---|---|---|
| Client-cache/publication artifact | meaningful compiled closure | `external_protocol_only` | typed workload/oracle/state/protocol adapter bundle |
| GPU rendering dispatch artifact | meaningful compiled closure | `external_protocol_only` | typed adapter plus SPIR-V output/timestamp runner route |
| UDP validation artifact | selection-only | `unresolved_selection` | exact compile-command selection before semantic claims |

For both external-protocol reports, rc6 preserved the local compiled information-flow evidence and
named exception, ownership, object-state, and external-call boundaries. It did not mark a candidate
generated, proved, benchmarked, integrated, or promoted. For the unresolved UDP report it correctly
withheld meaningful semantic coverage until one of two production compilation commands is selected.

Generated bundles were written outside NeuralFusion under `/tmp/vladder-rc6-neuralfusion-validation`
and contain an adapter manifest, same-executable benchmark skeleton, complete-observable hash
skeleton, and agent task. Every bundle remains non-promotable until its TODOs are implemented.

This validates the recovery workflow, not direct optimization coverage. It also confirms the
categorical boundary: Vulkan/driver behavior and owning C++ protocols are not made formally local by
adapter generation. The new mechanism makes that boundary actionable and queryable without hiding
eligible local proof units or architectural information-flow findings.
