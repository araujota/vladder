# Tasks

## Domain Model

- [x] Define versioned binary message, normalized event, fixed book, risk,
  feature, wire output, trace, and SPSC schemas.
- [x] Implement reference decode, book, risk, feature, encode, and ring operators.
- [x] Assert no allocation in hot paths.

## Grammar Candidates

- [x] Add word/field decode and checked common-type dispatch.
- [x] Add AoS/SoA or dense-window book layouts and best-price strategies.
- [x] Add short-circuit/mask risk forms and transactional state update.
- [x] Add incremental/recompute feature and packed/template encode forms.
- [x] Add batch-1 and microburst schedules without mixing objectives.

## Traces And Verification

- [x] Generate deterministic tuning, held-out, and adversarial traces.
- [x] Cover add/modify/delete, empty/full/crossed/duplicate/boundary states,
  risk rejection, price-window shift, and ring wraparound.
- [x] Compare every output/state/invariant after every event.

## Workflow

- [x] Add integrated replay CLI and p50-through-p99.99 reports.
- [x] Strictly validate specs and publish reproducibility evidence.
