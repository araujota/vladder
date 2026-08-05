# Grammar Authoring Tutorial

## 1. Start From Attribution

Add a grammar family only for measured cycles, bytes, cache traffic, dependency depth, repeated
realization, or synchronization. Record the workload and expected regional ceiling. A theoretically
interesting rewrite without attribution does not enter the production grammar.

## 2. Name The Semantic Operation

Express the invariant operation in `SemanticFlowGraph v2` before choosing a language or ISA. Reuse
existing nodes for values, state, control, materialization, transfer, lifetime, and protocols.
Language syntax and intrinsics belong in provenance and typed obligations unless they represent a
genuinely new semantic concept.

## 3. Define A Finite Derivation

Create a versioned grammar JSON under `vladder/grammars/<family>/grammar.json`. Each rule needs:

- stable family and rule IDs;
- source and destination information-flow forms;
- legality facts and bounded parameters;
- proof obligations;
- cost signals;
- a maturity and realization classification.

Register a callable lowerer in the capability registry. `vladder lower validate` fails if a rule
has no owner or if the lowerer claims undeclared rules.

## 4. Implement Realization Honestly

A deterministic plan lowerer is required for every rule. Source generation is separate. Return
`adapter_required` when the selected language, ABI, protocol, or code shape has no executable
emitter. Never substitute a scalar fallback while reporting an ISA-specific physical identity.

## 5. Bind Proofs

Emit typed obligations with stable IDs. Use Z3 for bounded algebra, state, bitvectors, extents, and
protocol transitions; Alive2 for tractable LLVM refinement; differential execution for concrete
memory and edge behavior; project tests for owning/external integration. State excluded claims in
the graph and report.

## 6. Add Good And Bad Seeds

Every family contributes at least one accepted derivation and one deliberately invalid candidate
or contract. The negative seed must fail for the intended semantic reason. Add deterministic tests
and include the family in `scripts/validate_release_seeds.py` when it is part of the public path.

## 7. Require Physical Evidence

Benchmark the reference and candidate in the same executable, randomize order, retain every sample,
and predeclare effect thresholds. Static costs only prune. A grammar is not validated by compiler
success or a microbenchmark that does not affect the attributed workload.
