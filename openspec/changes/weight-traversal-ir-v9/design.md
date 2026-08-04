# Design: WeightTraversalGraph IR V9

The graph is immutable and hash-addressed. Required nodes are `WeightBlockLoad`,
`WeightMetadataDecode`, `ActivationTile`, `TokenLane`, `SequenceLane`,
`ProjectionConsumer`, `AccumulatorBank`, `ConsumerBarrier`, `Commit`, `Rollback`,
`Dispatch`, and `WeightTraversalEnd`. The manifest pins the model, llama.cpp commit,
Q4_K x Q8_K path, E1 contract, grammar choices, workload portfolio, and interactive floor.
Projection grouping remains representable but fails closed because V8 admitted only reuse
across ready token or sequence lanes.
