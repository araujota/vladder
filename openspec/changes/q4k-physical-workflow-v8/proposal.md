# Change: Q4_K Physical Decomposition Workflow V8

## Why

Physical attribution is only reproducible when production path, model, compiler, hardware,
measurements, analyses, and decisions execute as one fail-closed workflow.

## What Changes

- Add `silicontune q4k decompose-v8`.
- Freeze and rerun V7 parity before physical analysis.
- Emit all ten required V8 deliverables and seven acceptance gates.

## Success

One command reproduces the production-semantic physical study without claiming a faster
kernel or model throughput gain.
