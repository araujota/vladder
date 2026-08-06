# Cross-TU Closure

Use this workflow before declaring a project helper an external C++ adapter boundary.

1. Select the exact mangled seed from `cpp inspect` or `cpp audit`.
2. Build the definition/reference index from the production `compile_commands.json` and existing
   object files.
3. Materialize a bounded caller/callee slice.
4. Read `cross-tu-closure-report.json` before generating candidates.

```bash
vladder build index --compile-commands build --out whole-build-index.json
vladder build closure \
  --compile-commands build \
  --seed '<mangled-symbol>' \
  --max-upstream 1 --max-downstream 3 --max-nodes 128 \
  --out-dir cross-tu-out
```

Interpretation:

- `definition` means a unique project body was found and hash-bound.
- `ambiguous_odr` means multiple weak/COMDAT bodies remain; preserve the boundary until equivalent
  body or actual-link provenance is established.
- `opaque`, `protocol`, and indirect boundaries do not block optimization of neighboring closed
  subgraphs.
- A passing summary proof establishes definition/effect/ownership composition, not function-level
  refinement across every call.

Never import every indexed function into candidate search. Expand only to the configured slice
budget and only run computational grammars on measured, closed regions.

