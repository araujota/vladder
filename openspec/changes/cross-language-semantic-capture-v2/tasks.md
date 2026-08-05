## 1. Evidence Correctness

- [x] 1.1 Make semantic recognizers boundary-aware and reject misleading constants.
- [x] 1.2 Resolve non-empty hot-code identities from symbols, assembly, or LLVM IR.
- [x] 1.3 Prevent unresolved identities or incomplete measurement from claiming bounded optimality.

## 2. Native Project Capture

- [x] 2.1 Preserve Zig module roots/imports and generate only signature-compatible wrappers.
- [x] 2.2 Load Julia packages through the declared project/module and reflect without invocation.
- [x] 2.3 Separate compiler capture, semantic closure, candidate generation, and proof dispositions.

## 3. Shared Executable Grammar

- [x] 3.1 Add C emitters for all bounded-dataflow terminals.
- [x] 3.2 Add Zig emitters for all bounded-dataflow terminals.
- [x] 3.3 Add Julia emitters for all bounded-dataflow terminals.
- [x] 3.4 Add native compile and differential verification with honest physical-distinctness metadata.

## 4. Validation And Product

- [x] 4.1 Add regression tests for false recognition, empty identity, and project-native capture.
- [x] 4.2 Run fixture and pinned upstream no-write evaluations across all four requested languages.
- [x] 4.3 Update README, skill, and reference documentation with the corrected evidence model.
- [x] 4.4 Run strict OpenSpec, full tests, package audit, and installed-skill validation.
