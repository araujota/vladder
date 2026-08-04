# Change: Stateful Execution Verification V9

## Why

Reorganizing ready work must preserve sequence isolation, completion counts, ordering,
dispatch safety, and E1 kernel semantics.

## What Changes

- Compare final prompt and decode state across schedules.
- Enforce unchanged production binary semantics for the initial V9 transfer.
- Model commit and rollback nodes while disabling speculative execution by contract.

## Success

No execution plan is accepted with a state mismatch or unverifiable semantic transition.
