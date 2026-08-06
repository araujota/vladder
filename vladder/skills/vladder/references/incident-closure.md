# Grammar Incident Closure

rc17 divides previously opaque failures into three classes.

1. **Locally representable:** typed SPIR-V operations, definition-visible helper effects,
   aggregate/member projections, exception cleanup traces, atomics, volatile accesses, and bounded
   no-growth subregions. These enter `SemanticFlowGraph v2` with typed obligations.
2. **Contract bounded:** ownership, publication, rollback, queue, partial socket, and device
   lifecycles. Use `vladder protocol template|verify`; preserve external calls and prove only the
   declared finite state projection.
3. **Physically external:** driver internals, firmware, display scanout, network behavior, and
   undeclared third-party state. Keep these as application runners and measured boundaries.

For structured C++ owners, read `structured_lowering_route`:

- `bounded_local_lowerer`: local executable candidate generation is available.
- `finite_protocol_plan_then_local_lowerer`: bind the state protocol, then optimize closed helpers.
- `architectural_realization_plan_adapter_required`: an agent must implement ownership, cleanup,
  fallback, and complete observables.

Recognition is not a performance claim. Promotion still requires candidate proof, complete
differential observables, paired physical ranking, and composed application confirmation.
