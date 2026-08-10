# Design: v2-only training pipeline

## Producer invariant

Every training producer returns `vladder-model-training-bundle-v2`. Public validation may still
recognize v1 for historical artifact inspection, but queue and transport functions require v2.

## Terminal workflow graph

The finalizer prefers a bounded semantic graph captured in the stage report. When a stage report
does not contain one, it emits a typed workflow-evidence graph representing semantic capture,
candidate generation, proof, measurement, integration, and promotion states. The fallback is
explicitly versioned as workflow evidence; it is not represented as source-level computation.

Every bundle contains a baseline candidate. A generated candidate is included only when the
workflow reports one. Proof, benchmark, composition, and negative observations remain separate so
the model can rank actions without confusing workflow completion with optimization success.

## Upgrade behavior

Outbox flush moves legacy v1 records into an owner-only quarantine directory. It reports the
quarantine count and does not attempt network transport. New enqueue and submit calls fail closed
for v1.

## Service boundary

`POST /api/training` returns `410 Gone` before reading or storing a body. The append capability and
`POST /api/training/v2` remain unchanged. Historical tables are retained and have no public read
path.

