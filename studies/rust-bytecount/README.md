# Rust Adapter Transfer Study

This study pins `llogiq/bytecount` and evaluates the first vLadder Rust adapter against a real
`no_std` systems crate. `benchmark.rs` compares the crate's production dispatch with its exported
iterator-fold reference in one executable. The generated vLadder benchmark separately compares
each proved native Rust schedule candidate with that reference.

The study must record the upstream commit, compiler identity, feature set, vLadder report path,
proof status, paired confidence intervals, and whether any source patch was promoted. A local
candidate is not allowed to replace `bytecount::count` merely because it beats `naive_count`.
