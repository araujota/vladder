## 1. Research And Requirements

- [x] 1.1 Research official Zig and Julia compilation, semantic IR, project identity, and proof surfaces.
- [x] 1.2 Specify shared-vocabulary support envelopes and explicit non-claims.
- [x] 1.3 Strictly validate the OpenSpec change.

## 2. Shared Proof Core

- [x] 2.1 Implement language-neutral exact-reduction schedules and parametric Z3 obligations.
- [x] 2.2 Bind regenerated native source to the proved schedule rather than trusting candidate metadata.

## 3. Zig Adapter

- [x] 3.1 Capture Zig source/build identity, compiler artifacts, effects, and common semantic graph.
- [x] 3.2 Regenerate native Zig candidates and emit proof/differential/benchmark artifacts.
- [x] 3.3 Add inspect, isolate, synthesize, optimize, audit, and support surfaces.

## 4. Julia Adapter

- [x] 4.1 Capture project/manifest/world/specialization identity and lowered, typed, LLVM, native artifacts.
- [x] 4.2 Regenerate native Julia candidates and emit proof/differential/benchmark artifacts.
- [x] 4.3 Add inspect, isolate, synthesize, optimize, audit, and support surfaces.

## 5. Product And Validation

- [x] 5.1 Add workflows, diagnostics, installer support, docs, examples, README, and skill guidance.
- [x] 5.2 Test deterministic capture, supported regions, and fail-closed unsupported boundaries.
- [x] 5.3 Test native compilation/JIT, source regeneration, Z3, Alive2-compatible proof units, differential execution, and ranking.
- [x] 5.4 Run full regression, strict doctor, package build/install smoke, and refresh the local skill.
