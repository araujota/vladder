## 1. Research And Architecture

- [x] 1.1 Compare Rust MIR, Zig compiler/LLVM, and Julia typed SSA/LLVM capture surfaces.
- [x] 1.2 Define the language-neutral canonical bounded-region model and claim boundary.
- [x] 1.3 Define independent semantic-capture and executable-lowering capability states.

## 2. Shared Extraction

- [x] 2.1 Implement canonical family classification and compiler corroboration.
- [x] 2.2 Implement universal SemanticFlowGraph lowering with typed obligations.
- [x] 2.3 Emit deterministic canonical-region artifacts and hashes.

## 3. Frontend Integration

- [x] 3.1 Integrate Rust source/MIR capture and preserve borrow/panic obligations.
- [x] 3.2 Integrate Zig module capture and preserve safety/error/ownership obligations.
- [x] 3.3 Integrate Julia concrete-specialization capture and preserve world/GC obligations.
- [x] 3.4 Prevent non-reduction regions from entering reduction-only synthesis.

## 4. Validation And Release Documentation

- [x] 4.1 Add a seven-family native fixture matrix for Rust, Zig, and Julia.
- [x] 4.2 Add negative tests for allocation and compiler/source mismatch boundaries.
- [x] 4.3 Update README, skill references, support matrix, and capability registry.
- [x] 4.4 Run affected tests, strict OpenSpec validation, lint, and strict doctor.
