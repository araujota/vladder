## 1. Registry Contract

- [x] 1.1 Define the callable lowerer and deterministic plan schemas.
- [x] 1.2 Add rule-specific legality, emission maturity, and backend metadata to the registry.
- [x] 1.3 Validate importability, family ownership, and exact rule coverage.

## 2. Lowering Implementations

- [x] 2.1 Implement family lowerers for expressions, control flow, loops, memory, and reductions.
- [x] 2.2 Implement family lowerers for layout, fusion, state, concurrency, and specialization.
- [x] 2.3 Implement family lowerers for hardware code generation and operator/pipeline planning.
- [x] 2.4 Route source-capable rules to concrete existing specialized backends.

## 3. Public Surfaces

- [x] 3.1 Add public lowering request, result, plan, engine, and coverage APIs.
- [x] 3.2 Add `vladder lower validate`, `list`, `show`, and `plan` commands.
- [x] 3.3 Update the skill and documentation to distinguish planning from source emission.

## 4. Verification

- [x] 4.1 Test every declared rule for deterministic plan lowering or contract rejection.
- [x] 4.2 Test registry failures, source-emission fail-closed behavior, and specialized routes.
- [x] 4.3 Run full tests, OpenSpec validation, package build/audit, and clean-wheel validation.
- [x] 4.4 Install and validate the repository-local skill in NeuralFusion.
