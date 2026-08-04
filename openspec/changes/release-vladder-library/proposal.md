## Why

SiliconTune has accumulated a capable research implementation, but its public identity, APIs,
dependency setup, grammar inventory, and agent workflow remain tied to project-specific
experiments. A vLadder release candidate is needed so a coding agent can apply the verified
information-flow workflow to performance-sensitive C/C++ code without reconstructing the
research environment.

## What Changes

- **BREAKING** Rename the distributable package and primary CLI from `silicontune` to
  `vladder` (Velocity Ladder), while documenting a bounded migration path.
- Add a stable Python library facade for analysis, synthesis, verification, benchmarking,
  artifact inspection, and patch generation.
- Add a versioned, machine-readable C/C++ capability and grammar registry spanning expression,
  control-flow, loop, memory, reduction, layout, state, concurrency, specialization, and
  pipeline concerns.
- Make proof obligations explicit: generated replacements are not promotable unless contract,
  structural, differential, SMT, and Alive2 results satisfy the selected verification policy.
- Add `vladder doctor`, a reproducible installer, pinned optional Alive2 build support, and an
  installable Codex `SKILL.md` with focused workflow references.
- Remove generated benchmark outputs, caches, vendored application trees, and research-only
  residue from the release candidate while preserving source, tests, grammars, specifications,
  and representative examples.
- Dry-run the packaged installation and skill workflow against NeuralFusion and retain a
  machine-readable release validation report.

## Capabilities

### New Capabilities

- `vladder-public-api`: Stable package, CLI, library facade, artifact model, and compatibility behavior.
- `cpp-information-flow-grammar`: Versioned grammar registry and semantic contracts for broad C/C++ optimization concerns.
- `proof-gated-replacement`: Zero-trust source reconstruction and promotion policy backed by Z3, Alive2, structural checks, and differential tests.
- `vladder-distribution`: Reproducible dependency installation, health checks, skill installation, release trimming, and dry-run validation.

### Modified Capabilities

None. Historical capabilities remain archived research inputs; the release contracts are new.

## Impact

The Python package directory, command names, generated artifact defaults, tests, examples,
documentation, grammar files, and OpenSpec metadata are affected. Runtime dependencies become
explicit (`PyYAML` and `z3-solver`), while Clang/LLVM, llvm-mca, perf, and Alive2 are managed as
external toolchain dependencies by the installer and reported by `vladder doctor`.
