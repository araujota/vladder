## Context

The existing `agent_workflow` produces a promotion summary and has whole-workflow content
identity, but routing still starts from a hand-authored `region.kind` and `region.action`.
Specialized frontends expose distinct capability reports, adapter generation is mostly C++-local,
and project evidence has no shared discovery schema. The new layer must orchestrate those systems
without pretending that arbitrary C++, external APIs, GPU drivers, or remote machines are locally
provable.

## Decisions

### 1. One planner, existing executors

The orchestrator emits an immutable plan before execution. Each plan step delegates to an existing
frontend or evidence subsystem. The planner does not become a second proof engine or grammar.
Legacy bounded-C optimization continues to call the existing optimizer implementation.

### 2. Reachability is evidence-state forecasting, not a proof claim

The feasibility pass predicts the first unreachable state from source shape, available tools,
declared or discovered oracles, and known frontend capabilities. Every forecast records confidence,
reasons, dependencies, estimated runtime range, and artifact count. Execution evidence supersedes
the forecast.

### 3. External authorities are semantic categories

The boundary map uses shared categories such as device runtime, foreign object model, network I/O,
filesystem I/O, allocator, callback, synchronization, exception/unwind, and dynamic dispatch.
Library names may be recorded as observations but do not create language- or vendor-specific core
semantics. Each category maps to a proof impact and a measurement or adapter strategy.

### 4. Five decisive facts plus an explicit terminal status

Default output reports semantic coverage, candidate generation, proof, physical measurement, and
application integration. A separate terminal status identifies `NO_COVERAGE`, `NO_CANDIDATE`,
`NO_PROOF`, `NO_BENCHMARK`, `INTEGRATION_REQUIRED`, `VERIFIED_REJECTION`, or `PROMOTABLE`.
Specialist detail remains available through artifact lineage.

### 5. Every remediation is executable

Failures contain category, ownership, evidence impact, exact artifact or manifest fragment to edit,
generated scaffold paths, and an argv-form next command. Prose remains explanatory only. Schema
diagnostics include an RFC 6902-style patch when a safe mechanical correction exists.

### 6. Stage-addressed recovery

Discovery, classification, feasibility, execution, and disposition each have keys derived from
their actual inputs. `resume` reuses valid stages and starts at the first invalid stage. External
hardware observations carry separate workload/hardware identities and are never silently reused as
fresh physical evidence.

### 7. Grammar coverage qualifies negative results

The report lists recognized expert families, executable grammar matches, plan-only matches, and
unrepresented families. A negative can be called `grammar_exhausted_negative` only when all
declared relevant expert families are executable and evaluated; otherwise it is
`grammar_limited_negative`.

### 8. Representativeness is multidimensional

Proof-unit representativeness is scored separately for dataflow, ownership, control flow, call
closure, and workload share. The aggregate score cannot promote a candidate and does not hide a
zero dimension. It decides whether local evidence may support application integration work.

### 9. Physical runners share one protocol

CPU processes, CUDA, Vulkan, generic device timestamps, network/RDMA, presentation, and remote
executors use a common command/result envelope with exact observable hashes, timing domains,
hardware/workload identity, counters, and integrity hashes. Backend-specific adapters populate the
envelope; they do not change proof authority.

### 10. Consent remains durable and independent

Optimization orchestration reads the existing local consent state and performs the already-defined
terminal v2 training contribution when enabled. It never reprompts a settled decision. Periodic
experience review remains separately approved, and campaign templates prepopulate objective fields
without submitting qualitative content.

## Risks

- Heuristic classification could route incorrectly. Plans expose confidence and alternatives, and
  `--plan-only` allows inspection before execution.
- Oracle discovery could mistake a test name for a complete observable. Discovered evidence is
  `candidate` until explicitly bound; it never satisfies promotion by discovery alone.
- Concise output could obscure proof boundaries. Every badge carries a one-sentence claim and a
  lineage reference, while `--verbose` exposes the complete plan and evidence.
- Runtime forecasts will be imperfect. They are ranges calibrated by stage history and labelled as
  estimates, not scheduling guarantees.

## Validation

Validate routing and compatibility on C, C++, Rust, Zig, Julia, shader, protocol, and lifetime
fixtures. Seed external boundaries, missing contracts, weak proof units, measured regressions,
overlapping composition effects, cache invalidation, and remote-result tampering. Confirm that the
same bounded-C command still runs the old optimizer, that no scaffold is promotable, and that
training contributions remain v2-only and consent-gated.
