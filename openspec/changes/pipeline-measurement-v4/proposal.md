# Change: Information Movement Measurement V4

## Why

Logical temporary bytes do not establish cache or DRAM traffic. V4 needs attributable,
multi-level estimates and physical counter evidence.

## What Changes

- Add cache-capacity/reuse-distance traffic estimates and lower bounds.
- Add operator and pipeline attribution against total decode.
- Measure counters, bandwidth, scratch/allocation, latency, and tokens per second.

## Success

Reports distinguish logical, modeled, and measured movement and refuse causal traffic
claims when counters are unavailable or statistically inconclusive.
