# Change: Q4_K Physical Bounds and Byte Accounting V8

## Why

Optimization headroom cannot be judged from runtime shares without representation,
memory-system, arithmetic, ISA, and dependency floors.

## What Changes

- Account for logical bytes, physical cache lines, activation reuse, and useful MACs.
- Calculate measured-access-pattern memory, optimistic ISA, and recurrence floors.
- Compare observed execution to each floor and qualify the active-bound classification.

## Success

The report states what each bound assumes, compares it with observed runtime, and makes no
physical optimality claim.
