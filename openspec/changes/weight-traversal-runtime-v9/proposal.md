# Change: Runtime Planner and llama.cpp Integration V9

## Why

Weight reuse is conditional on ready work. A production plan must select legal lane groups by
phase and queue state while preserving the pinned native kernel and a universal fallback.

## What Changes

- Add a deterministic queueing and execution simulator.
- Synthesize guarded phase, lane, and context dispatch rules.
- Exercise plans through pinned llama.cpp batched execution without changing the V8-frozen kernel.

## Success

Plans preserve request completion state and dispatch only where their guards are satisfied.
