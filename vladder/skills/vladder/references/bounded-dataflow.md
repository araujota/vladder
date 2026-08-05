# Bounded Variable-Output Dataflow

Use this workflow when the observable is a selected sequence, exact output extent, packed record,
multi-reduction, or bounded state transition rather than only a scalar count.

## Decision Recipe

1. Run `vladder dataflow coverage` and select the semantic family before selecting an ISA.
2. State exact output order, output mode, capacity policy, aliasing, exception behavior, and state
   publication semantics in a contract JSON.
3. For C++ containers, require a pre-write no-growth guard, trivial element lifetime, and a
   nonthrowing local region. `reserve()` alone does not close ownership.
4. Run `dataflow graph` to inspect typed obligations and excluded claims.
5. Run `dataflow verify` to generate C++20, source/graph binding, Z3 obligations, applicable local
   Alive2 evidence, and differential execution.
6. If an owning wrapper remains, preserve it and adapt only the proved borrowed kernel. Verify the
   adapter's capacity, status, extent, and state pre/postconditions separately.
7. Build a paired same-executable application benchmark before rewriting production source.

```bash
vladder dataflow graph --contract contract.json --target mask-prefix-stable --out graph.json
vladder dataflow verify --contract contract.json --target guarded-avx2-compaction --out-dir proof
```

## Proof Interpretation

- `exact_bounded_dataflow` covers the emitted local region and declared bounded observables.
- `exact_encoded_identity`, `exact_decoded_identity`, and `bounded_quality_only` are distinct block
  proof classes and must not be merged in a report.
- `alive2: not_applicable` is expected for variable-output memory/state protocols; inspect the Z3
  sequence and transition obligations instead.
- `production_promotion: false` means no repository rewrite or speedup has been established.

## Recovery Paths

- **Vector may allocate:** expose caller-owned storage plus capacity, or keep an explicit owning
  adapter. Do not assume `reserve()` is a proof.
- **Nontrivial records:** isolate projected trivial fields or require an ownership adapter.
- **State publication:** synthesize candidate state locally, then prove commit/rollback in a finite
  protocol adapter.
- **Dependency invalidation:** move to the lifetime/protocol workflow.
- **Floating-point geometry:** declare ordering, NaN, determinism, and tolerance before admission.
- **External APIs or concurrency:** retain a named protocol boundary; local closure can proceed
  independently but does not prove that boundary.

For architecture and research references, read `docs/bounded-dataflow-v1.md` in the source
distribution.
