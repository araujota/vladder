## 1. Support And Extraction

- [x] 1.1 Define the finite region support matrix and adapter taxonomy.
- [x] 1.2 Implement independent canonical ABI and loop-shape extraction.
- [x] 1.3 Emit deterministic support and adapter reports.

## 2. Regeneration And Proof

- [x] 2.1 Implement exact ordered-unroll source regeneration with scalar tails.
- [x] 2.2 Register structural candidates and Z3 proof schemas.
- [x] 2.3 Orchestrate strict memory, LLVM refinement, differential, benchmark, and source-identity gates.

## 3. Public Workflow

- [x] 3.1 Add automatic region API request and result types.
- [x] 3.2 Add `vladder region inspect|optimize` commands.
- [x] 3.3 Document support boundaries and adapter handoff in the skill.

## 4. Independent Validation

- [x] 4.1 Build an isolated C fixture workspace covering every supported class.
- [x] 4.2 Test unsupported ABI, multi-loop, external-call, and control-flow adapters.
- [x] 4.3 Run end-to-end proof workflows for all supported classes.
- [x] 4.4 Run full source and clean-wheel tests before changing the package version.
- [x] 4.5 Update the package version, rebuild, audit, and retest the final artifact.
