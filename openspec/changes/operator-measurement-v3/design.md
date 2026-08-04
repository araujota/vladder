# Design: Operator Measurement V3

The runner captures topology, affinity, NUMA node, sibling isolation, governor,
boost/frequency state, microcode, kernel, compiler, thermal readings where
available, memory, source/contract/grammar hashes, and trace identity. A manifest
hash keys all samples.

Latency samples use a serialized cycle clock and retain raw values. Quantiles are
empirical order statistics; bootstrap intervals resample independent-process
blocks. Candidate order is deterministically randomized per process. The ranker
first enforces correctness/resource/tail constraints, then applies objective and
minimum-effect rules.
