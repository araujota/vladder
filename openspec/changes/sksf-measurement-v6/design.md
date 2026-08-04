# Design: SKSF Measurement and Portfolio Ranking V6

The ranker consumes independent-process tokens/sec samples. It bootstraps workload and
portfolio effects, checks each relative-performance floor, and rejects a candidate even
when its aggregate score is positive if one required workload fails. Hardware manifests,
candidate order, held-out workload identity, and profiler state are retained.
