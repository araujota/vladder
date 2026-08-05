## ADDED Requirements

### Requirement: SPIR-V compute inspection and synthesis
vLadder SHALL compile or import a compute module, validate it, disassemble it, and generate bounded
SPIR-V optimizer candidates with deterministic provenance.

#### Scenario: GLSL compute source
- **WHEN** `glslangValidator` and SPIR-V Tools are present
- **THEN** inspection SHALL emit validated SPIR-V, disassembly, entry-point metadata, hashes, and
  candidate recipes

### Requirement: GPU proof boundary
Structural SPIR-V validation SHALL not be reported as semantic equivalence.

#### Scenario: Optimized module validates without an output runner
- **WHEN** `spirv-val` passes but no application oracle is supplied
- **THEN** the candidate SHALL remain `output_oracle_required` and non-promotable

### Requirement: Portable protocol adapters
GPU execution SHALL use explicit output and timestamp runner contracts rather than embedding
Vulkan, CUDA, driver, or presentation semantics in the core verifier.

#### Scenario: CUDA toolchain unavailable
- **WHEN** a CUDA workflow is requested without `nvcc` or a device runner
- **THEN** the report SHALL classify the missing toolchain/runner without affecting C++, lifetime,
  or SPIR-V workflows
