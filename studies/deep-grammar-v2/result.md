# Deep Shared Grammar V2 Result

## Question

The preceding Rust byte-count study found that five source-level schedule candidates all regressed
while the upstream implementation was 8.16x faster than the baseline. That was not a dispositive
hardware result: the grammar could not express the upstream word/SIMD information realization.

This study tests the stronger chain:

`expert source -> shared representation -> grammar derivation -> native lowering -> proof -> hardware`

## Frozen Environment

- CPU: AMD Ryzen 9 7950X3D, CPU 2 pinned, one visible thread per core
- governor: `performance`; boost remained enabled
- OS: Linux 7.0.0-28-generic x86_64
- Clang/LLVM: 20.1.2
- rustc: 1.85.0, LLVM 19.1.7
- Z3: 4.16.0
- Alive2: LLVM 20.1.2 optimized build
- grammar: `deep-v2`
- benchmark: 1,048,576 bytes, 128 calls per process sample
- ranking: 10 process pairs, 3 repetitions per variant, randomized order, bootstrap 95% interval
- expert transfer: 10 process pairs, 5 repetitions per variant

Frequency was not fixed, so the paired randomized design controls short-term drift but does not
replace a separate-day/fixed-frequency production confirmation.

## Grammar And Expert Audit

The grammar contains 10 families, 27 typed rules, and six terminal realizations: scalar,
word-SWAR, AVX2 mask/popcount, AVX2 byte accumulation, and guarded versions of both AVX2 paths.
Rules record semantic preconditions, physical parameters, complexity deltas, proof obligations,
and hardware cost signals.

The pinned `bytecount` revision `f06647f90a45ab302d9423dbe85019d595abf8c2` supplied four real
expert routes:

- equality count: scalar -> word-SWAR
- equality count: scalar -> AVX2 byte accumulation
- UTF-8 leading-byte count: scalar -> word-SWAR
- UTF-8 leading-byte count: scalar -> AVX2 byte accumulation

All four passed representation, derivation, native Rust lowering, and the applicable proof
envelope. The first audit exposed a real frontend failure to normalize `(byte >> 6) != 0b10`; that
gap was fixed in the shared predicate recognizer before the audit passed.

## Proof

Exact obligations include packed-word bit-vector identities, lane masks, population and horizontal
reductions, traversal/tail coverage, unaligned-load legality, constant synthesis, dispatch
completeness, and bounded byte-lane no-wrap through the 255-block flush interval. Bidirectional
Alive2 checks cover the vector mask/popcount and compare-to-byte-accumulator cores. Native
differential execution covers all 65,536 singleton value/needle pairs and every length from 0
through 520 with adversarial needles.

## Physical Ranking

Positive values are speedups over the generated scalar realization in the same executable.

| Language | Best terminal | Paired effect | Bootstrap 95% interval | Search class |
|---|---|---:|---:|---|
| C | AVX2 byte accumulation | +310.85% | [+305.96%, +315.89%] | `bounded_optimal_local` |
| Rust | guarded AVX2 byte accumulation | +277.64% | [+262.23%, +280.05%] | `bounded_optimal_local` |

Rust direct and guarded AVX2 forms compiled to the same normalized hot assembly under
`target-cpu=native`, so only one physical identity was ranked. The result is about this finite
grammar region and cache-hot repeated 1 MiB workload, not every equivalent implementation.

## Expert Transfer

The generated Rust byte-accumulator was also compiled into one executable with `bytecount` built
at the pinned revision with `runtime-dispatch-simd` enabled.

| Candidate versus upstream expert | Paired effect | Bootstrap 95% interval | Exact observable |
|---|---:|---:|---|
| direct AVX2 deployment contract | +4.91% | [+3.23%, +6.53%] | PASS |
| guarded AVX2 with scalar fallback | +6.07% | [+4.79%, +6.80%] | PASS |

For the guarded comparison, median upstream time was approximately 10,573 ns per 1 MiB call and
generated time was approximately 9,966 ns. This is a regional benchmark win, not an integrated
application or end-to-end throughput claim.

## NeuralFusion Read-Only Validation

Nine existing C++ information-flow artifacts were inspected without rerunning extraction or
changing NeuralFusion. Before/after revision and dirty-worktree fingerprints were identical. All
nine boundary graphs mapped into the shared vocabulary; none contained the exact byte-predicate
archetype, so the result correctly requested local archetype extraction rather than synthesizing an
unrelated candidate. Lifetime, protocol, GPU, and other grammar workflows remain independent.

## Conclusion

The previous negative result was a grammar-depth failure, not evidence that no faster equivalent
existed. Deepening the shared vocabulary to represent lane packing, mask/reduction structure,
bounded byte accumulators, tails, and dispatch exposed large verified wins and regenerated a
candidate that slightly outperformed a pinned expert implementation.

The broader mission remains open. `deep-v2` closes one bounded archetype; it does not yet provide
general expression-to-SIMD synthesis for arbitrary LLVM IR, arbitrary reductions, data-dependent
control, gathers/scatters, or algorithm invention. Future negative claims must continue to carry
the exact grammar and expert-audit coverage that makes them meaningful.
