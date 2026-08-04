# Change: Projection Measurement V5

## Why

V4 identifies projection nodes but not activation preparation versus fused weight
decode/dot execution, nor performance across prompt, decode, and token tiles.

## What Changes

- Add opt-in projection-substage instrumentation and phase/regime labels.
- Add portfolio manifests and regression floors.
- Require profiler-free randomized physical ranking.
