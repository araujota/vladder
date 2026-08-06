# Cross-TU Semantic Closure

vLadder closes ordinary project-defined helper calls across translation units without turning the
whole application into one optimization search.

```bash
vladder build index \
  --compile-commands build/compile_commands.json \
  --out vladder-whole-build-index.json

vladder build closure \
  --compile-commands build/compile_commands.json \
  --seed _ZN7project9transformERKNS_5InputE \
  --max-upstream 1 \
  --max-downstream 3 \
  --max-nodes 128 \
  --out-dir vladder-cross-tu
```

The seed is the concrete mangled symbol selected by the build. `whole-build-index.json` binds
translation-unit commands, sources, output objects, definitions, and references. The closure run
then emits:

- `bidirectional-slice.json`: bounded callers, callees, direct edges, and unresolved boundaries;
- `ownership-closure.json`: memory/resource construction, borrowing, mutation, publication, and
  retirement;
- `proofs/`: Z3 provenance, edge-disposition, effect-closure, ownership, and search-separation
  obligations;
- `cross-tu-closure-report.json`: the decisive report.

## What This Closes

- out-of-line project helpers with one build-resolved definition;
- same-build call chains and recursive SCCs;
- upstream callers whose object files reference the selected symbol;
- ownership/effect composition when the required relations are local or explicitly contracted.

## What It Does Not Close

- an arbitrary callback or unresolved virtual target;
- a third-party implementation absent from the indexed build;
- syscall, driver, device, or network behavior;
- concurrent publication without a finite protocol contract;
- ambiguous weak/COMDAT definitions unless equivalent bodies are established;
- functional equivalence across a call merely because its effects are summarized.

AST, LLVM IR, and linker/object evidence have distinct roles. The AST supplies source types and
ownership structure, LLVM supplies executable operations and direct calls, and object symbols
identify build definitions and references. A local AST alone cannot establish which weak or inline
definition the final link selected.

Indexing and semantic summaries add zero implementation candidates. Candidate generation remains
bounded to attributed closed regions inside the selected slice.

