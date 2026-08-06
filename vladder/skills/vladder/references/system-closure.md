# System Closure

Use system closure when a load-bearing path spans multiple selected functions or when a local
frontend reports ownership, helper, cleanup, dispatch, or external-call boundaries.

## Decision Route

1. Inspect every selected function with its native frontend.
2. Put the resulting support-report paths in one `reports` list.
3. Run `vladder system closure`.
4. Read `boundary_matrix`, then grouped `boundary_summary`.
5. Search attributed grammars only in `closed` functions/components.
6. For a finite protocol, establish every envelope guard and attach its proof artifact.
7. Preserve arbitrary callbacks and undeclared third-party APIs as call boundaries.

```yaml
system: hot-path
reports:
  - inspect-a/cpp-support.json
  - inspect-b/rust-support.json
  - inspect-c/zig-support.json
```

```bash
vladder workflow init --kind system --out system-workflow.yaml
vladder system closure --manifest system.yaml --out-dir system-out
vladder schema validate --kind system-closure \
  --artifact system-out/system-closure-report.json
```

## Interpretation

- `closed`: transitive effects and finite relations are represented for the selected build.
- `partial_with_local_subgraphs`: at least one local opaque boundary exists; closed neighbors remain
  eligible.
- `protocol_guard_required`: a known envelope is missing applicability evidence.
- `call-preserving-only`: retain the exact call; do not move values/control across it.
- `crossing: permitted`: guards closed, but the candidate still needs its local functional proof.

Protocol summaries always add zero candidate dimensions. If a report shows otherwise, stop: the
workflow has confused semantic closure with implementation enumeration.

Alive2 proves only local LLVM refinement. Use Z3 for finite relation/guard obligations and a
protocol verifier for state transitions. Application differential and physical evidence remain
required before source promotion.
