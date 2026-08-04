## 1. Requirements And Frontend

- [x] 1.1 Define the bounded C++ support matrix and proof classifications.
- [x] 1.2 Load and sanitize exact compilation-database commands.
- [x] 1.3 Extract concrete functions, methods, and template instantiations with Clang AST.
- [x] 1.4 Emit production LLVM IR and source/IR provenance.

## 2. Isolation And Verification

- [x] 2.1 Isolate canonical pointer, `std::span<float>`, and borrowed vector kernels.
- [x] 2.2 Generate adapter preconditions and Z3 extent proofs.
- [x] 2.3 Emit C++ source regeneration and compile it with the production command.
- [x] 2.4 Route isolated kernels into the existing automatic optimization workflow.

## 3. Fail-Closed Adapters

- [x] 3.1 Classify ownership/RAII, exception, external API, memory-order, and overload gaps.
- [x] 3.2 Ensure unsupported C++ emits no local-equivalence or whole-method proof claim.

## 4. Public Workflow And Validation

- [x] 4.1 Add CLI and library inspect, isolate, and optimize surfaces.
- [x] 4.2 Build an independent C++ fixture corpus with a compilation database.
- [x] 4.3 Test supported pointer, span, vector, method, and template regions.
- [x] 4.4 Test unsupported RAII, exception, external-call, concurrency, and overload cases.
- [x] 4.5 Run unit, proof, CLI, and clean-package tests.
- [x] 4.6 Update README and coding-agent skill documentation.
