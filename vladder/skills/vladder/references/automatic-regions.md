# Automatic Bounded Regions

`vladder region` is the fail-closed path for unattended extraction, source regeneration, proof,
benchmarking, and optional promotion. Its support matrix is versioned as `bounded-regions-v1`.

## Automatically Supported Boundary

The source must be C and define exactly one target region with this ABI:

```c
void transform(float *dst, const float *src, size_t n);
```

`static` and C `restrict` qualifiers are accepted. The target must contain one braced `size_t`
loop, a constant start, unit increment, and a bound of `i < n` or `i + C < n`. The admitted
information-flow classes are pointwise maps, guarded pointwise maps, bounded stencils, ordered
scans, ordered recurrences, and constant-stride modulo-n indirect reads. Allocation, I/O,
volatile/atomic access, external calls, and nonlocal loop control are excluded.

Inspect before optimizing:

```bash
vladder region inspect --source region.c --function transform --out-dir vladder-inspect
vladder region optimize --source region.c --function transform --out-dir vladder-out
```

The optimizer emits a source-regenerated scheduling candidate and runs structural legality, Z3
loop partition, Z3 memory-footprint, LLVM refinement, differential execution, and physical
benchmark gates. LLVM refinement uses canonical IR identity when the proof functions are
alpha-identical and Alive2 otherwise; the report records whether `alive-tv` was invoked. A
statistical tie or baseline win is valid and emits no patch.

The package also exposes explicit ordered-unroll source regeneration for analysis. That
realization preserves iteration and statement order plus a scalar tail, but strict automatic
promotion uses the source scheduling realization because Alive2 may not terminate on explicitly
duplicated scan or recurrence loops. Proof reports state this distinction.

## Adapter Handoff

`adapter_required` is a result, not a partial success. The report names the missing semantic
boundary and the next workflow. Current adapter classes include:

- `language-adapter`: isolate a restricted C++ region behind an `extern "C"` C semantic capsule.
- `abi-adapter`: map project arguments, outputs, shapes, and state to an admitted contract.
- `loop-shape-adapter`: identify a legal single-loop slice or use operator/pipeline extraction.
- `external-call-adapter`: inline a pure call or provide its modeled semantics and side effects.
- `control-flow-adapter`: make early exits and nonlocal control explicit in a region contract.
- `memory-order-adapter`: model volatile, atomic, ownership, and ordering obligations.
- `compiler-adapter`: provide the production compile command, includes, defines, and target flags.
- `region-class-adapter`: route multi-stream, stateful, quantized, concurrent, or otherwise
  specialized work to the corresponding vLadder graph and verifier.

Never rewrite an unsupported region merely by imitating an automatic candidate. Build the named
adapter, rerun inspection, and preserve the adapter's contract in the proof artifact.
