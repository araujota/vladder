# Design: Weight Traversal Search V9

Search enumerates token tile, sequence tile, projection sharing, traversal, runtime policy,
and speculation. Static scores estimate useful MACs per model-byte proxy, lane efficiency,
latency, and queue exposure; they prune only and never constitute physical acceptance.
Autoregressive decode cannot create same-sequence token tiles greater than one without an
enabled exact speculative protocol. The result classification is `best_verified_found`
unless exhaustive local coverage and sound pruning justify a narrower claim.
