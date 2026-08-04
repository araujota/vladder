# Design: Projection IR V5

ProjectionComplexGraph is an immutable directed graph whose nodes describe semantic
projection substages and whose edges describe physical tensor/block flow. It retains
logical MACs and bytes separately from modeled and measured traffic. Token and sequence
counts are contract inputs rather than compile-time assumptions unless guarded.

The IR records existing llama.cpp native-repack behavior so SiliconTune does not claim
an existing output-row interleave as a new representation result.
