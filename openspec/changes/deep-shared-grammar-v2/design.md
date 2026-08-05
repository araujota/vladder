## Context

The existing grammar registry has broad conceptual coverage, but its common declarative lowerer
produces guard/transform/proof/cost plan records rather than transformed semantic graphs. A
`source_routes` entry establishes that some specialized function is callable; it does not prove
that the registered rule is represented, derived, emitted, verified, or benchmarked.

The replacement design follows several primary research results:

- LLVM VPlan separates legality, plan construction/costing, and execution, and models complete
  vector loops with recipes rather than treating a vector-width flag as vectorization:
  <https://llvm.org/docs/VectorizationPlan.html>.
- LLVM IR exposes vector reductions, masks, and predication as semantic operations:
  <https://llvm.org/docs/LangRef.html>.
- Souper and Minotaur demonstrate synthesis plus formal validation over LLVM dataflow and SIMD:
  <https://arxiv.org/abs/1711.04422> and <https://arxiv.org/abs/2306.00229>.
- `egg` shows how equality saturation can retain many equivalent realizations before
  hardware-aware extraction: <https://arxiv.org/abs/2004.03082>.
- goSLP and VeGen show that lane packing, permutation, and target instruction semantics must be
  explicit search objects: <https://arxiv.org/abs/1804.08733> and
  <https://commit.csail.mit.edu/papers/2021/vegen.pdf>.

## Decisions

### 1. One semantic vocabulary, multiple language contracts

`LaneMap`, `Pack`, `MaskExtract`, `PopulationCount`, `HorizontalReduce`, `Tail`, `Dispatch`,
`Materialize`, and `Fuse` describe physical information realization for every language. C, C++,
and Rust adapters attach language-specific contracts and native emitters but may not redefine
these operations.

### 2. Graph derivations replace route-count coverage

Each deep rule has typed source and target realization patterns, preconditions, parameters,
complexity effects, proof generators, cost signals, and native emitter support. Search records the
full derivation. Registry validation distinguishes plan, graph, source, proof, and benchmark
coverage.

### 3. The first executable archetype is exact byte predicate reduction

The first archetype computes an exact count of bytes satisfying a lane-local predicate. It is
small enough for bit-vector proof but rich enough to exercise scalar-to-word/SIMD decomposition,
packing, masks, horizontal reductions, tail policy, load shape, ISA dispatch, constants, and
producer/reduction fusion. Equality and UTF-8-leading-byte predicates provide independent expert
cases.

### 4. Proof is compositional

Z3 proves lane identities, word/SIMD mask semantics, reduction equivalence, traversal coverage,
tail coverage, bounded accumulator safety, and dispatch completeness. Alive2 proves compatible
compiled core refinements where possible. Differential execution covers native source, memory,
and boundary lengths. No layer is promoted as proof of another.

### 5. Algorithmic rules carry explicit complexity contracts

Every realization records work, logical bytes, temporary bytes, passes, and asymptotic class.
Rules may alter the algorithm only when the manifest declares equal observables and an admitted
complexity relation. A lower operation count is not itself semantic proof.

### 6. Expert audits are diagnostic gates

For each scalar/expert pair, the audit asks whether both are representable, whether a derivation
connects them, whether the lowerer regenerates the expert class, whether proof closes, and whether
physical performance transfers. Failures are classified at the earliest unsupported boundary.

### 7. External repositories remain read-only validation inputs

Open-source Rust projects and NeuralFusion are fingerprinted before and after inspection. All
generated graphs, candidates, and reports are written into vLadder or temporary output trees.

## Risks

- Hand-authored intrinsic templates could merely encode known answers. The graph derivation and
  parameter search must therefore be independently inspectable and shared across emitters.
- LLVM may canonicalize several realizations to the same assembly. Assembly hashes and physical
  ties remain first-class outcomes.
- Unsafe native vector loads require language-specific bounds and target-feature obligations.
  Safe wrappers, checked dispatch, exact tails, and fallback paths are mandatory.
- Bit-vector proofs can establish lane semantics while missing memory traversal. Coverage and
  footprint obligations are separate and differential tests include adversarial boundaries.

## Validation

Validate deterministic graph hashes and derivations; seed representation, grammar, lowering, and
proof failures; prove word and vector identities; compile C and Rust candidates; compare native
outputs over exhaustive short inputs and randomized long inputs; benchmark paired candidates; and
show read-only NeuralFusion fingerprints are unchanged.
