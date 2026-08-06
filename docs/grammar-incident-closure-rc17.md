# Grammar Incident Closure (rc17)

This release addresses the rc16 incident report by making available semantics explicit without
flattening external systems into local IR.

| Incident | rc17 disposition |
|---|---|
| SPIR-V logical/div/rem/dot/matrix/image/cooperative operations | Typed capture plus validity, numeric, descriptor, and capability obligations |
| Recursive C++ helpers | Definition-visible transitive effect composition; real external calls remain boundaries |
| Containers and runtime calls | Parametric call-preserving summaries; allocation, cleanup, and invalidation remain observable |
| Exceptions and RAII | Normal/exception/terminate outcome and ordered cleanup trace representation |
| Aggregates and members | Compiled ABI channels plus named old/new member projections |
| Atomics and volatile | Operation, ordering, synchronization scope, and publication descriptors |
| External protocols | Finite resource DSL with publication, rollback, retirement, and happens-before proof |
| Deep archetype mismatch | Structured sparse/cache/parse/scatter/state/lifetime recognition and lowerer routing |
| Artifact name overflow | Bounded readable identity plus stable hash |

The release does not claim generic source synthesis for owning C++ wrappers or equivalence of
driver, OpenUSD, Vulkan, socket-kernel, firmware, NIC, or display internals. It verifies declared
finite public protocols and optimizes locally closed computation around those boundaries.

NeuralFusion validation writes only to `/tmp`. The shader inventory reached complete opcode
capture for all 74 modules. The C++ matrix retained semantic capture for all 69 implementations;
20 were supported as whole local, bounded-state, or extractable-subregion proof surfaces and 49
remained explicit external-protocol boundaries. Compared with the pre-fix audit, recursive helper
composition reduced external-call adapters from 54 to 38 and increased extractable subregions from
6 to 10. Ownership, cleanup, and external protocols continue to limit whole-wrapper executable
closure. Structured evidence recognized non-byte archetypes in 68/69 implementations while
marking only existing extracted local regions executable.

The audit's tracked-diff digest was identical before and after execution. NeuralFusion remained an
artifact-only validation target; no source replacement or repository write was requested.
