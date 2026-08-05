# Reproducible Release Demos

Run all three from a clean source checkout:

```bash
python3 scripts/run_release_demos.py --out-dir /tmp/vladder-release-demos
```

The command writes `release-demos.json` and independent artifact directories.

| Demo | Boundary | Evidence | Explicit non-claim |
|---|---|---|---|
| C pointwise capture | canonical borrowed arrays | automatic region and SemanticFlowGraph classification | no speedup |
| C++ aggregate closure | byte span, helper, multi-exit POD result | ABI/aggregate/exit Z3 closure | no owning-wrapper equivalence |
| Rust byte-count capture | monomorphic borrowed byte slice | Cargo/MIR/LLVM/native provenance and shared graph | no arbitrary Rust or speedup |

These demos are intentionally small and deterministic. They demonstrate supported semantic
boundaries and fail-closed claims. Hardware speedups belong in separately pinned benchmark
portfolios and must not be inferred from demo completion.
