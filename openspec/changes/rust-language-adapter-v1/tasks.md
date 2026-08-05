## 1. Research And Protocol

- [x] 1.1 Research rustc/Cargo IR, proof tools, source semantics, and physical tooling.
- [x] 1.2 Implement and validate a versioned general LanguageAdapter protocol.
- [x] 1.3 Strictly validate this OpenSpec change.

## 2. Rust Semantic Frontend

- [x] 2.1 Capture Cargo metadata, exact rustc identity, target/profile/features, and source hashes.
- [x] 2.2 Resolve a concrete Rust function and emit source, MIR, LLVM IR, assembly, and provenance.
- [x] 2.3 Build a deterministic Rust information-flow graph and verbose closure/effect classification.

## 3. Rust Synthesis And Proof

- [x] 3.1 Implement the first bounded R1 exact-reduction grammar and deterministic native Rust regeneration.
- [x] 3.2 Implement MIR-derived bounded Z3 equivalence with explicit panic/overflow scope.
- [x] 3.3 Compile candidate MIR/LLVM and invoke Alive2 local refinement without overstating scope.
- [x] 3.4 Add deterministic differential tests and a same-executable physical benchmark harness.

## 4. Product Surface

- [x] 4.1 Add `vladder rust inspect|isolate|synthesize|optimize|audit` CLI and library APIs.
- [x] 4.2 Add diagnostics, installer metadata, examples, README, architecture, and skill guidance.
- [x] 4.3 Emit concise promotion summaries and explicit adapter recovery instructions.

## 5. Validation

- [x] 5.1 Add unit and end-to-end fixtures for supported and rejected Rust semantics.
- [x] 5.2 Pull and pin a manageable Rust systems project and run its tests/program.
- [x] 5.3 Attribute a load-bearing region, run the Rust workflow, and report measured candidates.
- [x] 5.4 Run full vLadder regression, strict doctor, OpenSpec validation, package build, and install smoke.
