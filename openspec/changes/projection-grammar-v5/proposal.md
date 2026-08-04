# Change: Projection Grammar V5

## Why

The V4 pipeline grammar cannot choose activation preparation scope, quantized weight
layout, token reuse, accumulator banks, or phase-specific projection dispatch.

## What Changes

- Add seven projection grammar families and hierarchical bounded search.
- Preserve vector costs and complete derivation/rejection audits.
- Classify non-exhaustive results as `best_verified_found`.
