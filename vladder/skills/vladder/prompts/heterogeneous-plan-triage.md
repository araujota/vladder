# Heterogeneous Algorithm And Policy Triage

Use this prompt only after profiling identifies a load-bearing GPU, sparse-update, queue, or
presentation region.

1. Name the exact observable boundary: output bytes/state, queue completion, packet reconstruction,
   or presentation stage.
2. Record measured attribution and provenance. Do not add a grammar because it is merely plausible.
3. Select one bounded family:
   - `gpu-stable-compaction` for predicate/prefix/stable-scatter with a finite extent;
   - `queue-overlap` for a finite operation/resource dependency DAG;
   - `sparse-update-policy` for exact sparse/dense or minimum-byte representation selection;
   - `presentation-policy` for supported swapchain modes, image count, flight count, and deadlines.
4. List every bound: elements, workgroups, operations, queues, resources, images, in-flight frames,
   and recursion depth. An unbounded SCC is an adapter, not a search input.
5. Separate generated source from executable runtime plans. State the repository binding required
   for every runtime plan.
6. Inspect every Z3 and device-protocol obligation. Treat generated GraphML and static cost as
   ranking evidence only.
7. Build one exact application runner returning `total_time_ns`, `output_hash`, `state_hash`,
   `device_identity`, and `evidence_class`.
8. Report model-only, simulated, device-timestamp, presentation-stage, and end-to-end evidence
   separately. Never promote simulated overlap or modeled frame latency.
9. For external networking, driver, and display behavior, optimize the declared policy transducer,
   then measure the actual external system. Do not place proprietary implementation internals in
   the semantic-equivalence search.
10. Promote only a proved, exact, representative physical win with a confidence interval clearing
    the declared threshold.
