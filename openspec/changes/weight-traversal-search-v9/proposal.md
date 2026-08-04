# Change: Weight Traversal Search V9

## Why

Token, sequence, traversal, and runtime choices form a bounded cross-product whose legality
depends on autoregressive readiness and the V8 grammar-admission decision.

## What Changes

- Exhaustively enumerate the declared local V9 grammar.
- Reject unavailable future-token lanes, unadmitted projection sharing, and disabled speculation.
- Apply static dominance and emit every derivation and rejection.

## Success

The complete bounded product is audited and every retained plan has a guarded fallback.
