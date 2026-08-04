# Change: SKSF Measurement and Portfolio Ranking V6

## Why

Kernel timing can improve while tokens/sec regresses, and aggregate averages can hide an
important workload failure.

## What Changes

- Require process-level randomized hardware measurements and manifest compatibility.
- Add workload floors and bootstrap portfolio ranking.
- Record PMU unavailability and instrumentation contamination explicitly.

## Success

No candidate is accepted unless its confidence interval clears the portfolio target and
every workload satisfies its declared floor.
