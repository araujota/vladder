# bytecount Rust Adapter Result

## Frozen Inputs

- Repository: `https://github.com/llogiq/bytecount`
- Commit: `f06647f90a45ab302d9423dbe85019d595abf8c2`
- Target region: `naive::naive_count`
- Production comparison: `bytecount::count`
- Features: default feature set
- rustc: `1.85.0 (4d91de4e4 2025-02-17)`, LLVM 19.1.7
- Alive2: LLVM 20.1.2 build
- CPU: AMD Ryzen 9 7950X3D, one pinned logical core, SMT sibling absent from the allocated CPU set
- Workload: 1,048,576 bytes, 256 calls per executable sample
- Sampling: 10 independent processes, 5 repetitions per process, randomized pair order

The crate built successfully in release mode, its normal no-default-features suite passed all 11
integration tests and 7 doctests, and the standalone linked correctness/benchmark program executed
successfully.

## Proof Result

All five generated candidates passed:

- native Rust compilation and rustfmt;
- emitted MIR operation and source-derived schedule validation;
- parametric chunk/tail schedule proof plus bounded Z3 content obligations through length 32;
- bidirectional Alive2 refinement of fixed-length LLVM wrappers;
- adversarial differential execution.

The Alive2 input erased unsupported `noalias`, `nocapture`, EH-personality, and optimization
metadata assumptions from a separately hashed proof copy. Executable LLVM operations were not
rewritten. Erasing assumptions broadens the proof domain.

## Physical Result

Positive numbers are speedups; negative numbers are regressions relative to the iterator-fold
baseline.

| Candidate | Paired effect | Bootstrap 95% interval | Disposition |
|---|---:|---:|---|
| explicit scalar | -2.00% | [-6.80%, -0.11%] | reject |
| unroll 2 | -88.56% | [-88.63%, -88.26%] | reject |
| unroll 4 | -82.51% | [-82.89%, -82.07%] | reject |
| unroll 4, 4 banks | -88.01% | [-88.28%, -87.82%] | reject |
| unroll 8, 4 banks | -90.07% | [-90.14%, -89.94%] | reject |

No source patch was emitted or promoted. The source-level unroll forms introduced guarded indexed
loads that inhibited the stronger vectorized lowering rustc already selected for the iterator
fold. This is a useful negative result and a grammar-pruning signal.

The crate's existing production `bytecount::count` path was 715.54% faster than
`naive_count` by the paired ratio, with a 95% interval of [709.41%, 722.67%]. Equivalently, it
delivered about 8.16x throughput and reduced median per-call time from roughly 255.3 us to 31.3 us
on this workload. This is an upstream production implementation, not a vLadder discovery. It
establishes that `naive_count` is a proof-transfer target rather than a production optimization
opportunity.

## Serviceability Decision

The Rust adapter is serviceable for its declared R1 envelope: it captured a real Cargo crate,
reconstructed a common information-flow graph from source and MIR, regenerated native Rust,
closed Z3 and LLVM proof layers, executed the program, physically ranked alternatives, and rejected
all harmful rewrites. The result does not establish arbitrary Rust support or a project speedup.
